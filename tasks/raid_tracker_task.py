import discord
from discord.ext import commands, tasks
import logging

from lib.wynncraft_api import WynncraftAPI
from lib.database_handler import add_raid_history
from config import GUILD_NAME # 追跡対象のギルド名

logger = logging.getLogger(__name__)

class RaidTrackerTask(commands.Cog, name="RaidDataCollector"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.wynn_api = WynncraftAPI()
        self.previous_raid_counts = {} # 前回のレイド数を記憶
        self.collect_raid_data_task.start()

    def cog_unload(self):
        self.collect_raid_data_task.cancel()

    @tasks.loop(minutes=2.0)
    async def collect_raid_data_task(self):
        logger.info(f"--- [RaidTrackerTask] {GUILD_NAME}のメンバーデータを収集中...")
        guild_data = await self.wynn_api.get_nori_guild_data(GUILD_NAME)
        if not guild_data or 'members' not in guild_data:
            logger.warning("--- [RaidTrackerTask] ギルドデータの取得に失敗。")
            return
            
        current_raid_counts = {}
        history_to_add = []
        
        all_members = [p for rank in guild_data['members'] for p in rank.values()]

        for member in all_members:
            if not isinstance(member, dict) or 'uuid' not in member: continue
            
            uuid = member['uuid']
            name = member.get('username', 'Unknown')
            server = member.get('server')
            raids = member.get('globalData', {}).get('raids', {}).get('list', {})
            
            current_raid_counts[uuid] = raids
            
            # 前回のデータと比較
            if uuid in self.previous_raid_counts:
                previous_raids = self.previous_raid_counts[uuid]
                for raid_name, current_count in raids.items():
                    previous_count = previous_raids.get(raid_name, 0)
                    if current_count > previous_count:
                        logger.info(f"--- [RaidTrackerTask] クリア検知: {name}が{raid_name}をクリア！ ({previous_count} -> {current_count})")
                        # (UUID, 名前, レイド名, 新しいクリア数, サーバー)のタプルを追加
                        history_to_add.append((uuid, name, raid_name, current_count, server))

        if history_to_add:
            add_raid_history(history_to_add)

        self.previous_raid_counts = current_raid_counts
        logger.info(f"--- [RaidTrackerTask] データ収集完了。")

    @collect_raid_data_task.before_loop
    async def before_task(self):
        await self.bot.wait_until_ready()

async def setup(bot: commands.Bot):
    await bot.add_cog(RaidTrackerTask(bot))
