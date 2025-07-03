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
    Bot本体のメインクラス。起動時のセットアップを担当する。
    """
    def __init__(self):
        # スラッシュコマンドのみを使用するため、プレフィックスは不要
        super().__init__(command_prefix=commands.when_mentioned_or("!"), intents=intents)

    async def setup_hook(self):
        """
        Botの非同期セットアップを管理する特別なメソッド。
        BotがDiscordにログインする前に一度だけ実行される。
        """
        print("--- [司令塔] 起動準備を開始します ---")
        
        # 1. データベースをセットアップ
        print("--- [司令塔] -> データベース担当にセットアップを依頼...")
        setup_database()
        
        # 2. 24時間稼働用のWebサーバーを起動
        print("--- [司令塔] -> Webサーバーを起動...")
        keep_alive()

        # 3. cogsフォルダから全ての「受付係」を読み込む
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
        # コマンドを特定のサーバーに即時反映
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
    else:
        try:
            print("--- [司令塔] Botの起動を開始します... ---")
            bot.run(TOKEN)
        except Exception as e:
            print(f"Botの起動中に予期せぬエラーが発生しました: {e}")
