import discord
from discord.ext import commands
import os
import asyncio
import sys

from keep_alive import keep_alive
from database import setup_database
from config import GUILD_ID_INT

TOKEN = os.getenv('DISCORD_TOKEN')

# Intents
intents = discord.Intents.default()
intents.message_content = True
intents.members = True 
intents.presences = True

class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix='!', intents=intents)
        self.ready_event = asyncio.Event()

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
        # 準備が完了したことを他の処理に合図する
        self.ready_event.set()

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
    setup_database()
    keep_alive()

    try:
        # Botの起動処理をバックグラウンドタスクとして開始
        bot_task = asyncio.create_task(bot.start(TOKEN))

        # on_readyで合図が送られるのを、タイムアウト付きで待つ
        await asyncio.wait_for(bot.ready_event.wait(), timeout=90.0)

        # Botが正常に終了するまで待機
        await bot_task

    except asyncio.TimeoutError:
        print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
        print("!!! 起動タイムアウト: 90秒以内にBotが準備完了になりませんでした。")
        print("!!! Renderの自動再起動機能により、プロセスを再起動します。")
        print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
        sys.exit(1) # 異常終了コードでプログラムを終了し、Renderに再起動を促す
    except discord.errors.LoginFailure:
        print("エラー: 不正なトークンです。Renderの環境変数を確認してください。")
        sys.exit(1)
    except Exception as e:
        print(f"Botの実行中に予期せぬエラーが発生しました: {e}")
        sys.exit(1)


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Botを手動で停止します。")
