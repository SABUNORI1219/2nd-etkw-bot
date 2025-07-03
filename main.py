import discord
from discord.ext import commands
import os
import asyncio # asyncioをインポート

from keep_alive import keep_alive
from database import setup_database
from config import GUILD_ID_INT

TOKEN = os.getenv('DISCORD_TOKEN')

# Intents（権限）を強化
intents = discord.Intents.default()
intents.message_content = True
intents.members = True 
intents.presences = True

class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix='!', intents=intents)

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

    async def on_ready(self):
        print("==================================================")
        print(f"ログイン成功: {self.user} (ID: {self.user.id})")
        print("Botは正常に起動し、準備が完了しました。")
        print("==================================================")

bot = MyBot()

@bot.command()
@commands.is_owner()
async def sync(ctx):
    guild = discord.Object(id=GUILD_ID_INT)
    try:
        ctx.bot.tree.copy_global_to(guild=guild)
        synced = await ctx.bot.tree.sync(guild=guild)
        await ctx.send(f"{len(synced)}個のコマンドをサーバーに同期しました。")
    except Exception as e:
        await ctx.send(f"コマンドの同期に失敗しました: {e}")

# ▼▼▼【最終修正箇所】▼▼▼
async def main():
    # データベースとWebサーバーを先に準備
    print("データベースのセットアップを開始します...")
    setup_database()
    print("Webサーバーを起動します...")
    keep_alive()

    async with bot:
        try:
            print("Botを起動し、Discordへの接続を開始します...")
            # bot.run()の代わりに、制御可能なbot.start()を使用
            await bot.start(TOKEN)
        except discord.errors.LoginFailure:
            print("エラー: 不正なトークンです。Renderの環境変数を確認してください。")
        except Exception as e:
            print(f"Botの起動中に予期せぬエラーが発生しました: {e}")

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Botを手動で停止します。")
