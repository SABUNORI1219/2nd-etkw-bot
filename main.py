 import discord
from discord.ext import commands, tasks
from discord import app_commands
import os
import sys
import asyncio
import math
from dotenv import load_dotenv
import logging
import psutil

# 作成したモジュールから必要な関数やクラスをインポート
from keep_alive import keep_alive
from logger_setup import setup_logger
from lib.db import create_table
from lib.discord_notify import LanguageSwitchView
from lib.ticket_embeds import register_persistent_views
from lib.application_views import ApplicationButtonView, register_persistent_views

APPLICATION_CHANNEL_ID = 1415107620108501082

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

# メモリ監視用の閾値
MAP_GEN_MEMORY_MB = 100
MEMORY_LIMIT_MB = 450

# commands.Botを継承したカスタムBotクラス
class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents, activity=activity)

    async def setup_hook(self):
        """Botの非同期セットアップを管理する"""
        logger.info("[Minister Chikuwa] -> 起動準備を開始")
        
        # 同期的な準備処理を最初に実行
        create_table()
        keep_alive()

        # Cogsを読み込む
        for filename in os.listdir('./cogs'):
            if filename.endswith('.py'):
                try:
                    await self.load_extension(f'cogs.{filename[:-3]}')
                    logger.info(f"[Minister Chikuwa] -> ✅ Cog '{filename}' をセットアップしました")
                except Exception as e:
                    logger.error(f"[Minister Chikuwa] -> ❌ Cog '{filename}' のセットアップに失敗: {e}")

        # tasksを読み込む
        for filename in os.listdir('./tasks'):
            if filename.endswith('.py'):
                try:
                    await self.load_extension(f'tasks.{filename[:-3]}')
                    logger.info(f"[Minister Chikuwa] -> ✅ Task '{filename}' をセットアップしました")
                except Exception as e:
                    logger.error(f"[Minister Chikuwa] -> ❌ Task '{filename}' のセットアップに失敗: {e}")
        
        register_persistent_views(self)
        # HElper Function Kidou
        await ensure_application_embed()

        try:
            synced = await self.tree.sync()
            logger.info(f"[Minister Chikuwa] -> ✅ {len(synced)}個のコマンドの同期が完了しました")
        except Exception as e:
            logger.error(f"[Minister Chikuwa] -> ❌ コマンドの同期に失敗しました: {e}")

        self.add_view(LanguageSwitchView())
        self.add_view(ApplicationButtonView())

    async def on_ready(self):
        """Botの準備が完了したときに呼ばれるイベント"""
        logger.info("==================================================")
        logger.info(f"ログイン成功: {self.user} (ID: {self.user.id})")
        await self.change_presence(status=discord.Status.online, activity=activity)
        logger.info(f"ステータス設定完了: {self.activity.type.name} {self.activity.name}")
        logger.info("Botは正常に起動し、現在稼働中です。")
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

# HElper Function Desu
async def ensure_application_embed():
    """申請ボタン付きEmbedがチャンネルに常駐しているか確認し、なければ送信"""
    channel = bot.get_channel(APPLICATION_CHANNEL_ID)
    if channel is None:
        channel = await bot.fetch_channel(APPLICATION_CHANNEL_ID)
    # 直近100件程度を調べる
    async for msg in channel.history(limit=100):
        if msg.author != bot.user:
            continue
        # Embedタイトルで判定
        if msg.embeds and msg.embeds[0].title and "メンバー申請" in msg.embeds[0].title:
            # --- ボタン(custom_id)も判定 ---
            for action_row in msg.components:
                for component in getattr(action_row, "children", []):
                    if getattr(component, "custom_id", None) == "application_start":
                        # 既に申請ボタン付きEmbedがある
                        return
    # なければ新規投稿
    embed = ApplicationButtonView.make_application_guide_embed()
    view = ApplicationButtonView()
    await channel.send(embed=embed, view=view)

async def wait_for_memory_ok(required=MAP_GEN_MEMORY_MB, limit=MEMORY_LIMIT_MB, timeout=60):
    """
    required: この後実行する処理で消費する想定メモリ(MB)
    limit: サービス全体で許容する最大メモリ(MB)
    timeout: 最大待機秒数。超えたらRuntimeError
    """
    proc = psutil.Process()
    waited = 0
    while True:
        mem_mb = proc.memory_info().rss / (1024 * 1024)
        if mem_mb + required < limit:
            return
        if waited == 0:
            logger.info(f"[MemoryGuard] メモリ残量不足: {mem_mb:.1f}MB/上限{limit}MB。空き待機開始...")
        await asyncio.sleep(2)
        waited += 2
        if waited >= timeout:
            raise RuntimeError(f"サーバが高負荷状態（~{mem_mb:.1f}MB使用中）のため、処理を中断しました。")

@tasks.loop(hours=1)
async def start_embed_check():
    """1時間おきに申請ボタン付きEmbedが存在するか再確認＆復旧"""
    await ensure_application_embed()

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
