import asyncio
from logging import Logger
from typing import Final

import discord
from discord import app_commands
from discord.ext import commands, voice_recv

from config import LM_STUDIO_URL
from helpers import prepare_listening_client, respond
from LogController import get_logger
import state
from speech_judge import SpeechJudge
from voice_transcribe import TranscribeSink, transcriber

logger: Final[Logger] = get_logger(__name__)


class TranscribeCog(commands.Cog):
    """VCの文字起こし(Whisper)と、発話の判定(LM Studio)"""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # VC音声の文字起こしを開始する
    @app_commands.command(name="transcribe_start", description="VCの発話をローカルのWhisperで文字起こしし、このチャンネルに投稿する")
    async def transcribe_start(self, interaction: discord.Interaction) -> None:
        # モデルの読み込みやVC接続に3秒以上かかることがあるため、先に応答を保留する
        await interaction.response.defer()
        voice_client = await prepare_listening_client(interaction)
        if voice_client is None:
            return

        try:
            await asyncio.to_thread(transcriber.load)
        except Exception as e:
            logger.error(f'Whisperモデルの読み込みに失敗しました ({e})')
            await respond(interaction, 'Whisperモデルの読み込みに失敗しました')
            return

        sink = TranscribeSink(interaction.channel, asyncio.get_running_loop())
        state.transcribe_sinks[interaction.guild.id] = sink
        voice_client.listen(sink)
        await respond(
            interaction,
            'VCの文字起こしを開始しました。発話はこのチャンネルに投稿されます。音声は保存しません。参加者の発話がテキスト化されることにご注意ください。終了は `/transcribe_stop` です。',
            ephemeral=False,
        )

    # 文字起こし結果の判定を開始する
    @app_commands.command(name="judge_start", description="文字起こしした発話をLM Studioで採点する（要: /transcribe_start）")
    async def judge_start(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message('このコマンドはサーバー内で実行してください', ephemeral=True)
            return
        sink = state.transcribe_sinks.get(interaction.guild.id)
        if sink is None:
            await interaction.response.send_message('先に `/transcribe_start` で文字起こしを開始してください', ephemeral=True)
            return
        if interaction.guild.id in state.speech_judges:
            await interaction.response.send_message('すでに判定中です', ephemeral=True)
            return

        judge = SpeechJudge(LM_STUDIO_URL, interaction.channel)
        state.speech_judges[interaction.guild.id] = judge
        sink.on_text = judge.submit
        await interaction.response.send_message(
            '発話の判定を開始しました。文字起こしされた発話はLM Studioに渡され、社会通念やポリティカルコレクトネスの観点で問題度(0〜10)が採点され、このチャンネルに投稿されます。終了は `/judge_stop` です。',
            ephemeral=False,
        )

    # 文字起こし結果の判定を終了する
    @app_commands.command(name="judge_stop", description="発話の採点を終了する（文字起こしは継続）")
    async def judge_stop(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message('このコマンドはサーバー内で実行してください', ephemeral=True)
            return
        if not state.stop_speech_judge(interaction.guild.id):
            await interaction.response.send_message('実行中の判定はありません', ephemeral=True)
            return
        await interaction.response.send_message('発話の判定を終了しました。文字起こしは継続しています。', ephemeral=False)

    # VC音声の文字起こしを終了する
    @app_commands.command(name="transcribe_stop", description="VCの文字起こしを終了する")
    async def transcribe_stop(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message('このコマンドはサーバー内で実行してください', ephemeral=True)
            return

        sink = state.transcribe_sinks.pop(interaction.guild.id, None)
        state.stop_speech_judge(interaction.guild.id)
        voice_client = interaction.guild.voice_client
        if sink is None or not isinstance(voice_client, voice_recv.VoiceRecvClient):
            await interaction.response.send_message('実行中の文字起こしはありません', ephemeral=True)
            return

        if voice_client.is_listening():
            voice_client.stop_listening()
        await interaction.response.send_message('文字起こしを終了しました。処理中の発話は、完了次第投稿されます。', ephemeral=False)

    async def stop_transcription_on_leave(self, guild: discord.Guild, reason: str) -> None:
        """VC切断などで文字起こしを止め、開始したチャンネルへ通知する"""
        sink = state.transcribe_sinks.pop(guild.id, None)
        state.stop_speech_judge(guild.id)
        if sink is None:
            return
        voice_client = guild.voice_client
        if isinstance(voice_client, voice_recv.VoiceRecvClient) and voice_client.is_listening():
            voice_client.stop_listening()
        sink.cleanup()  # 切断済みでstop_listeningが呼ばれない場合に備える(冪等)
        logger.info(f'文字起こしを終了しました ({reason})')
        try:
            await sink.channel.send(f'{reason}ため、文字起こしを終了しました。処理中の発話は、完了次第投稿されます。')
        except discord.HTTPException as e:
            logger.warning(f'文字起こし終了の通知に失敗しました ({e})')

    # VCの状態変化を監視し、botの切断・VCから人がいなくなった場合に文字起こしと受信テストを止める
    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState) -> None:
        guild = member.guild
        if member == self.bot.user:
            if before.channel is not None and after.channel is None:
                state.receive_test_sinks.pop(guild.id, None)
                await self.stop_transcription_on_leave(guild, 'botがVCから切断された')
            return

        if guild.id not in state.transcribe_sinks:
            return
        voice_client = guild.voice_client
        if voice_client is None or before.channel != voice_client.channel:
            return
        if any(not m.bot for m in voice_client.channel.members):
            return
        await self.stop_transcription_on_leave(guild, 'VCに参加者がいなくなった')


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(TranscribeCog(bot))
