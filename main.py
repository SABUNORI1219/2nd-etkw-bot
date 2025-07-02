import discord
from discord.ext import commands
import os

from keep_alive import keep_alive
from database import setup_database

TOKEN = os.getenv('DISCORD_TOKEN')

#  Intents（権限）を強化
intents = discord.Intents.default()
intents.message_content = True
intents.members = True # メンバー情報を取得するために追加
intents.presences = True # プレゼンス情報（オンライン状態など）のために追加

class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix='!', intents=intents)

    # Botのセットアップを管理する特別なメソッド
    async def setup_hook(self):
        print("--- setup_hook: Cogsの読み込みを開始 ---")
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
        print("==================================================")
        print(f"ログイン成功: {self.user} (ID: {self.user.id})")
        print("Botは正常に起動し、準備が完了しました。")
        print("==================================================")
        # 注意: このメッセージが表示されない場合、DISCORD_TOKENが間違っている可能性が非常に高いです。

bot = MyBot()

# Botのオーナーのみが実行できる同期コマンド
@bot.command()
@commands.is_owner()
async def sync(ctx):
    try:
        synced = await ctx.bot.tree.sync()
        await ctx.send(f"{len(synced)}個のコマンドを同期しました。")
        print(f"{len(synced)}個のコマンドを同期しました。")
    except Exception as e:
        await ctx.send(f"コマンドの同期に失敗しました: {e}")
        print(f"コマンドの同期に失敗しました: {e}")

if __name__ == '__main__':
    print("データベースのセットアップを開始します...")
    setup_database()

    print("Webサーバーを起動します...")
    keep_alive()
    
    print("Botを起動します...")
    bot.run(TOKEN)
