import discord
from discord.ext import commands
import os

# 他のファイルから必要な関数をインポート
from keep_alive import keep_alive
from database import setup_database

TOKEN = os.getenv('DISCORD_TOKEN')

# BotのプレフィックスとIntentsを設定
intents = discord.Intents.default()
intents.message_content = True

class MyBot(commands.Bot):
    # Botのセットアップを管理する特別なメソッド
    async def setup_hook(self):
        print("--- setup_hook: Cogsの読み込みを開始 ---")
        # cogsフォルダ内の.pyファイルをすべて読み込む
        for filename in os.listdir('./cogs'):
            if filename.endswith('.py'):
                try:
                    await self.load_extension(f'cogs.{filename[:-3]}')
                    print(f"✅ Cog '{filename}' の読み込みに成功しました。")
                except Exception as e:
                    print(f"❌ Cog '{filename}' の読み込みに失敗しました。エラー: {e}")
        print("--- setup_hook: すべてのCogsの読み込みが完了 ---")

    # Bot起動時に実行される処理
    async def on_ready(self):
        print(f'ログイン成功: {self.user}')

# Botインスタンスを作成
bot = MyBot(command_prefix='!', intents=intents)

# メインの実行部分
if __name__ == '__main__':
    # データベースのセットアップ
    setup_database()
    # Webサーバーの起動
    keep_alive()
    # Botの起動
    bot.run(TOKEN)
