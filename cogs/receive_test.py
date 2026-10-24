import asyncio
import os
import re
import time
import wave
from datetime import datetime
from logging import Logger
from threading import Lock
from typing import Final

import discord
from discord import app_commands
from discord.ext import commands, voice_recv

from helpers import prepare_listening_client, respond
from LogController import get_logger
import state

logger: Final[Logger] = get_logger(__name__)

RECORDINGS_DIR: Final[str] = 'recordings'
# discord-ext-voice-recvのPCM形式: 48kHz / 16bit / ステレオ
PCM_CHANNELS: Final[int] = 2
PCM_SAMPLE_WIDTH: Final[int] = 2
PCM_SAMPLE_RATE: Final[int] = 48000
PCM_BYTES_PER_SEC: Final[int] = PCM_CHANNELS * PCM_SAMPLE_WIDTH * PCM_SAMPLE_RATE
PCM_FRAME_SECONDS: Final[float] = 0.02
# メモリ使用量の上限としてユーザーごとの録音時間を制限する(約115MB/10分)
MAX_RECORD_SECONDS: Final[int] = 600


class ReceiveTestSink(voice_recv.AudioSink):
    def __init__(self) -> None:
        super().__init__()
        self._lock = Lock()
        self._started_at: float = time.monotonic()
        self._names: dict[int, str] = {}
        self._pcm: dict[int, bytearray] = {}
        self._packets: dict[int, int] = {}
        self.limit_reached: bool = False

    def wants_opus(self) -> bool:
        return False

    def write(self, user: discord.User | None, data: voice_recv.VoiceData) -> None:
        if user is None or not data.pcm:
            return

        offset = time.monotonic() - self._started_at
        with self._lock:
            buf = self._pcm.setdefault(user.id, bytearray())
            self._names[user.id] = user.name
            self._packets[user.id] = self._packets.get(user.id, 0) + 1

            # 無音で届かない区間を無音データで埋めて、開始からの時間軸を保つ
            gap = (offset - PCM_FRAME_SECONDS) - len(buf) / PCM_BYTES_PER_SEC
            if gap > PCM_FRAME_SECONDS * 5:
                frame_size = PCM_CHANNELS * PCM_SAMPLE_WIDTH
                buf.extend(bytes(int(gap * PCM_SAMPLE_RATE) * frame_size))

            if len(buf) / PCM_BYTES_PER_SEC >= MAX_RECORD_SECONDS:
                self.limit_reached = True
                return
            buf.extend(data.pcm)

    def cleanup(self) -> None:
        pass

    def snapshot(self) -> list[tuple[int, str, int, float]]:
        """(user_id, name, packets, seconds)のリストを返す"""
        with self._lock:
            return [
                (uid, self._names[uid], self._packets[uid], len(buf) / PCM_BYTES_PER_SEC)
                for uid, buf in self._pcm.items()
            ]

    def save_wav_files(self, directory: str) -> list[str]:
        """ユーザーごとのWAVを書き出し、作成したファイル名を返す"""
        with self._lock:
            recordings = [(uid, self._names[uid], bytes(buf)) for uid, buf in self._pcm.items()]

        os.makedirs(directory, exist_ok=True)
        paths: list[str] = []
        for uid, name, pcm in recordings:
            safe_name = re.sub(r'[^\w\-]', '_', name)[:32]
            path = os.path.join(directory, f'{safe_name}_{uid}.wav')
            with wave.open(path, 'wb') as wf:
                wf.setnchannels(PCM_CHANNELS)
                wf.setsampwidth(PCM_SAMPLE_WIDTH)
                wf.setframerate(PCM_SAMPLE_RATE)
                wf.writeframes(pcm)
            paths.append(path)
        return paths


class ReceiveTestCog(commands.Cog):
    """VC音声の受信テスト(WAV書き出し)"""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # VC音声の受信テストを開始する
    @app_commands.command(name="receive_test_start", description="VC音声の受信テストを開始する（停止時に音声をWAV保存します）")
    async def receive_test_start(self, interaction: discord.Interaction) -> None:
        voice_client = await prepare_listening_client(interaction)
        if voice_client is None:
            return
        guild = interaction.guild

        sink = ReceiveTestSink()
        state.receive_test_sinks[guild.id] = sink
        voice_client.listen(sink)
        await respond(interaction, '音声受信テストを開始しました。VCで話した後、/receive_test_stopで停止すると、受信した音声をWAVファイルとして書き出します。録音されることを参加者に伝えてください。')

    # VC音声の受信テストを終了し、ユーザーごとの受信量を表示する
    @app_commands.command(name="receive_test_stop", description="VC音声の受信テストを終了して結果を表示する")
    async def receive_test_stop(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message('このコマンドはサーバー内で実行してください', ephemeral=True)
            return

        sink = state.receive_test_sinks.pop(interaction.guild.id, None)
        voice_client = interaction.guild.voice_client
        if sink is None or not isinstance(voice_client, voice_recv.VoiceRecvClient):
            await interaction.response.send_message('実行中の音声受信テストはありません', ephemeral=True)
            return

        if voice_client.is_listening():
            voice_client.stop_listening()

        stats = sink.snapshot()
        if not stats:
            await interaction.response.send_message('音声データを受信できませんでした。VCで発話したか確認してください。', ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        directory = os.path.join(RECORDINGS_DIR, f'{datetime.now():%Y%m%d_%H%M%S}_{interaction.guild.id}')
        try:
            await asyncio.to_thread(sink.save_wav_files, directory)
        except OSError as e:
            logger.error(f'受信音声の書き出しに失敗しました ({e})')
            await interaction.followup.send('受信音声の書き出しに失敗しました', ephemeral=True)
            return
        logger.info(f'受信音声を書き出しました ({directory})')

        result = f'## 音声受信テスト結果\n保存先: `{directory}`'
        for _, name, packets, seconds in stats:
            line = f'\n- {name}: {packets} packets, {seconds:.1f} sec'
            if len(result) + len(line) > 1800:
                result += '\n※表示上限のため、以降の結果は省略しました。'
                break
            result += line
        if sink.limit_reached:
            result += f'\n※ユーザーごとの上限({MAX_RECORD_SECONDS}秒)に達したため、以降は録音していません。'
        await interaction.followup.send(result, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ReceiveTestCog(bot))
