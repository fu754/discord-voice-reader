from typing import Final, Union
from logging import Logger

import discord
from discord import app_commands
from discord.ext import commands

from config import STYLE_ID
from LogController import get_logger
import state
from typedef.Speaker import Speaker
from voicevox import create_wav_sound, get_style_list

logger: Final[Logger] = get_logger(__name__)


class StyleCog(commands.Cog):
    """VOICEVOXの読み上げスタイル"""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # スタイル一覧表示コマンド
    @app_commands.command(name="style_list", description="スタイルの一覧を表示する")
    async def style_list(self, interaction: discord.Interaction) -> None:
        speaker_list: Union[list[Speaker], None] = await get_style_list()
        if not speaker_list:
            logger.error(f'スタイル一覧の取得に失敗しました')
            await interaction.response.send_message('スタイル一覧の取得に失敗しました')
            return

        text: str = '## スタイル一覧\n'
        for speaker in speaker_list:
            text += f'### {speaker["name"]}\n'
            for style in speaker['styles']:
                text += f'- {style["id"]} : {style["name"]}\n'
        await interaction.response.send_message(text)
        return

    # 現在のスタイルを確認するコマンド
    @app_commands.command(name="check_style", description="現在のスタイルを確認する")
    async def check_style(self, interaction: discord.Interaction) -> None:
        text: str = f'現在のスタイル: {state.STYLE_LIST[state.current_style_id]}'
        await interaction.response.send_message(text)
        return

    async def _announce_change(self, interaction: discord.Interaction) -> None:
        """スタイル変更後、VCに参加中で再生していなければ音声で知らせる"""
        if interaction.guild.voice_client:
            if interaction.guild.voice_client.is_playing():
                pass
            else:
                text = 'スタイルを変更しました'
                is_created: bool = await create_wav_sound(state.current_style_id, text)
                if not is_created:
                    logger.error('音声ファイルの生成に失敗しました')
                    await interaction.response.send_message('音声ファイルの生成に失敗しました')
                    return
                wav_sound = discord.FFmpegPCMAudio("out.wav")
                interaction.guild.voice_client.play(wav_sound)
                logger.info(f'読み上げ済み: {text}')

    # スタイルを変更するコマンド
    @app_commands.command(name="change_style", description="スタイルを変更する")
    async def change_style(self, interaction: discord.Interaction, id: int) -> None:
        old_style: str = state.STYLE_LIST[state.current_style_id]
        state.current_style_id = int(id)
        new_style: str = state.STYLE_LIST[state.current_style_id]
        text: str = f'スタイルを変更しました: {old_style} -> {new_style}'
        await interaction.response.send_message(text)
        await self._announce_change(interaction)
        return

    # 春日部つむぎさん
    @app_commands.command(name="default_style", description="春日部つむぎさん")
    async def default_style(self, interaction: discord.Interaction) -> None:
        old_style: str = state.STYLE_LIST[state.current_style_id]
        state.current_style_id = STYLE_ID
        new_style: str = state.STYLE_LIST[state.current_style_id]
        text: str = f'スタイルを変更しました: {old_style} -> {new_style}'
        await interaction.response.send_message(text)
        await self._announce_change(interaction)
        return


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(StyleCog(bot))
