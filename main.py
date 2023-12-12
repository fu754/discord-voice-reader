import os
import discord
from discord import app_commands
from discord.ext import commands
from voicevox import create_wav_sound
from typing import Final

from dotenv import load_dotenv
load_dotenv()

DISCORD_BOT_TOKEN: Final[str] =os.environ.get('DISCORD_BOT_TOKEN')
intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

# 起動時に実行される
@client.event
async def on_ready() -> None:
    print(f'We have logged in as {client.user}')
    synced_cmd = await tree.sync() # スラッシュコマンドを同期する
    print(synced_cmd)

# testコマンド
@tree.command(name="test",description="これはテストコマンドです。")
async def test(interaction: discord.Interaction) -> None:
    username = interaction.user.name
    await interaction.response.send_message(f'テストコマンドを実行しました (receive from: {username})', ephemeral=False) # Trueにすると実行者のみ

@tree.command(name="start",description="botをVCに参加させ音声読み上げを開始する")
async def system_start(interaction: discord.Interaction) -> None:
    if not interaction.user.voice:
        await interaction.response.send_message('ボイスチャンネルに参加していないユーザーからコマンドが実行されました', ephemeral=False)
        return
    vc = interaction.user.voice.channel
    try:
        await vc.connect()
        await interaction.response.send_message('ボイスチャンネルに参加しました', ephemeral=False)
    except discord.errors.ClientException as e:
        await interaction.response.send_message('既にボイスチャンネルに参加しています。一度終了してから再実行してください。', ephemeral=False)
    except:
        await interaction.response.send_message('ボイスチャンネルへの接続に失敗しました', ephemeral=False)

@tree.command(name="stop",description="botをVCから退席させ音声読み上げを終了する")
async def system_stop(interaction: discord.Interaction) -> None:
    if not interaction.guild.voice_client:
        await interaction.response.send_message('botがボイスチャンネルに参加していません', ephemeral=False)
        return
    await interaction.guild.voice_client.disconnect()
    await interaction.response.send_message('退席しました', ephemeral=False)

@client.event
async def on_message(message) -> None:
    if message.author == client.user:
        pass

    elif message.content.startswith('hello'):
        await message.channel.send('Hello!')

    elif message.content.startswith('$system'):
        pass

    elif message.guild.voice_client:
        if message.guild.voice_client.is_playing():
            await message.channel.send('前の音声がまだ再生中です')
            return
        is_created = create_wav_sound(message.content)
        if not is_created:
            await message.channel.send('音声ファイルの生成に失敗しました')
            return
        wav_sound = discord.FFmpegPCMAudio("out.wav")
        message.guild.voice_client.play(wav_sound)
    else:
        pass

client.run(DISCORD_BOT_TOKEN)
