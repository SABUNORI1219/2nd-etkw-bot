import discord
from discord.ext import commands
import os
import asyncio

# 各モジュールから必要な関数やクラスをインポート
from keep_alive import keep_alive
from database import setup_database
from config import GUILD_ID_INT

# 環境変数からトークンを取得
TOKEN = os.getenv('DISCORD_TOKEN')

# Botが必要とする権限（Intents）を定義
intents = discord.Intents.default()
intents.message_content = True
intents.members = True 
intents.presences = True

# commands.Botを継承したカスタムBotクラス
class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix='!', intents=intents)

    # Botの非同期セットアップを管理する特別なメソッド
    async def setup_hook(self):
        # --- 起動時の準備処理をすべてここに集約 ---
        
        print("--- setup_hook: データベースのセットアップを開始 ---")
        # 同期関数を非同期で安全に実行
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, setup_database)
        print("--- setup_hook: データベースのセットアップが完了 ---")

        print("--- setup_hook: Webサーバーを起動 ---")
        keep_alive()
        
        print("--- setup_hook: Cogsの読み込みを開始 ---")
        for filename in os.listdir('./cogs'):
            if filename.endswith('.py'):
                try:
                    await self.load_extension(f'cogs.{filename[:-3]}')
                    print(f"✅ Cog '{filename}' の読み込みに成功しました。")
                except Exception as e:
                    print(f"❌ Cog '{filename}' の読み込みに失敗しました。エラー: {e}")
        print("--- setup_hook: すべてのCogsの読み込みが完了 ---")

    # Botの準備が完了したときに呼ばれるイベント
    async def on_ready(self):
        print("==================================================")
        print(f"ログイン成功: {self.user} (ID: {self.user.id})")
        print("Botは正常に起動し、準備が完了しました。")
        print("==================================================")

# Botのインスタンスを作成
bot = MyBot()

# Botのオーナーのみが実行できる同期コマンド
@bot.command()
@commands.is_owner()
async def sync(ctx):
    if GUILD_ID_INT == 0:
        await ctx.send("エラー: GUILD_IDが環境変数に設定されていません。")
        return
        
    guild = discord.Object(id=GUILD_ID_INT)
    try:
        # コマンドを特定のサーバーに即時反映させる
        ctx.bot.tree.copy_global_to(guild=guild)
        synced = await ctx.bot.tree.sync(guild=guild)
        await ctx.send(f"{len(synced)}個のコマンドをサーバーに同期しました。")
    except Exception as e:
        await ctx.send(f"コマンドの同期に失敗しました: {e}")

# メインの実行ブロック
if __name__ == '__main__':
    try:
        # Botを起動
        bot.run(TOKEN)
    except discord.errors.LoginFailure:
        print("エラー: 不正なトークンです。Renderの環境変数 'DISCORD_TOKEN' を確認してください。")
    except Exception as e:
        print(f"Botの起動中に予期せぬエラーが発生しました: {e}")
