import platform
import asyncio
from collections import deque
from logging import Logger
from typing import Final, Union

import discord
from discord.ext import commands

from config import DISCORD_BOT_TOKEN, MAX_HISTORY_LENGTH, SYSTEM_PROMPT
from helpers import ask_lm_studio, clean_text_for_voicevox, omit_special_word
from LogController import get_logger
import state
from typedef.Speaker import Speaker
from voicevox import create_wav_sound, get_style_list

logger: Final[Logger] = get_logger(__name__)

# 読み込むコマンド群(cogs/以下のモジュール)
EXTENSIONS: Final[tuple[str, ...]] = (
    'cogs.voice',
    'cogs.style',
    'cogs.chat_history',
    # 'cogs.receive_test',
    'cogs.transcribe',
)


class VoiceReaderBot(commands.Bot):
    async def setup_hook(self) -> None:
        for extension in EXTENSIONS:
            await self.load_extension(extension)

# インスタンス作成
intents = discord.Intents.default()
intents.message_content = True
# スラッシュコマンドのみ使うため、プレフィックスコマンドはbotへのメンションのみとする
client = VoiceReaderBot(command_prefix=commands.when_mentioned, intents=intents)
tree = client.tree

# 起動時に実行される部分
@client.event
async def on_ready() -> None:
    # style一覧のリストを作成
    speaker_list: Union[list[Speaker], None] = await get_style_list()
    if not speaker_list:
        logger.error('speaker_listの取得に失敗しました。プログラムを終了します。')
        exit()
    for speaker in speaker_list:
        for style in speaker['styles']:
            style_name = f'{speaker["name"]} ({style["name"]})'
            state.STYLE_LIST[int(style['id'])] = style_name
    logger.info(f'スタイル一覧: {state.STYLE_LIST}')

    # スラッシュコマンドを同期する
    synced_cmd = await tree.sync()
    logger.info(f'コマンドを同期しました ({synced_cmd})')
    logger.info('システムを起動しました')
    return

# 通常のメッセージ受信時
@client.event
async def on_message(message: discord.Message) -> None:
    # ① bot自身のメッセージは無視
    if message.author == client.user:
        return

    # ② AIとの会話かどうかの判定（メンション、またはbotへのリプライ）
    is_reply_to_bot = False
    if message.reference and message.reference.resolved:
        if message.reference.resolved.author == client.user:
            is_reply_to_bot = True

    # botへのメンションが含まれているか、botへのリプライである場合
    if client.user in message.mentions or is_reply_to_bot:
        
        # メンション文字列（@bot名）を削除して本文を抽出
        clean_content = message.clean_content.replace(f'@{client.user.name}', '').strip()
        clean_content = omit_special_word(clean_content)
        logger.info(f"LM Studio送信前文字列: {clean_content}")

        if not clean_content:
            await message.channel.send('何かご用でしょうか？')
            return

        # --- ここから会話履歴の処理とLM Studioへの問い合わせ ---
        channel_id = message.channel.id
        if channel_id not in state.chat_histories:
            state.chat_histories[channel_id] = deque(maxlen=MAX_HISTORY_LENGTH)
        
        state.chat_histories[channel_id].append({"role": "user", "content": clean_content})
        system_prompt_dict = {"role": "system", "content": SYSTEM_PROMPT}
        api_messages = [system_prompt_dict] + list(state.chat_histories[channel_id])

        async with message.channel.typing():
            ai_response: str = await ask_lm_studio(api_messages)
        
        state.chat_histories[channel_id].append({"role": "assistant", "content": ai_response})
        text = clean_text_for_voicevox(ai_response)
        await message.reply(text)
        # --------------------------------------------------

        # ③ ボイスチャットに参加している場合はAIの返答「だけ」を読み上げる
        if message.guild.voice_client:
            while message.guild.voice_client.is_playing():
                await asyncio.sleep(1)

            is_created: bool = await create_wav_sound(state.current_style_id, text)
            if not is_created:
                logger.error('AI返答の音声ファイルの生成に失敗しました')
                return
            
            wav_sound = discord.FFmpegPCMAudio("out.wav")
            message.guild.voice_client.play(wav_sound)
            logger.info(f'AI返答読み上げ済み: {text}')
        
        return 

    # ④ メンションやリプライ以外の「通常のユーザーメッセージ」の読み上げ処理
    if message.guild.voice_client:
        # 再生中の場合は、終わるまで1秒ずつ待機する
        while message.guild.voice_client.is_playing():
            await asyncio.sleep(1)
        
        text: str = message.content
        text = omit_special_word(text)

        is_created: bool = await create_wav_sound(state.current_style_id, text)
        if not is_created:
            logger.error('音声ファイルの生成に失敗しました')
            await message.channel.send('音声ファイルの生成に失敗しました')
            return
        wav_sound = discord.FFmpegPCMAudio("out.wav")
        message.guild.voice_client.play(wav_sound)
        logger.info(f'読み上げ済み: {text}')
    return

# bot起動
if __name__ == '__main__':
    if platform.system() == 'Darwin':
        if not discord.opus.is_loaded():
            # Apple Silicon Mac (M1/M2/M3/M4) のHomebrewの標準パス
            import os
            if os.path.exists('/opt/homebrew/lib/libopus.dylib'):
                discord.opus.load_opus('/opt/homebrew/lib/libopus.dylib')
                logger.info("macOS (Apple Silicon) 用の Opus ライブラリをロードしました")
            # Intel Mac のHomebrewの標準パス
            elif os.path.exists('/usr/local/lib/libopus.dylib'):
                discord.opus.load_opus('/usr/local/lib/libopus.dylib')
                logger.info("macOS (Intel) 用の Opus ライブラリをロードしました")
    # loggerを設定しているのでdiscord.clientのロガーは無効化する
    client.run(DISCORD_BOT_TOKEN, log_handler=None)
