import discord
from discord.ext import commands
import os
import sys
import asyncio
from dotenv import load_dotenv
import logging # loggingをインポート

# 作成したモジュールから必要な関数やクラスをインポート
from keep_alive import keep_alive
from lib.database_handler import setup_database
from logger_setup import setup_logger # ロガー設定関数をインポート

# .envファイルから環境変数を読み込む
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

# --- ▼▼▼ ロガーのセットアップ ▼▼▼ ---
# printより先にロガーを準備する
setup_logger()
logger = logging.getLogger(__name__)
# --- ▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲

# Botのステータス（アクティビティ）を定義
activity = discord.Streaming(
    name="ちくちくちくわ",
    url="https://www.youtube.com/watch?v=E6O3-hAwJDY&list=RDE6O3-hAwJDY&start_radio=1"
)

# Botが必要とする権限（Intents）を定義
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

# Botのインスタンスを作成
bot = commands.Bot(command_prefix="!", intents=intents, activity=activity)

@bot.event
async def on_ready():
    """Botの準備が完了したときに呼ばれるイベント"""
    logger.info("==================================================")
    logger.info(f"ログイン成功: {bot.user} (ID: {bot.user.id})")
    await bot.change_presence(status=discord.Status.online)
    logger.info(f"ステータス設定完了: {bot.activity.type.name} {bot.activity.name}")
    logger.info("Botは正常に起動し、命令待機状態に入りました。")
    
    # コマンドのグローバル同期
    try:
        logger.info("--- スラッシュコマンドをグローバルに同期します... ---")
        synced = await bot.tree.sync()
        logger.info(f"--- ✅ {len(synced)}個のコマンドをグローバル同期しました。")
    except Exception as e:
        logger.error(f"--- ❌ コマンドの同期に失敗しました: {e}")
        
    logger.info("==================================================")

async def load_cogs():
    """cogsフォルダから全ての機能部品を読み込む"""
    logger.info("--- [司令塔] -> 全ての受付係（Cogs）を配属させます...")
    for filename in os.listdir('./cogs'):
        if filename.endswith('.py'):
            try:
                await bot.load_extension(f'cogs.{filename[:-3]}')
                logger.info(f"--- [司令塔] ✅ 受付係 '{filename}' の配属完了。")
            except Exception as e:
                logger.error(f"--- [司令塔] ❌ 受付係 '{filename}' の配属に失敗しました: {e}")

async def main():
    """Botの起動シーケンスを管理するメイン関数"""
    async with bot:
        setup_database()
        keep_alive()
        await load_cogs()
        await bot.start(TOKEN)

if __name__ == '__main__':
    if not TOKEN:
        logger.critical("致命的エラー: `DISCORD_TOKEN`が設定されていません。")
        sys.exit(1)
        
    try:
        logger.info("--- [司令塔] Botの起動を開始します... ---")
        asyncio.run(main())
    except Exception as e:
        logger.critical(f"Botの起動中に予期せぬエラーが発生しました: {e}")
        sys.exit(1)
