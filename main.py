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
        # 準備完了を知らせるための合図（イベント）を作成
        self.ready_event = asyncio.Event()

    async def setup_hook(self):
        """
        Botの非同期セットアップを管理する。
        """
        print("--- [司令塔] 起動準備を開始します ---")
        
        print("--- [司令塔] -> データベース担当にセットアップを依頼...")
        setup_database()
        
        print("--- [司令塔] -> Webサーバーを起動...")
        keep_alive()

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
        # 準備が完了したことを他の処理に合図する
        self.ready_event.set()

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
async def main():
    try:
        # Botの起動処理をバックグラウンドタスクとして開始
        bot_task = asyncio.create_task(bot.start(TOKEN))
        
        # on_readyで合図が送られるのを、90秒のタイムアウト付きで待つ
        await asyncio.wait_for(bot.ready_event.wait(), timeout=90.0)
        
        # Botが正常に終了するまで待機
        await bot_task

    except asyncio.TimeoutError:
        print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
        print("!!! 起動タイムアウト: 90秒以内にBotが準備完了になりませんでした。")
        print("!!! Renderの自動再起動機能により、プロセスを再起動します。")
        print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
        # 異常終了コードでプログラムを終了し、Renderに再起動を促す
        sys.exit(1)
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
