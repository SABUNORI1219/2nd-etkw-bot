import discord
from discord.ext import commands
from discord import app_commands
import os
import sys
import asyncio
import math
from dotenv import load_dotenv
import logging

# 作成したモジュールから必要な関数やクラスをインポート
from keep_alive import keep_alive
from logger_setup import setup_logger

# ロガーを最初にセットアップ
setup_logger()
logger = logging.getLogger(__name__)

# .envファイルから環境変数を読み込む
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

# Botのステータス（アクティビティ）を定義
activity = discord.Streaming(
    name="ちくちくちくわ",
    url="https://www.youtube.com/watch?v=E6O3-hAwJDY"
)

# Botが必要とする権限（Intents）を定義
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

# commands.Botを継承したカスタムBotクラス
class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents, activity=activity)

    async def setup_hook(self):
        """Botの非同期セットアップを管理する"""
        logger.info("--- [司令塔] 起動準備を開始します ---")
        try:
            create_table()
            logger.info("DBテーブルセットアップ正常終了")
        except Exception as e:
            logger.error(f"DBセットアップ失敗: {e}")
        
        # 同期的な準備処理を最初に実行
        keep_alive()

        # Cogsを読み込む
        logger.info("--- [司令塔] -> 全ての受付係（Cogs）を配属させます...")
        for filename in os.listdir('./cogs'):
            if filename.endswith('.py'):
                try:
                    await self.load_extension(f'cogs.{filename[:-3]}')
                    logger.info(f"--- [司令塔] ✅ 受付係 '{filename}' の配属完了。")
                except Exception as e:
                    logger.error(f"--- [司令塔] ❌ 受付係 '{filename}' の配属に失敗しました: {e}")

        # tasksを読み込む
        logger.info("--- [司令塔] -> 全ての内部処理係（tasks）を配属させます...")
        for filename in os.listdir('./tasks'):
            if filename.endswith('.py'):
                try:
                    await self.load_extension(f'tasks.{filename[:-3]}')
                    logger.info(f"--- [司令塔] ✅ 受付係 '{filename}' の配属完了。")
                except Exception as e:
                    logger.error(f"--- [司令塔] ❌ 受付係 '{filename}' の配属に失敗しました: {e}")
        
        try:
            logger.info("--- [司令塔] -> スラッシュコマンドをグローバルに同期します... ---")
            synced = await self.tree.sync()
            logger.info(f"--- [司令塔] ✅ {len(synced)}個のコマンドをグローバル同期しました。")
        except Exception as e:
            logger.error(f"--- [司令塔] ❌ コマンドの同期に失敗しました: {e}")

    async def on_ready(self):
        """Botの準備が完了したときに呼ばれるイベント"""
        logger.info("==================================================")
        logger.info(f"ログイン成功: {self.user} (ID: {self.user.id})")
        # ステータスの設定は on_ready で行うのが最も確実
        await self.change_presence(status=discord.Status.online, activity=activity)
        logger.info(f"ステータス設定完了: {self.activity.type.name} {self.activity.name}")
        logger.info("Botは正常に起動し、命令待機状態に入りました。")
        logger.info("==================================================")

# Botのインスタンスを作成
bot = MyBot()

@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.CommandOnCooldown):
        # 残り時間を秒単位で取得し、小数点以下を切り上げ
        remaining_seconds = math.ceil(error.retry_after)
        await interaction.response.send_message(
            f"現在クールダウン中です。あと **{remaining_seconds}秒** 待ってからもう一度お試しください。",
            ephemeral=True # コマンドを実行した本人にだけ見えるメッセージ
        )
    elif isinstance(error, app_commands.CheckFailure):
        # CheckFailure時のカスタムメッセージ
        await interaction.response.send_message(str(error), ephemeral=True)
    else:
        # 他のエラーはコンソールに出力（これまで通り）
        logger.error(f"--- [司令塔] 予期せぬエラーが発生: {error}", exc_info=True)
        # 必要であれば、ユーザーにエラーが発生したことを伝えるメッセージを送信
        # await interaction.response.send_message("コマンドの実行中にエラーが発生しました。", ephemeral=True)

# メインの実行ブロック
if __name__ == '__main__':
    if not TOKEN:
        logger.critical("致命的エラー: `DISCORD_TOKEN`が設定されていません。")
        sys.exit(1)
        
    try:
        logger.info("--- [司令塔] Botの起動を開始します... ---")
        bot.run(TOKEN)
    except Exception as e:
        logger.critical(f"Botの起動中に予期せぬエラーが発生しました: {e}")
        sys.exit(1)
