"""複数のCogやmain.pyから使う共通関数"""
import asyncio
import re
from logging import Logger
from typing import Final, Union

import aiohttp
import discord
import emoji
from discord.ext import voice_recv

from config import LM_STUDIO_URL
from dave_receive import DaveVoiceRecvClient
from LogController import get_logger

logger: Final[Logger] = get_logger(__name__)

async def ask_lm_studio(messages: list[dict]) -> str:
    """LM Studioにメッセージ履歴を送信し、返答を受け取る非同期関数"""
    headers = {"Content-Type": "application/json"}
    payload = {
        "messages": messages, # 構築した履歴リストをそのまま渡す
        "temperature": 0.5,
        "max_tokens": 1024,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    logger.info(payload)
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(LM_STUDIO_URL, headers=headers, json=payload) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    logger.info(data)
                    return data['choices'][0]['message']['content']
                else:
                    logger.error(f"LM Studio API Error: HTTP {resp.status}")
                    return "LM Studio上の処理でエラーが発生しました。"
    except Exception as e:
        logger.error(f"LM Studio 接続エラー: {e}")
        return "LM Studioに接続できませんでした。LM Studioが起動しているか確認してください。"

# 除外する正規表現
re_http: Final[re.Pattern[str]] = re.compile(r'https?://\S+')
re_emoji: Final[re.Pattern[str]] = re.compile(r'<:.*?>')
re_animeted_emoji: Final[re.Pattern[str]] = re.compile(r'<a:.*?>')
re_reply_user_id: Final[re.Pattern[str]] = re.compile(r'<@(\d+)>')
re_here: Final[re.Pattern[str]] = re.compile(r'@here')
re_everyone: Final[re.Pattern[str]] = re.compile(r'@everyone')
def omit_special_word(text: str) -> str:
    # 特定の文字列は読み上げない
    text = re_http.sub(" ", text)
    text = re_emoji.sub(" ", text)
    text = re_animeted_emoji.sub(" ", text)
    text = re_reply_user_id.sub(" ", text)
    text = re_here.sub(" ", text)
    text = re_everyone.sub(" ", text)
    return text

def clean_text_for_voicevox(text: str) -> str:
    """AIの返答から読み上げに不要な絵文字や顔文字を除外する"""

    # 1. 絵文字（🍎、✨、🥺など）をすべて削除
    text = emoji.replace_emoji(text, replace='')

    # 2. 読み上げに不要な特殊記号を削除（正規表現）
    text = re.sub(r'[♪☆★♡♥]', '', text)

    # 3. よくある顔文字や記号のパターンを削除
    # 例: (^^), (笑), /// など
    text = re.sub(r'\(.*?\)', '', text) # カッコで囲まれたもの (笑) や (^^) などを消す（※必要なカッコも消える点に注意）
    text = text.replace('///', '')
    text = text.replace('www', '')

    # 4. 既存のURLやメンションの削除処理もここで行う
    text = re_http.sub(" ", text)
    text = re_reply_user_id.sub(" ", text)

    return text.strip()

async def respond(interaction: discord.Interaction, message: str, *, ephemeral: bool = True) -> None:
    """応答済みならfollowup、未応答ならresponseで送信する"""
    if interaction.response.is_done():
        await interaction.followup.send(message, ephemeral=ephemeral)
    else:
        await interaction.response.send_message(message, ephemeral=ephemeral)

async def prepare_listening_client(interaction: discord.Interaction) -> Union[voice_recv.VoiceRecvClient, None]:
    """
    音声受信を始められる状態のvoice_clientを返す。botが未接続なら実行者のVCに参加する。
    開始できない場合は、ユーザーへ理由を送信してNoneを返す。
    """
    if interaction.guild is None:
        await respond(interaction, 'このコマンドはサーバー内で実行してください')
        return None
    user_voice = interaction.user.voice
    if user_voice is None:
        await respond(interaction, '先にボイスチャンネルに参加してください')
        return None

    voice_client = interaction.guild.voice_client
    if voice_client is None:
        try:
            voice_client = await user_voice.channel.connect(cls=DaveVoiceRecvClient)
        except (asyncio.TimeoutError, discord.ClientException, discord.HTTPException) as e:
            logger.error(f'受信用のボイスチャンネル接続に失敗しました ({e})')
            await respond(interaction, 'ボイスチャンネルに接続できませんでした')
            return None
    elif not isinstance(voice_client, voice_recv.VoiceRecvClient):
        await respond(interaction, '現在の接続は音声受信に対応していません。/stopで退席後、もう一度実行してください')
        return None

    if voice_client.channel != user_voice.channel:
        await respond(interaction, 'botと同じボイスチャンネルに参加してください')
        return None
    if voice_client.is_listening():
        await respond(interaction, '音声受信テストまたは文字起こしがすでに実行中です')
        return None
    return voice_client
