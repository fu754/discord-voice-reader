import os
import re
import asyncio
import discord
from discord import app_commands
from voicevox import create_wav_sound, get_style_list
from typedef.Speaker import Speaker
from enum import Enum, auto
from typing import Final, Union

from dotenv import load_dotenv
load_dotenv()

# envの設定
class Env(Enum):
    dev = auto()
    prod = auto()

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

# インスタンス作成
intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

# 除外する正規表現
def omit_special_word(text: str) -> str:
    re_http = re.compile(r'https?://\S+')
    text = re_http.sub(" アドレス文字列 ", text)
    re_emoji = re.compile(r'<:.*?>')
    text = re_emoji.sub(" 絵文字 ", text)
    return text

# 起動時に実行される部分
@client.event
async def on_ready() -> None:
    print(f'We have logged in as {client.user}')
    synced_cmd = await tree.sync() # スラッシュコマンドを同期する
    print(synced_cmd)
    return

# testコマンド
@tree.command(name="test", description="これはテストコマンドです。")
async def test(interaction: discord.Interaction) -> None:
    username = interaction.user.name
    await interaction.response.send_message(f'テストコマンドを実行しました (receive from: {username})', ephemeral=False) # Trueにすると実行者のみ
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
        text: str = 'ボイスチャンネルに参加しました'
        await interaction.response.send_message(text, ephemeral=False)

        # 参加時の音声生成
        is_created: bool = await create_wav_sound(STYLE_ID, text)
        if not is_created:
            await interaction.response.send_message('音声ファイルの生成に失敗しました')
            return
        wav_sound = discord.FFmpegPCMAudio("out.wav")
        await asyncio.sleep(1)
        interaction.guild.voice_client.play(wav_sound)
        print(f'読み上げ済み: {text}')
    except discord.errors.ClientException as e:
        await interaction.response.send_message('既にボイスチャンネルに参加しています。一度終了してから再実行してください。', ephemeral=False)
    except:
        await interaction.response.send_message('ボイスチャンネルへの接続に失敗しました', ephemeral=False)
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
@tree.command(name="get_list", description="スタイルの一覧を表示する")
async def get_list(interaction: discord.Interaction) -> None:
    speaker_list: Union[list[Speaker], None] = await get_style_list()
    if not speaker_list:
        await interaction.response.send_message('スタイル一覧の取得に失敗しました')
        return

    text: str = '## スタイル一覧\n'
    for speaker in speaker_list:
        text += f'### {speaker.name}\n'
        for style in speaker.styles:
            text += f'- {style["id"]} : {style["name"]}\n'
    await interaction.response.send_message(text)
    return

# 通常のメッセージ受信時
@client.event
async def on_message(message: discord.Message) -> None:
    # bot自身のメッセージは除外
    if message.author == client.user:
        pass
    # botがボイスチャットに参加しているとき
    elif message.guild.voice_client:
        if message.guild.voice_client.is_playing():
            await message.channel.send('前の音声がまだ再生中です')
            return
        text: str = message.content
        text = omit_special_word(text)

        # 音声の生成
        is_created: bool = await create_wav_sound(STYLE_ID, text)
        if not is_created:
            await message.channel.send('音声ファイルの生成に失敗しました')
            return
        wav_sound = discord.FFmpegPCMAudio("out.wav")
        message.guild.voice_client.play(wav_sound)
        print(f'読み上げ済み: {text}')
    else:
        pass
    return

# bot起動
client.run(DISCORD_BOT_TOKEN)
