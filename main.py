import discord
from discord.ext import commands
import os
import sys

# 環境変数からトークンを取得
TOKEN = os.getenv('DISCORD_TOKEN')

# Botが必要とする権限（Intents）を定義
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

class MyBot(commands.Bot):
    """
    Bot本体のメインクラス。Cogsの読み込みと自動同期を担当する。
    """
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        """
        Botの非同期セットアップを管理する。
        """
        # cogsフォルダから全てのCogを読み込む
        print("--- [司令塔] -> 全ての受付係（Cogs）を配属させます...")
        cogs_to_load = ['setup_cog', 'player_cog','guild_cog'] # 読み込み順を定義
        for cog_name in cogs_to_load:
            try:
                await self.load_extension(f'cogs.{cog_name}')
                print(f"--- [司令塔] ✅ 受付係 '{cog_name}.py' の配属完了。")
            except Exception as e:
                print(f"--- [司令塔] ❌ 受付係 '{cog_name}.py' の配属に失敗しました: {e}")
        
        # 全ての準備完了後、グローバルコマンドを同期
        try:
            print("--- [司令塔] -> スラッシュコマンドをグローバルに同期します...")
            synced = await self.tree.sync()
            print(f"--- [司令塔] ✅ {len(synced)}個のコマンドをグローバル同期しました。（反映には最大1時間かかります）")
        except Exception as e:
            print(f"--- [司令塔] ❌ コマンドの同期に失敗しました: {e}")

    async def on_ready(self):
        """Botの準備が完了したときに呼ばれるイベント"""
        print("==================================================")
        print(f"ログイン成功: {self.user} (ID: {self.user.id})")
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
