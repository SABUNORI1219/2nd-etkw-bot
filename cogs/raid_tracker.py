# cogs/raid_tracker.py

import discord
from discord.ext import tasks, commands
import aiohttp # HTTPリクエストを非同期で行うためのライブラリ

# Wynncraft APIのベースURL
PLAYER_API_URL = "https://api.wynncraft.com/v3/player/{}"
GUILD_API_URL = "https://nori.fish/api/guild/Empire%20of%20TKW"

class RaidTracker(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # {player_uuid: {raid_name: count, ...}} の形式で前回のレイド数を保存
        self.previous_raid_counts = {}
        # ループ処理を開始
        self.raid_check_loop.start()

    def cog_unload(self):
        # Cogがアンロードされるときにループを停止
        self.raid_check_loop.cancel()

    # 1分ごとにループするタスクを定義
    @tasks.loop(minutes=1)
    async def raid_check_loop(self):
        print("レイド数のチェックを開始します...")
        # --- ここに、APIからデータを取得して比較するロジックを実装していく ---
        
        # 例: まずはギルドメンバーのリストを取得
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(GUILD_API_URL) as response:
                    if response.status == 200:
                        guild_data = await response.json()
                        online_members = guild_data.get("members", [])
                        print(f"現在オンラインのメンバーは{len(online_members)}人です。")
                        # 次のステップで、このメンバーたちのレイド数を取得・比較します。
                    else:
                        print(f"ギルドAPIへのアクセスに失敗しました。ステータスコード: {response.status}")
        except Exception as e:
            print(f"ループ処理中にエラーが発生しました: {e}")


    @raid_check_loop.before_loop
    async def before_raid_check_loop(self):
        # Botが完全に準備できるまで待機
        await self.bot.wait_until_ready()
        print("Botの準備が完了したため、レイド監視ループを開始します。")


async def setup(bot):
    """CogをBotに登録するための必須の関数"""
    await bot.add_cog(RaidTracker(bot))
