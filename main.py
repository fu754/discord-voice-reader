import os
import platform
import re
import asyncio
import aiohttp
import emoji
import discord
from discord import app_commands
from voicevox import create_wav_sound, get_style_list
from LogController import get_logger
from logging import Logger
from typedef.Speaker import Speaker
from typedef.General import Env
from typing import Final, Union
from dotenv import load_dotenv
from collections import deque
load_dotenv()

logger: Final[Logger] = get_logger(__name__)

# envの設定
_env: Env
if os.environ.get('ENV') == 'prod':
    _env = Env.prod
elif os.environ.get('ENV') == 'dev':
    _env = Env.dev
else:
    raise ValueError('ENV is invalid value (set prod or dev)')
ENV: Final[Env] = _env

# トークンの取得
DISCORD_BOT_TOKEN: Final[str] =os.environ.get('DISCORD_BOT_TOKEN')

# デフォルトのスタイルIDの設定
STYLE_ID: Final[int] = int(os.environ.get('DEFAULT_STYLE_ID'))
STYLE_LIST: dict = {}
current_style_id: int = STYLE_ID

# 会話履歴の最大保持数（1往復 = userとassistantで2つ。5往復なら10）
MAX_HISTORY_LENGTH: Final[int] = 15
# チャンネルごとの会話履歴を保存する辞書 { channel_id : deque }
chat_histories: dict[int, deque] = {}

SYSTEM_PROMPT: Final[str] = (
    "あなたはDiscordサーバーの優秀なアシスタントAIであり、名前は楽園ちゃん(アカウントIDはRakuenVoiceReader)です。直前の会話の文脈を踏まえて、日本語で短く簡潔に返答してください。"
    "キャラの性格として、アニメに出てくるようなかわいい女の子で、オタクに優しいギャルを演じてください。一人称は「あたし」で敬語は使わないでください。"
    "【重要】あなたからの返信は音声合成ソフトで読み上げられます。顔文字（(^^)、m(_ _)mなど）や絵文字（😊、✨など）は絶対に使用しないでください。"
    "出力はプレーンな日本語のテキストと、基本的な句読点のみにしてください。"
)

_lmstudio_url: str
if ENV == Env.prod:
    _lmstudio_url = 'http://host.docker.internal:1234/v1/chat/completions'
elif ENV == Env.dev:
    _lmstudio_url = 'http://127.0.0.1:1234/v1/chat/completions'
else:
    _lmstudio_url = 'http://127.0.0.1:1234/v1/chat/completions'
