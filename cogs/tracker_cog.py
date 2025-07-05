import discord
from discord.ext import commands, tasks
from datetime import datetime
import uuid

# libとconfigから必要なものをインポート
from lib.wynncraft_api import WynncraftAPI
from lib.database_handler import add_raid_records
from lib.raid_logic import RaidLogicHandler
from config import TRACKING_CHANNEL_ID, GUILD_NAME # 追跡対象のギルド名をインポート
from player import Player

class RaidTrackerCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.wynn_api = WynncraftAPI()
        self.raid_logic = RaidLogicHandler()
        self.previous_state = {}
        self.raid_tracker_task.start()

    def cog_unload(self):
        self.raid_tracker_task.cancel()

    @tasks.loop(minutes=1.0)
    async def raid_tracker_task(self):
        print(f"--- [TrackerCog] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - トラッキングチェックを開始...")
        
        # ▼▼▼【エラー修正箇所】ギルド名を引数として渡す▼▼▼
        guild_data = await self.wynn_api.get_nori_guild_data(GUILD_NAME)
        # ▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲

        if not guild_data:
            print("--- [TrackerCog] APIからギルドデータを取得できませんでした。")
            return

        # (以降のロジックは変更なし)
        # ...
        
    # (他のメソッドは変更なし)
    # ...

async def setup(bot: commands.Bot):
    await bot.add_cog(RaidTrackerCog(bot))
