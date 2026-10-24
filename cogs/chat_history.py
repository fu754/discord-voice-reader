from typing import Final
from logging import Logger

import discord
from discord import app_commands
from discord.ext import commands

from LogController import get_logger
import state

logger: Final[Logger] = get_logger(__name__)


class ChatHistoryCog(commands.Cog):
    """LM Studioとの会話履歴の管理"""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # チャットの履歴を削除する
    @app_commands.command(name="clear_chat_history", description="楽園ちゃんのチャット履歴のキャッシュクリアを行う")
    async def clear_chat_history(self, interaction: discord.Interaction) -> None:
        channel_id = interaction.channel.id

        # 履歴が存在すれば削除して初期化する(なくても同じ応答を返す)
        state.chat_histories.pop(channel_id, None)
        await interaction.response.send_message('このチャンネルの会話の記憶をリセットしました！また新しい話題でお話ししましょう。', ephemeral=False)
        logger.info(f'チャンネル({channel_id})のチャット履歴をクリアしました')
        return

    # チャットの履歴を表示する
    @app_commands.command(name="check_chat_history", description="楽園ちゃんにキャッシュされているチャット履歴を表示する")
    async def check_chat_history(self, interaction: discord.Interaction) -> None:
        channel_id = interaction.channel.id

        # そのチャンネルの履歴が存在するかチェック
        if channel_id not in state.chat_histories or not state.chat_histories[channel_id]:
            await interaction.response.send_message('現在、このチャンネルにキャッシュされているチャット履歴はありません', ephemeral=False)
            return

        text: str = "## 📝 現在のチャット履歴キャッシュ\n"
        history = state.chat_histories[channel_id]

        for i, msg in enumerate(history, 1):
            # role（役割）を分かりやすく変換
            role_name = "🗣️ ユーザー" if msg["role"] == "user" else "🌸 楽園ちゃん"
            content = msg["content"]

            # 1発言が長すぎる場合は表示用に少し省略する（必要に応じて変更してください）
            if len(content) > 150:
                content = content[:150] + "..."

            line_text = f"**{i}. {role_name}**\n{content}\n\n"

            # Discordの2000文字制限に引っかからないように安全対策
            if len(text) + len(line_text) > 1900:
                text += "※文字数制限のため、以降の表示は省略されています。\n"
                break

            text += line_text

        await interaction.response.send_message(text, ephemeral=True)
        return


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ChatHistoryCog(bot))
