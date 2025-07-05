import discord
from discord.ext import commands
import os
import sys
import asyncio
from dotenv import load_dotenv

# 作成したモジュールから必要な関数をインポート
from keep_alive import keep_alive
from lib.database_handler import setup_database

# .envファイルから環境変数を読み込む
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

activity = discord.Streaming(
    name="ちくちくちくわ",
    url="https://youtu.be/E6O3-hAwJDY?si=uQnbzsJSHSvMJ9Db"
)

# Botが必要とする権限（Intents）を定義
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

# activityをここで設定します。
bot = commands.Bot(command_prefix="!", intents=intents, activity=activity)

@bot.event
async def on_ready():
    """Botの準備が完了したときに呼ばれるイベント"""
    print("==================================================")
    print(f"ログイン成功: {bot.user} (ID: {bot.user.id})")
    # ステータスを「オンライン（緑丸）」に設定
    await bot.change_presence(status=discord.Status.online)
    print(f"ステータス設定完了: {bot.activity.type.name} {bot.activity.name}")
    print("Botは正常に起動し、命令待機状態に入りました。")
    
    # コマンドのグローバル同期をここで行う
    try:
        print("--- スラッシュコマンドをグローバルに同期します... ---")
        synced = await bot.tree.sync()
        print(f"--- ✅ {len(synced)}個のコマンドをグローバル同期しました。（反映には最大1時間かかります）")
    except Exception as e:
        print(f"--- ❌ コマンドの同期に失敗しました: {e}")
        
    print("==================================================")

async def load_cogs():
    """cogsフォルダから全ての機能部品を読み込む"""
    print("--- [司令塔] -> 全ての受付係（Cogs）を配属させます...")
    for filename in os.listdir('./cogs'):
        if filename.endswith('.py'):
            try:
                await bot.load_extension(f'cogs.{filename[:-3]}')
                print(f"--- [司令塔] ✅ 受付係 '{filename}' の配属完了。")
            except Exception as e:
                print(f"--- [司令塔] ❌ 受付係 '{filename}' の配属に失敗しました: {e}")

async def main():
    """Botの起動シーケンスを管理するメイン関数"""
    async with bot:
        # 同期的な準備処理を最初に実行
        setup_database()
        keep_alive()
        
        # Botが接続する前に、非同期の準備処理（Cogs読み込み）を行う
        await load_cogs()
        
        # Botを起動し、Discordに接続
        await bot.start(TOKEN)

# メインの実行ブロック
if __name__ == '__main__':
    if not TOKEN:
        print("致命的エラー: `DISCORD_TOKEN`が設定されていません。")
        sys.exit(1)
        
    try:
        print("--- [司令塔] Botの起動を開始します... ---")
        asyncio.run(main())
    except Exception as e:
        print(f"Botの起動中に予期せぬエラーが発生しました: {e}")
        sys.exit(1)
