# main.py

import discord
from discord.ext import commands
import os
import asyncio

# 他のファイルから必要な関数をインポート
from keep_alive import keep_alive
from database import setup_database

TOKEN = os.getenv('DISCORD_TOKEN')

# BotのプレフィックスとIntentsを設定
intents = discord.Intents.default()
intents.message_content = True
# Clientの代わりにBotを使用
bot = commands.Bot(command_prefix='!', intents=intents)

# Bot起動時に実行される処理
@bot.event
async def on_ready():
    print(f'ログイン成功: {bot.user}')

# Cogsを読み込むための非同期関数
async def load_cogs():
    # cogsフォルダ内の.pyファイルをすべて読み込む
    for filename in os.listdir('./cogs'):
        if filename.endswith('.py'):
            # 'cogs.ファイル名'（.pyは除く）の形式で読み込む
            await bot.load_extension(f'cogs.{filename[:-3]}')

# メインの実行部分
async def main():
    # データベースのセットアップ
    setup_database()
    # Cogsの読み込み
    await load_cogs()
    # Webサーバーの起動
    keep_alive()
    # Botの起動
    await bot.start(TOKEN)

if __name__ == '__main__':
    asyncio.run(main())
