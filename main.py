import discord
from discord.ext import commands
import os
import asyncio
import sys

# 作成したモジュールから必要な関数やクラスをインポート
from keep_alive import keep_alive
from lib.database_handler import setup_database
from config import GUILD_ID_INT

# 環境変数からトークンを取得
TOKEN = os.getenv('DISCORD_TOKEN')

# Botが必要とする権限（Intents）を定義
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

class MyBot(commands.Bot):
    """
    Bot本体のメインクラス。起動時のセットアップを担当する。
    """
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        """
        Botの非同期セットアップを管理する。
        BotがDiscordにログインする前に一度だけ実行される。
        """
        print("--- [司令塔] 起動準備を開始します ---")
        
        loop = asyncio.get_running_loop()

        # 同期的なセットアップ処理を非同期イベントループで安全に実行
        print("--- [司令塔] -> データベース担当にセットアップを依頼...")
        await loop.run_in_executor(None, setup_database)
        
        print("--- [司令塔] -> Webサーバーを起動...")
        await loop.run_in_executor(None, keep_alive)

        # cogsフォルダから全ての「受付係」を読み込む
        print("--- [司令塔] -> 全ての受付係（Cogs）を配属させます...")
        for filename in os.listdir('./cogs'):
            if filename.endswith('.py'):
                try:
                    await self.load_extension(f'cogs.{filename[:-3]}')
                    print(f"--- [司令塔] ✅ 受付係 '{filename}' の配属完了。")
                except Exception as e:
                    print(f"--- [司令塔] ❌ 受付係 '{filename}' の配属に失敗しました: {e}")
        
        print("--- [司令塔] 全ての起動準備が完了しました。")

    async def on_ready(self):
        """Botの準備が完了したときに呼ばれるイベント"""
        print("==================================================")
        print(f"ログイン成功: {self.user} (ID: {self.user.id})")
        print("Botは正常に起動し、命令待機状態に入りました。")
        print("==================================================")

# Botのインスタンスを作成
bot = MyBot()

@bot.command()
@commands.is_owner()
async def sync(ctx: commands.Context):
    """スラッシュコマンドをDiscordに即時反映させるためのオーナー用コマンド"""
    if GUILD_ID_INT == 0:
        await ctx.send("エラー: `GUILD_ID`が環境変数に設定されていません。")
        return
        
    guild = discord.Object(id=GUILD_ID_INT)
    try:
        bot.tree.copy_global_to(guild=guild)
        synced = await bot.tree.sync(guild=guild)
        await ctx.send(f"`{len(synced)}`個のコマンドをこのサーバーに同期しました。")
        print(f"{len(synced)}個のコマンドをサーバーに同期しました。")
    except Exception as e:
        await ctx.send(f"コマンドの同期に失敗しました: {e}")

# メインの実行ブロック
if __name__ == '__main__':
    if not TOKEN:
        print("致命的エラー: `DISCORD_TOKEN`が設定されていません。")
        sys.exit(1)
        
    try:
        print("--- [司令塔] Botの起動を開始します... ---")
        bot.run(TOKEN)
    except Exception as e:
        print(f"Botの起動中に予期せぬエラーが発生しました: {e}")
        sys.exit(1)
