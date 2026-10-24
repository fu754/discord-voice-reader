"""VC音声を発話単位に区切り、ローカルのWhisperで文字起こししてテキストチャンネルに投稿する。

処理の流れ:
    受信スレッド(AudioSink.write) → 発話の区切り(簡易VAD) → キュー → 文字起こしスレッド → Discordへ投稿
Whisperの推論は時間がかかるため、受信を止めないよう専用スレッドで行う。
"""
from __future__ import annotations

import asyncio
import importlib.util
import logging
import os
import queue
import re
import threading
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable, Final, Optional

import discord
import numpy as np
from discord.ext import voice_recv
from dotenv import load_dotenv

if TYPE_CHECKING:
    from whisper import Whisper

load_dotenv()

log = logging.getLogger(__name__)

__all__ = [
    'WhisperTranscriber',
    'TranscribeSink',
    'transcriber',
]

# discord-ext-voice-recvのPCM形式: 48kHz / 16bit / ステレオ
PCM_SAMPLE_RATE: Final[int] = 48000
PCM_FRAME_BYTES: Final[int] = 4
PCM_BYTES_PER_SEC: Final[int] = PCM_SAMPLE_RATE * PCM_FRAME_BYTES
WHISPER_SAMPLE_RATE: Final[int] = 16000

# 発話の区切りに関する設定
VAD_RMS_THRESHOLD: Final[float] = float(os.environ.get('VAD_RMS_THRESHOLD', '300'))  # これ以上の音量を発話とみなす(int16のRMS)
SILENCE_SEC: Final[float] = 0.8  # 無音がこの秒数続いたら発話の終わりとする
MIN_VOICED_SEC: Final[float] = 0.3  # 発話とみなす音声の最短秒数(短いノイズを除外)
MAX_UTTERANCE_SEC: Final[float] = 25.0  # 話し続けた場合に強制的に区切る秒数
PREROLL_SEC: Final[float] = 0.3  # 発話開始の直前から含める秒数(語頭が欠けないように)
TAIL_SEC: Final[float] = 0.2  # 発話終了の直後から含める秒数(受信できた分のみ)
MAX_GAP_SEC: Final[float] = 1.0  # パケットが途切れた時に無音で埋める最大秒数
POLL_INTERVAL_SEC: Final[float] = 0.1
MAX_PENDING_UTTERANCES: Final[int] = 20

# 文字起こしの設定
WHISPER_MODEL: Final[str] = os.environ.get('WHISPER_MODEL', 'turbo')
# 'mlx'(Apple Silicon向けのmlx-whisper)、'openai'(openai-whisper)、'auto'(mlx-whisperが入っていればmlx)
WHISPER_BACKEND: Final[str] = os.environ.get('WHISPER_BACKEND', 'auto').lower()
WHISPER_DEVICE: Final[str] = os.environ.get('WHISPER_DEVICE', 'cpu')
WHISPER_LANGUAGE: Final[str] = os.environ.get('WHISPER_LANGUAGE', 'ja')
WHISPER_BEAM_SIZE: Final[int] = int(os.environ.get('WHISPER_BEAM_SIZE', '5'))  # 1で貪欲法(速いが短い発話で不安定)
NO_SPEECH_PROB_THRESHOLD: Final[float] = 0.6
AVG_LOGPROB_THRESHOLD: Final[float] = -1.0
# 無音や雑音に対してWhisperが出力しがちな定型句
re_hallucination: Final[re.Pattern[str]] = re.compile(r'ご視聴(いただき)?ありがとうございました|チャンネル登録')