LM_STUDIO_URL: Final[str] = _lmstudio_url
async def ask_lm_studio(messages: list[dict]) -> str:
    """LM Studioにメッセージ履歴を送信し、返答を受け取る非同期関数"""
    headers = {"Content-Type": "application/json"}
    payload = {
        "messages": messages, # 構築した履歴リストをそのまま渡す
        "temperature": 0.5,
        "max_tokens": 1024,
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

# インスタンス作成
intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

# 除外する正規表現
re_http: Final[re.Pattern[str]] = re.compile(r'https?://\S+')
re_emoji: Final[re.Pattern[str]] = re.compile(r'<:.*?>')
re_animeted_emoji: Final[re.Pattern[str]] = re.compile(r'<a:.*?>')
re_reply_user_id: Final[re.Pattern[str]] = re.compile(r'<@(\d+)>')
re_here: Final[re.Pattern[str]] = re.compile(r'@here')
re_everyone: Final[re.Pattern[str]] = re.compile(r'@everyone')
def omit_special_word(text: str) -> str:
    # 特定の文字列は読み上げない
    # text = re_http.sub(" アドレス文字列 ", text)
    # text = re_emoji.sub(" 絵文字 ", text)
    # text = re_animeted_emoji.sub(" 絵文字 ", text)
    # text = re_reply_user_id.sub(" リプライ ", text)
    # text = re_here.sub(" アットヒアー ", text)
    # text = re_everyone.sub(" アットエブリワン ", text)
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
            STYLE_LIST[int(style['id'])] = style_name
    logger.info(f'スタイル一覧: {STYLE_LIST}')

    # スラッシュコマンドを同期する
    synced_cmd = await tree.sync()
    logger.info(f'コマンドを同期しました ({synced_cmd})')
    logger.info('システムを起動しました')
    return

# testコマンド
@tree.command(name="ping", description="サーバーが応答を返すか確認用")
async def test(interaction: discord.Interaction) -> None:
    await interaction.response.send_message('pingコマンドの受信に成功しました', ephemeral=False) # Trueにすると実行者のみ
    return

# 開始コマンド
@tree.command(name="start", description="botをVCに参加させ音声読み上げを開始する")
async def system_start(interaction: discord.Interaction) -> None:
    if not interaction.user.voice:
        await interaction.response.send_message('ボイスチャンネルに参加していないユーザーからコマンドが実行されました', ephemeral=False)
        return
    vc = interaction.user.voice.channel

    try:
        await vc.connect()
        text: str = f'ボイスチャンネルに参加しました [現在のスタイル: {STYLE_LIST[current_style_id]}]'
        speak_text: str = 'ボイスチャンネルに参加しました'
        
        # 【1回目のレスポンス】
        await interaction.response.send_message(text, ephemeral=False)

        # 参加時の音声生成
        is_created: bool = await create_wav_sound(current_style_id, speak_text)
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
        # 【修正】既にレスポンス済みかを判定して送信メソッドを変える
        if interaction.response.is_done():
            await interaction.followup.send('ボイスチャンネルへの接続または音声再生に失敗しました')
        else:
            await interaction.response.send_message('ボイスチャンネルへの接続または音声再生に失敗しました', ephemeral=False)
    return

# 終了コマンド
@tree.command(name="stop", description="botをVCから退席させ音声読み上げを終了する")
async def system_stop(interaction: discord.Interaction) -> None:
    if not interaction.guild.voice_client:
        await interaction.response.send_message('botがボイスチャンネルに参加していません', ephemeral=False)
        return
    await interaction.guild.voice_client.disconnect()
    await interaction.response.send_message('退席しました', ephemeral=False)
    return

# スタイル一覧表示コマンド
@tree.command(name="style_list", description="スタイルの一覧を表示する")
async def style_list(interaction: discord.Interaction) -> None:
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
@tree.command(name="check_style", description="現在のスタイルを確認する")
async def check_style(interaction: discord.Interaction) -> None:
    text: str = f'現在のスタイル: {STYLE_LIST[current_style_id]}'
    await interaction.response.send_message(text)
    return

# スタイルを変更するコマンド
@tree.command(name="change_style", description="スタイルを変更する")
async def change_style(interaction: discord.Interaction, id: int) -> None:
    global current_style_id
    text: str = f'現在のスタイル: {STYLE_LIST[current_style_id]}'
    old_style: str = STYLE_LIST[current_style_id]
    current_style_id = int(id)
    new_style: str = STYLE_LIST[current_style_id]
    text: str = f'スタイルを変更しました: {old_style} -> {new_style}'
    await interaction.response.send_message(text)

    if interaction.guild.voice_client:
        if interaction.guild.voice_client.is_playing():
            pass
        else:
            text = 'スタイルを変更しました'
            is_created: bool = await create_wav_sound(current_style_id, text)
            if not is_created:
                logger.error('音声ファイルの生成に失敗しました')
                await interaction.response.send_message('音声ファイルの生成に失敗しました')
                return
            wav_sound = discord.FFmpegPCMAudio("out.wav")
            interaction.guild.voice_client.play(wav_sound)
            logger.info(f'読み上げ済み: {text}')
    return

# 春日部つむぎさん
@tree.command(name="default_style", description="春日部つむぎさん")
async def default_style(interaction: discord.Interaction) -> None:
    global current_style_id
    text: str = f'現在のスタイル: {STYLE_LIST[current_style_id]}'
    old_style: str = STYLE_LIST[current_style_id]
    current_style_id = STYLE_ID
    new_style: str = STYLE_LIST[current_style_id]
    text: str = f'スタイルを変更しました: {old_style} -> {new_style}'
    await interaction.response.send_message(text)

    if interaction.guild.voice_client:
        if interaction.guild.voice_client.is_playing():
            pass
        else:
            text = 'スタイルを変更しました'
            is_created: bool = await create_wav_sound(current_style_id, text)
            if not is_created:
                logger.error('音声ファイルの生成に失敗しました')
                await interaction.response.send_message('音声ファイルの生成に失敗しました')
                return
            wav_sound = discord.FFmpegPCMAudio("out.wav")
            interaction.guild.voice_client.play(wav_sound)
            logger.info(f'読み上げ済み: {text}')
    return

# チャットの履歴を削除する
@tree.command(name="clear_chat_history", description="楽園ちゃんのチャット履歴のキャッシュクリアを行う")
async def clear_chat_history(interaction: discord.Interaction) -> None:
    channel_id = interaction.channel.id

    # そのチャンネルの履歴が存在するかチェック
    if channel_id in chat_histories:
        # 履歴を削除して初期化
        del chat_histories[channel_id]
        await interaction.response.send_message('このチャンネルの会話の記憶をリセットしました！また新しい話題でお話ししましょう。', ephemeral=False)
        logger.info(f'チャンネル({channel_id})のチャット履歴をクリアしました')
    else:
        await interaction.response.send_message('このチャンネルの会話の記憶をリセットしました！また新しい話題でお話ししましょう。', ephemeral=False)
        logger.info(f'チャンネル({channel_id})のチャット履歴をクリアしました')
        # そもそも履歴がない場合
        # await interaction.response.send_message('このチャンネルにはまだ私の記憶がありません！', ephemeral=False)
    return

# チャットの履歴を表示する
@tree.command(name="check_chat_history", description="楽園ちゃんにキャッシュされているチャット履歴を表示する")
async def check_chat_history(interaction: discord.Interaction) -> None:
    channel_id = interaction.channel.id

    # そのチャンネルの履歴が存在するかチェック
    if channel_id not in chat_histories or not chat_histories[channel_id]:
        await interaction.response.send_message('現在、このチャンネルにキャッシュされているチャット履歴はありません', ephemeral=False)
        return

    text: str = "## 📝 現在のチャット履歴キャッシュ\n"
    history = chat_histories[channel_id]

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
        if channel_id not in chat_histories:
            chat_histories[channel_id] = deque(maxlen=MAX_HISTORY_LENGTH)
        
        chat_histories[channel_id].append({"role": "user", "content": clean_content})
        system_prompt_dict = {"role": "system", "content": SYSTEM_PROMPT}
        api_messages = [system_prompt_dict] + list(chat_histories[channel_id])

        async with message.channel.typing():
            ai_response: str = await ask_lm_studio(api_messages)
        
        chat_histories[channel_id].append({"role": "assistant", "content": ai_response})
        text = clean_text_for_voicevox(ai_response)
        await message.reply(text)
        # --------------------------------------------------

        # ③ ボイスチャットに参加している場合はAIの返答「だけ」を読み上げる
        if message.guild.voice_client:
            while message.guild.voice_client.is_playing():
                await asyncio.sleep(1)

            is_created: bool = await create_wav_sound(current_style_id, text)
            if not is_created:
                logger.error('AI返答の音声ファイルの生成に失敗しました')
                return
            
            wav_sound = discord.FFmpegPCMAudio("out.wav")
            message.guild.voice_client.play(wav_sound)
            logger.info(f'AI返答読み上げ済み: {text}')
        
        return 

    # ④ メンションやリプライ以外の「通常のユーザーメッセージ」の読み上げ処理
    if message.guild.voice_client:
        # 【変更】再生中の場合は、終わるまで1秒ずつ待機する
        while message.guild.voice_client.is_playing():
            await asyncio.sleep(1)
        
        text: str = message.content
        text = omit_special_word(text)

        is_created: bool = await create_wav_sound(current_style_id, text)
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
            import os
            # Apple Silicon Mac (M1/M2/M3/M4) のHomebrewの標準パス
            if os.path.exists('/opt/homebrew/lib/libopus.dylib'):
                discord.opus.load_opus('/opt/homebrew/lib/libopus.dylib')
                logger.info("macOS (Apple Silicon) 用の Opus ライブラリをロードしました")
            # Intel Mac のHomebrewの標準パス
            elif os.path.exists('/usr/local/lib/libopus.dylib'):
                discord.opus.load_opus('/usr/local/lib/libopus.dylib')
                logger.info("macOS (Intel) 用の Opus ライブラリをロードしました")
    # loggerを設定しているのでdiscord.clientのロガーは無効化する
    client.run(DISCORD_BOT_TOKEN, log_handler=None)
