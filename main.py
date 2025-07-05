import discord
from discord.ext import commands
import os
import sys
from dotenv import load_dotenv

# .envファイルから環境変数を読み込む
load_dotenv()

# 環境変数からトークンを取得
TOKEN = os.getenv('DISCORD_TOKEN')

# Botが必要とする権限（Intents）を定義
intents = discord.Intents.default()
intents.message_content = True # 将来的にメッセージ内容を読み取る機能のために維持
intents.members = True       # メンバーの参加などを検知するために維持

activity = discord.Streaming(
    name="ちくちくちくわ",
    url="https://youtu.be/E6O3-hAwJDY?si=uQnbzsJSHSvMJ9Db"
)

class MyBot(commands.Bot):
    """
    Bot本体のメインクラス。Cogsの読み込みとステータス設定を担当する。
    """
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents, activity=activity)

    async def setup_hook(self):
        """
        Botの非同期セットアップを管理する。
        """
        print("--- [司令塔] -> 全ての受付係（Cogs）を配属させます...")
        cogs_to_load = ['setup_cog', 'player_cog', 'guild_cog']
        for cog_name in cogs_to_load:
            try:
                await self.load_extension(f'cogs.{cog_name}')
                print(f"--- [司令塔] ✅ 受付係 '{cog_name}.py' の配属完了。")
            except Exception as e:
                print(f"--- [司令塔] ❌ 受付係 '{cog_name}.py' の配属に失敗しました: {e}")
        
        # グローバルコマンドの同期は、!syncコマンドで行うため、ここからは削除
        # これにより、起動時間を短縮し、レート制限のリスクを減らせます。

    async def on_ready(self):
        """Botの準備が完了したときに呼ばれるイベント"""
        print("==================================================")
        print(f"ログイン成功: {self.user} (ID: {self.user.id})")
        # ステータスを「オンライン（緑丸）」に設定
        await self.change_presence(status=discord.Status.online)
        print(f"ステータス設定完了: {self.activity.type.name} {self.activity.name}")
        print("Botは正常に起動し、命令待機状態に入りました。")
        print("==================================================")

# Botのインスタンスを作成
bot = MyBot()

# メインの実行ブロック
if __name__ == '__main__':
    if not TOKEN:
        print("致命的エラー: `DISCORD_TOKEN`が設定されていません。")
        sys.exit(1)
        
    try:
        print("--- [司令塔] Botの起動を開始します... ---")
        bot.run(TOKEN)
    except Exception as e:
        print(f"Botの起動中に予期せぬエラーが発生しました: {e}")
        sys.exit(1)
