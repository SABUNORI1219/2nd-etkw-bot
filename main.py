import discord
from discord.ext import commands
import os
import sys
import asyncio
from dotenv import load_dotenv

# 作成したモジュールから必要な関数やクラスをインポート
from keep_alive import keep_alive
from lib.database_handler import setup_database

# .envファイルから環境変数を読み込む
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

activity = discord.Streaming(
    name="ちくちくちくわ",
    url="https://www.youtube.com/watch?v=dQw4w9WgXcQ"
)

# Botが必要とする権限（Intents）を定義
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

# Botのインスタンスを作成（プレフィックスは不要）
bot = commands.Bot(command_prefix="!", intents=intents, activity=activity)

@bot.event
async def on_ready():
    """Botの準備が完了したときに呼ばれるイベント"""
    print("==================================================")
    print(f"ログイン成功: {bot.user} (ID: {bot.user.id})")
    print("Botは正常に起動し、命令待機状態に入りました。")
    # コマンドのグローバル同期
    try:
        synced = await bot.tree.sync()
        print(f"--- ✅ {len(synced)}個のスラッシュコマンドをグローバル同期しました。")
    except Exception as e:
        print(f"--- ❌ コマンドの同期に失敗しました: {e}")
    print("==================================================")

async def load_cogs():
    """cogsフォルダから全ての機能部品を読み込む"""
    print("--- [司令塔] -> 全ての受付係（Cogs）を配属させます...")
    # setup_cogは不要になったため、リストから削除
    cogs_to_load = ['player_cog', 'guild_cog', 'tracker_cog']
    for cog_name in cogs_to_load:
        try:
            await bot.load_extension(f'cogs.{cog_name}')
            print(f"--- [司令塔] ✅ 受付係 '{cog_name}.py' の配属完了。")
        except Exception as e:
            print(f"--- [司令塔] ❌ 受付係 '{cog_name}.py' の配属に失敗しました: {e}")

async def main():
    """Botの起動シーケンスを管理するメイン関数"""
    async with bot:
        # Botが接続する前に、非同期の準備処理（Cogs読み込み）を行う
        await load_cogs()
        # Botを起動し、Discordに接続
        await bot.start(TOKEN)

# メインの実行ブロック
if __name__ == '__main__':
    # Botの非同期ループが始まる前に、全ての同期的な準備を完了させる
    setup_database()
    keep_alive()
    
    if not TOKEN:
        print("致命的エラー: `DISCORD_TOKEN`が設定されていません。")
        sys.exit(1)
        
    try:
        print("--- [司令塔] Botの起動を開始します... ---")
        asyncio.run(main())
    except Exception as e:
        print(f"Botの起動中に予期せぬエラーが発生しました: {e}")
        sys.exit(1)
