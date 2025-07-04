from discord.ext import commands

# libフォルダとルートから必要な関数をインポート
from lib.database_handler import setup_database
from keep_alive import keep_alive

class SetupCog(commands.Cog):
    """
    Botの起動時に、同期的な準備処理（DB、Webサーバー）を担当する専門のCog。
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        print("--- [準備担当] 起動準備を開始します...")
        
        # データベースをセットアップ
        print("--- [準備担当] -> データベースをセットアップ...")
        setup_database()
        
        # 24時間稼働用のWebサーバーを起動
        print("--- [準備担当] -> Webサーバーを起動...")
        keep_alive()
        
        print("--- [準備担当] ✅ 全ての同期準備が完了しました。")

# BotにCogを登録するためのセットアップ関数
async def setup(bot: commands.Bot):
    await bot.add_cog(SetupCog(bot))
