"""discord-ext-voice-recv に DAVE (音声E2EE) の復号を追加する。

拡張本体はトランスポート暗号の復号までしか行わず、DAVEで暗号化されたままの
データをOpusデコーダーに渡して `OpusError: corrupted stream` になる。
ここでは拡張本体を変更せず、サブクラスで復号を差し込む。

使い方: `channel.connect(cls=DaveVoiceRecvClient)`
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Final, Optional

import discord
import davey
from discord.ext import voice_recv
from discord.ext.voice_recv.reader import AudioReader, PacketDecryptor
from discord.ext.voice_recv.rtp import OPUS_SILENCE

if TYPE_CHECKING:
    from discord.ext.voice_recv.rtp import RTPPacket
    from discord.ext.voice_recv.reader import AfterCB

log = logging.getLogger(__name__)

__all__ = [
    'DaveVoiceRecvClient',
]

# DAVEのフレーム末尾に付くマーカー。平文のOpusとの判別に使う
DAVE_MAGIC_MARKER: Final[bytes] = b'\xfa\xfa'


class DaveDecryptor:
    """PacketDecryptorをラップし、RTPペイロードにDAVE復号を追加する。"""

    def __init__(self, inner: PacketDecryptor, voice_client: voice_recv.VoiceRecvClient) -> None:
        self._inner: PacketDecryptor = inner
        self._voice_client: voice_recv.VoiceRecvClient = voice_client
        self._drop_counts: dict[int, int] = {}

    def __getattr__(self, name: str) -> Any:
        # decrypt_rtcp / update_secret_key などは元の実装へ委譲する
        return getattr(self._inner, name)

    def decrypt_rtp(self, packet: RTPPacket) -> bytes:
        payload: bytes = self._inner.decrypt_rtp(packet)

        # 無音フレームはDAVEの対象外で、常に平文で届く
        if payload == OPUS_SILENCE:
            return payload

        connection = self._voice_client._connection
        session: Optional[davey.DaveSession] = connection.dave_session
        if connection.dave_protocol_version == 0 or session is None:
            return payload

        user_id = self._voice_client._get_id_from_ssrc(packet.ssrc)
        if user_id is None:
            return self._drop(packet.ssrc, 'ssrcに対応するユーザーが未解決')

        if not payload.endswith(DAVE_MAGIC_MARKER):
            # マーカーが無い = 平文。移行中などパススルーが許可されている間だけ通す
            if not session.ready or session.can_passthrough(user_id):
                return payload
            return self._drop(packet.ssrc, '暗号化されていないフレームがパススルー無効の状態で到着')

        if not session.ready:
            return self._drop(packet.ssrc, 'DAVEセッションが未確立')

        try:
            return session.decrypt(user_id, davey.MediaType.audio, payload)
        except Exception as e:
            return self._drop(packet.ssrc, f'DAVE復号に失敗 ({e})')

    def _drop(self, ssrc: int, reason: str) -> bytes:
        """復号できないフレームは破棄する。無音フレームを返して後段のデコードエラーを避ける。"""
        count = self._drop_counts.get(ssrc, 0) + 1
        self._drop_counts[ssrc] = count
        # ログが溢れないよう最初の1回と以降100回ごとにだけ出力する
        if count == 1 or count % 100 == 0:
            log.warning('音声フレームを破棄しました (ssrc=%s, 累計%s件): %s', ssrc, count, reason)
        return OPUS_SILENCE


class DaveAudioReader(AudioReader):
    def __init__(
        self,
        sink: voice_recv.AudioSink,
        voice_client: voice_recv.VoiceRecvClient,
        *,
        after: Optional[AfterCB] = None,
    ) -> None:
        super().__init__(sink, voice_client, after=after)
        # start()前に差し替えるので、DAVE復号を経由しないパケットは発生しない
        self.decryptor = DaveDecryptor(self.decryptor, voice_client)  # type: ignore[assignment]


class DaveVoiceRecvClient(voice_recv.VoiceRecvClient):
    """DAVE復号に対応したVoiceRecvClient。"""

    def listen(self, sink: voice_recv.AudioSink, *, after: Optional[AfterCB] = None) -> None:
        # 親のlisten()はAudioReaderを直接生成するため、同じ手順でDaveAudioReaderに置き換える
        if not self.is_connected():
            raise discord.ClientException('Not connected to voice.')
        if not isinstance(sink, voice_recv.AudioSink):
            raise TypeError(f'sink must be an AudioSink not {sink.__class__.__name__}')
        if self.is_listening():
            raise discord.ClientException('Already receiving audio.')

        self._reader = DaveAudioReader(sink, self, after=after)
        self._reader.start()
