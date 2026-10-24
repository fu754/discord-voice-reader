import asyncio
from typing import Final
from logging import Logger

import discord
from discord import app_commands
from discord.ext import commands, voice_recv

from LogController import get_logger
import state
from voicevox import create_wav_sound

logger: Final[Logger] = get_logger(__name__)


class VoiceCog(commands.Cog):
    """botのVC参加・退席と動作確認"""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # testコマンド
    @app_commands.command(name="ping", description="サーバーが応答を返すか確認用")
    async def test(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message('pingコマンドの受信に成功しました', ephemeral=False) # Trueにすると実行者のみ
        return

    # 開始コマンド
    @app_commands.command(name="start", description="botをVCに参加させ音声読み上げを開始する")
    async def system_start(self, interaction: discord.Interaction) -> None:
        if not interaction.user.voice:
            await interaction.response.send_message('ボイスチャンネルに参加していないユーザーからコマンドが実行されました', ephemeral=False)
            return
        vc = interaction.user.voice.channel

        try:
            await vc.connect()
            text: str = f'ボイスチャンネルに参加しました [現在のスタイル: {state.STYLE_LIST[state.current_style_id]}]'
            speak_text: str = 'ボイスチャンネルに参加しました'

            # 【1回目のレスポンス】
            await interaction.response.send_message(text, ephemeral=False)

            # 参加時の音声生成
            is_created: bool = await create_wav_sound(state.current_style_id, speak_text)
            if not is_created:
                # 既にレスポンス済みなので、followup.send を使う
                await interaction.followup.send('音声ファイルの生成に失敗しました')
                return

            wav_sound = discord.FFmpegPCMAudio("out.wav")
            await asyncio.sleep(1)
            interaction.guild.voice_client.play(wav_sound)
            logger.info(f'読み上げ済み「{speak_text}」')

        except discord.errors.ClientException as e:
            logger.error(f'ボイスチャンネル重複参加エラー ({e})')
            if interaction.response.is_done():
                await interaction.followup.send('既にボイスチャンネルに参加しています。一度終了してから再実行してください。')
            else:
                await interaction.response.send_message('既にボイスチャンネルに参加しています。一度終了してから再実行してください。')

        except Exception as e:
            logger.error(f'ボイスチャンネル参加時の例外エラー ({e})')
            # 既にレスポンス済みかを判定して送信メソッドを変える
            if interaction.response.is_done():
                await interaction.followup.send('ボイスチャンネルへの接続または音声再生に失敗しました')
            else:
                await interaction.response.send_message('ボイスチャンネルへの接続または音声再生に失敗しました', ephemeral=False)
        return

    # 終了コマンド
    @app_commands.command(name="stop", description="botをVCから退席させ音声読み上げを終了する")
    async def system_stop(self, interaction: discord.Interaction) -> None:
        if not interaction.guild.voice_client:
            await interaction.response.send_message('botがボイスチャンネルに参加していません', ephemeral=False)
            return
        voice_client = interaction.guild.voice_client
        if isinstance(voice_client, voice_recv.VoiceRecvClient) and voice_client.is_listening():
            voice_client.stop_listening()
        state.receive_test_sinks.pop(interaction.guild.id, None)
        state.transcribe_sinks.pop(interaction.guild.id, None)
        state.stop_speech_judge(interaction.guild.id)
        await voice_client.disconnect()
        await interaction.response.send_message('退席しました', ephemeral=False)
        return


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(VoiceCog(bot))
