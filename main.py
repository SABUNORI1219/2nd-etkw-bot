import discord
from discord.ext import commands
import os
import asyncio

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
    Bot本体のメインクラス。非同期のセットアップを担当する。
    """
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        """
        BotがDiscordにログインする前に一度だけ実行される。
        Cogs（機能部品）の読み込みに専念させる。
        """
        print("--- [司令塔] Cogs（受付係）の配属を開始します...")
        for filename in os.listdir('./cogs'):
            if filename.endswith('.py'):
                try:
                    await self.load_extension(f'cogs.{filename[:-3]}')
                    print(f"--- [司令塔] ✅ 受付係 '{filename}' の配属完了。")
                except Exception as e:
                    print(f"--- [司令塔] ❌ 受付係 '{filename}' の配属に失敗しました: {e}")
        print("--- [司令塔] 全ての受付係の配属が完了しました。")

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
    # Botの非同期ループが始まる前に、全ての同期的な準備を完了させる
    print("--- [起動シーケンス] データベースをセットアップします...")
    setup_database()
    
    print("--- [起動シーケンス] 24時間稼働用のWebサーバーを起動します...")
    keep_alive()

    if not TOKEN:
        print("致命的エラー: `DISCORD_TOKEN`が設定されていません。")
    else:
        try:
            print("--- [起動シーケンス] Botの起動を開始します... ---")
            bot.run(TOKEN)
        except Exception as e:
            print(f"Botの起動中に予期せぬエラーが発生しました: {e}")
