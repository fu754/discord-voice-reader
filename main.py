import os
import discord
from discord.ext import commands
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
async def on_ready():
    print(f'We have logged in as {client.user}')

# testコマンド
@client.command()
async def test(ctx, *, arg):
    await ctx.send(f'This is test message (receive from: {ctx.author}), message: {arg}')

# 新規メッセージの受信
# https://discordpy.readthedocs.io/ja/latest/faq.html#why-does-on-message-make-my-commands-stop-working
@client.listen('on_message')
async def recv_message(message):
    if message.author == client.user:
        pass

    if message.content.startswith('hello'):
        await message.channel.send('Hello!')

client.run(DISCORD_BOT_TOKEN)
