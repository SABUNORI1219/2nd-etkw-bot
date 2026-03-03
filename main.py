import discord
from discord.ext import commands
from discord import app_commands
import os
import sys
import math
from dotenv import load_dotenv
import logging

from keep_alive import keep_alive
from logger_setup import setup_logger
from lib.db import create_table
from lib.utils import create_embed

# ロガーを最初にセットアップ
setup_logger()
logger = logging.getLogger(__name__)

# .envファイルから環境変数を読み込む
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

# commands.Botを継承したカスタムBotクラス
class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=discord.Intents.all())

    async def setup_hook(self):
        """Botの非同期セットアップを管理する"""
        logger.info("[Onyx_] -> 起動準備を開始")
        
        # 同期的な準備処理を最初に実行
        create_table()
        keep_alive()

        # Cogsを読み込む
        for filename in os.listdir('./cogs'):
            if filename.endswith('.py'):
                try:
                    await self.load_extension(f'cogs.{filename[:-3]}')
                    logger.info(f"[Onyx_] -> ✅ Cog '{filename}' をセットアップしました")
                except Exception as e:
                    logger.error(f"[Onyx_] -> ❌ Cog '{filename}' のセットアップに失敗: {e}")

        # tasksを読み込む
        for filename in os.listdir('./tasks'):
            if filename.endswith('.py'):
                try:
                    await self.load_extension(f'tasks.{filename[:-3]}')
                    logger.info(f"[Onyx_] -> ✅ Task '{filename}' をセットアップしました")
                except Exception as e:
                    logger.error(f"[Onyx_] -> ❌ Task '{filename}' のセットアップに失敗: {e}")

        try:
            synced = await self.tree.sync()
            logger.info(f"[Onyx_] -> ✅ {len(synced)}個のコマンドの同期が完了しました")
        except Exception as e:
            logger.error(f"[Onyx_] -> ❌ コマンドの同期に失敗しました: {e}")

    async def on_ready(self):
        """Botの準備が完了したときに呼ばれるイベント"""
        logger.info("==================================================")
        logger.info(f"ログイン成功: {self.user} (ID: {self.user.id})")
        logger.info("Botは正常に起動し、現在稼働中です。")
        logger.info("==================================================")

bot = MyBot()

@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.CommandOnCooldown):
        # 残り時間を秒単位で取得し、小数点以下を切り上げ
        remaining_seconds = math.ceil(error.retry_after)
        embed = create_embed(description=f"現在クールダウン中です。\nあと **{remaining_seconds}秒** 待ってからもう一度お試しください。", title="🔴 エラーが発生しました", color=discord.Color.red(), footer_text=f"Main System | Onyx_")
        await interaction.response.send_message(embed=embed, ephemeral=True)
    elif isinstance(error, app_commands.CheckFailure):
        # CheckFailure時のカスタムメッセージ
        embed = create_embed(description=str(error), title="🔴 エラーが発生しました", color=discord.Color.red(), footer_text=f"Main System | Onyx_")
        await interaction.response.send_message(embed=embed, ephemeral=True)
    else:
        # 他のエラーはコンソールに出力
        logger.error(f"[Onyx_] -> 予期せぬエラーが発生: {error}", exc_info=True)

# メインの実行ブロック
if __name__ == '__main__':
    if not TOKEN:
        logger.critical("致命的エラー: `DISCORD_TOKEN`が設定されていません。")
        sys.exit(1)
        
    try:
        logger.info("[Onyx_] -> Botの起動を開始します... ---")
        bot.run(TOKEN)
    except Exception as e:
        logger.critical(f"[Onyx_] -> Botの起動中に予期せぬエラーが発生しました: {e}")
        sys.exit(1)
