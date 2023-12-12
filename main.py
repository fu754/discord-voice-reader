import os
import discord
from discord.ext import commands
from voicevox import create_wav_sound

from typing import Final

from dotenv import load_dotenv
load_dotenv()

DISCORD_BOT_TOKEN: Final[str] =os.environ.get('DISCORD_BOT_TOKEN')
intents = discord.Intents.default()
intents.message_content = True

# client = discord.Client(intents=intents)
client = commands.Bot(command_prefix='$', intents=intents, )

# 起動時に実行される
@client.event
async def on_ready() -> None:
    print(f'We have logged in as {client.user}')

# testコマンド
@client.command()
async def test(ctx, *, arg) -> None:
    await ctx.send(f'This is test message (receive from: {ctx.author}), message: {arg}')

@client.command()
async def system_start(ctx) -> None:
    if not ctx.author.voice:
        await ctx.send(f'ボイスチャンネルに参加していないユーザーからコマンドが実行されました')
        return
    vc = ctx.author.voice.channel
    try:
        await vc.connect()
    except discord.errors.ClientException as e:
        await ctx.send('既にボイスチャンネルに参加しています。一度終了してから再実行してください。')
    except:
        await ctx.send('ボイスチャンネルへの接続に失敗しました')


@client.command()
async def system_stop(ctx) -> None:
    if not ctx.voice_client:
        await ctx.send(f'botがボイスチャンネルに参加していません')
        return
    await ctx.voice_client.disconnect()

# 新規メッセージの受信
# https://discordpy.readthedocs.io/ja/latest/faq.html#why-does-on-message-make-my-commands-stop-working
@client.listen('on_message')
async def recv_message(message) -> None:
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