def pcm_to_whisper_audio(pcm: bytes) -> np.ndarray:
    """48kHzステレオint16のPCMを、Whisperが受け取る16kHzモノラルfloat32に変換する"""
    samples = np.frombuffer(pcm, dtype=np.int16)
    samples = samples[: len(samples) // 2 * 2].reshape(-1, 2)
    mono = samples.astype(np.float32).mean(axis=1) / 32768.0
    # 48kHz→16kHzは3サンプルの平均で間引く
    mono = mono[: len(mono) // 3 * 3]
    return mono.reshape(-1, 3).mean(axis=1)


def resolve_backend(backend: str) -> str:
    if backend not in ('auto', 'mlx', 'openai'):
        raise ValueError(f'WHISPER_BACKENDが不正です: {backend} (auto、mlx、openaiのいずれか)')
    if backend != 'auto':
        return backend
    return 'mlx' if importlib.util.find_spec('mlx_whisper') is not None else 'openai'


def mlx_model_repo(model_name: str) -> str:
    """openai-whisperのモデル名を、mlx-communityのHugging Faceリポジトリ名に変換する。"/"を含む場合はそのまま使う"""
    if '/' in model_name:
        return model_name
    if model_name == 'turbo':
        return 'mlx-community/whisper-large-v3-turbo'
    return f'mlx-community/whisper-{model_name}-mlx'


class WhisperTranscriber:
    def __init__(self, model_name: str, device: str, language: str, backend: str = 'auto') -> None:
        self.model_name = model_name
        self.device = device
        self.language = language
        self.backend = resolve_backend(backend)
        self._model: Optional[Whisper] = None
        self._loaded = False
        self._lock = threading.Lock()

    def load(self) -> None:
        """モデルを読み込む。初回のみ時間がかかる(未取得ならダウンロードも行う)"""
        with self._lock:
            if self._loaded:
                return
            started = time.monotonic()
            if self.backend == 'mlx':
                # 未取得ならここでダウンロードされる。ウォームアップで初回推論の遅延を先に済ませる
                import mlx_whisper

                mlx_whisper.transcribe(
                    np.zeros(16000, dtype=np.float32),
                    path_or_hf_repo=mlx_model_repo(self.model_name),
                    language=self.language,
                    verbose=None,
                )
                label = mlx_model_repo(self.model_name)
            else:
                import whisper

                self._model = whisper.load_model(self.model_name, device=self.device)
                label = f'{self.model_name}, {self.device}'
            self._loaded = True
            log.info('Whisperモデル(%s, %s)を読み込みました (%.1f秒)', self.backend, label, time.monotonic() - started)

    def transcribe(self, pcm: bytes) -> str:
        self.load()
        audio = pcm_to_whisper_audio(pcm)
        with self._lock:
            if self.backend == 'mlx':
                import mlx_whisper

                # mlx-whisperはビームサーチ未対応のため貪欲法で認識する
                result = mlx_whisper.transcribe(
                    audio,
                    path_or_hf_repo=mlx_model_repo(self.model_name),
                    language=self.language,
                    temperature=0.0,
                    condition_on_previous_text=False,
                    no_speech_threshold=NO_SPEECH_PROB_THRESHOLD,
                    logprob_threshold=AVG_LOGPROB_THRESHOLD,
                    verbose=None,
                )
            else:
                assert self._model is not None
                result = self._model.transcribe(
                    audio,
                    language=self.language,
                    fp16=self.device == 'cuda',
                    temperature=0.0,
                    beam_size=WHISPER_BEAM_SIZE if WHISPER_BEAM_SIZE > 1 else None,
                    condition_on_previous_text=False,
                    no_speech_threshold=NO_SPEECH_PROB_THRESHOLD,
                    logprob_threshold=AVG_LOGPROB_THRESHOLD,
                    verbose=None,
                )

        texts: list[str] = []
        for segment in result['segments']:
            if segment['no_speech_prob'] > NO_SPEECH_PROB_THRESHOLD and segment['avg_logprob'] < AVG_LOGPROB_THRESHOLD:
                continue
            text = segment['text'].strip()
            if text and not re_hallucination.search(text):
                texts.append(text)
        return ' '.join(texts)


transcriber: Final[WhisperTranscriber] = WhisperTranscriber(WHISPER_MODEL, WHISPER_DEVICE, WHISPER_LANGUAGE, WHISPER_BACKEND)


@dataclass
class _UserState:
    name: str
    active: bool = False
    buf: bytearray = field(default_factory=bytearray)
    preroll: bytearray = field(default_factory=bytearray)
    voiced_len: int = 0  # 最後に発話があった位置までのバイト数
    voiced_sec: float = 0.0
    last_voiced_at: float = 0.0
    last_packet_at: Optional[float] = None


@dataclass
class _Utterance:
    name: str
    pcm: bytes


class TranscribeSink(voice_recv.AudioSink):
    def __init__(self, channel: discord.abc.Messageable, loop: asyncio.AbstractEventLoop) -> None:
        super().__init__()
        self._channel = channel
        self._loop = loop
        # 文字起こし結果ごとにイベントループ上で呼ばれる(name, text)のコールバック
        self.on_text: Optional[Callable[[str, str], None]] = None
        self._lock = threading.Lock()
        self._states: dict[int, _UserState] = {}
        self._queue: queue.Queue[Optional[_Utterance]] = queue.Queue(maxsize=MAX_PENDING_UTTERANCES)
        self._closed = False
        self._stop_poller = threading.Event()
        self._poller = threading.Thread(target=self._poll_loop, name='transcribe-poller', daemon=True)
        self._worker = threading.Thread(target=self._work_loop, name='transcribe-worker', daemon=True)
        self._poller.start()
        self._worker.start()

    @property
    def channel(self) -> discord.abc.Messageable:
        return self._channel

    def wants_opus(self) -> bool:
        return False

    # ---- 受信側 ----

    def write(self, user: Optional[discord.User | discord.Member], data: voice_recv.VoiceData) -> None:
        if user is None or user.bot or not data.pcm:
            return
        self._feed(user.id, user.display_name, data.pcm, time.monotonic())

    def _feed(self, user_id: int, name: str, pcm: bytes, now: float) -> None:
        samples = np.frombuffer(pcm, dtype=np.int16)
        voiced = samples.size > 0 and float(np.sqrt(np.mean(samples.astype(np.float32) ** 2))) >= VAD_RMS_THRESHOLD

        with self._lock:
            if self._closed:
                return
            state = self._states.setdefault(user_id, _UserState(name))
            state.name = name

            if not state.active:
                if not voiced:
                    state.preroll.extend(pcm)
                    max_preroll = int(PREROLL_SEC * PCM_SAMPLE_RATE) * PCM_FRAME_BYTES
                    if len(state.preroll) > max_preroll:
                        del state.preroll[: len(state.preroll) - max_preroll]
                    return
                state.active = True
                state.buf = bytearray(state.preroll)
                state.preroll.clear()
                state.voiced_len = 0
                state.voiced_sec = 0.0
                state.last_packet_at = None
            elif state.last_packet_at is not None:
                # 発話の途切れでパケットが来なかった区間を無音で埋める
                gap = now - state.last_packet_at - len(pcm) / PCM_BYTES_PER_SEC
                if gap > 0.1:
                    state.buf.extend(bytes(int(min(gap, MAX_GAP_SEC) * PCM_SAMPLE_RATE) * PCM_FRAME_BYTES))

            state.buf.extend(pcm)
            state.last_packet_at = now
            if voiced:
                state.last_voiced_at = now
                state.voiced_len = len(state.buf)
                state.voiced_sec += len(pcm) / PCM_BYTES_PER_SEC

            if len(state.buf) / PCM_BYTES_PER_SEC >= MAX_UTTERANCE_SEC:
                self._finish_locked(state)

    def _finish_locked(self, state: _UserState) -> None:
        """発話を確定して文字起こしキューに積む。_lockを保持して呼ぶこと"""
        tail = int(TAIL_SEC * PCM_SAMPLE_RATE) * PCM_FRAME_BYTES
        pcm = bytes(state.buf[: state.voiced_len + tail])
        enough = state.voiced_sec >= MIN_VOICED_SEC
        state.active = False
        state.buf = bytearray()
        state.voiced_len = 0
        state.voiced_sec = 0.0
        state.last_packet_at = None

        if not enough:
            return
        try:
            self._queue.put_nowait(_Utterance(state.name, pcm))
        except queue.Full:
            log.warning('文字起こしが追いつかないため、%sさんの発話を破棄しました', state.name)

    def _poll(self, now: float) -> None:
        with self._lock:
            for state in self._states.values():
                if state.active and now - state.last_voiced_at >= SILENCE_SEC:
                    self._finish_locked(state)

    def _poll_loop(self) -> None:
        while not self._stop_poller.wait(POLL_INTERVAL_SEC):
            try:
                self._poll(time.monotonic())
            except Exception:
                log.exception('発話の区切り処理でエラーが発生しました')

    def cleanup(self) -> None:
        if not hasattr(self, '_lock'):
            return
        with self._lock:
            if self._closed:
                return
            self._closed = True
            for state in self._states.values():
                if state.active:
                    self._finish_locked(state)
        self._stop_poller.set()
        # 残りの発話を処理し終えてからワーカーを終了させる
        self._queue.put(None)

    # ---- 文字起こし側 ----

    def _work_loop(self) -> None:
        while True:
            utterance = self._queue.get()
            if utterance is None:
                return
            try:
                started = time.monotonic()
                text = transcriber.transcribe(utterance.pcm)
                log.info(
                    '文字起こし完了 (%s, 音声%.1f秒, 処理%.1f秒): %s',
                    utterance.name,
                    len(utterance.pcm) / PCM_BYTES_PER_SEC,
                    time.monotonic() - started,
                    text,
                )
                if text:
                    self._post(utterance.name, text)
                    callback = self.on_text
                    if callback is not None:
                        self._loop.call_soon_threadsafe(callback, utterance.name, text)
            except Exception:
                log.exception('文字起こしに失敗しました (%s)', utterance.name)

    def _post(self, name: str, text: str) -> None:
        content = f'**{discord.utils.escape_markdown(name)}**: {text}'[:1900]
        future = asyncio.run_coroutine_threadsafe(
            self._channel.send(content, allowed_mentions=discord.AllowedMentions.none()),
            self._loop,
        )
        future.add_done_callback(self._on_post_done)

    @staticmethod
    def _on_post_done(future: 'asyncio.Future[object]') -> None:
        if not future.cancelled() and future.exception() is not None:
            log.error('文字起こし結果の投稿に失敗しました (%s)', future.exception())
