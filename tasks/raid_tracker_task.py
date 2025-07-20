import discord
import asyncio
from discord.ext import commands, tasks
from datetime import datetime, timedelta
import logging

from lib.wynncraft_api import WynncraftAPI
from lib.database_handler import add_raid_history, get_setting, add_server_history, get_latest_server_before
from lib.raid_analyzer import RaidAnalyzer
from config import GUILD_NAME # 追跡対象のギルド名
from aiohttp import ClientSession

logger = logging.getLogger(__name__)

class RaidTrackerTask(commands.Cog, name="RaidDataCollector"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.wynn_api = WynncraftAPI()
        self.analyzer = RaidAnalyzer()
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

        # メンバー抽出（owner, chiefなどの各階層を走査）
        member_section = guild_data["members"]
        all_names = []
        for rank_name, rank_dict in member_section.items():
            if rank_name == "total":
                continue
            for name, info in rank_dict.items():
                all_names.append((name, info))

        current_raid_counts = {}
        history_to_add = []
        server_history_to_add = []

        # --- 並列でAPIアクセス（async gather） ---
        async def fetch_player_data(name, member):
            uuid = member.get("uuid")
            if not uuid:
                return None
            player_data = await self.wynn_api.get_nori_player_data(name)
            if not player_data:
                logger.warning(f"--- {name} のプレイヤーデータ取得に失敗")
                return None
            raids = player_data.get('globalData', {}).get('raids', {}).get('list', {})
            server = player_data.get("server")
            now = datetime.utcnow()
            return (uuid, name, raids, server, now)

        # 並列で取得
        results = await asyncio.gather(
            *[fetch_player_data(name, member) for name, member in all_names],
            return_exceptions=True
        )

        for res in results:
            if not res or isinstance(res, Exception):
                continue
            uuid, name, raids, server, now = res
            current_raid_counts[uuid] = raids
            server_history_to_add.append((uuid, name, server, now))

            if uuid in self.previous_raid_counts:
                previous_raids = self.previous_raid_counts[uuid]
                for raid_name, current_count in raids.items():
                    previous_count = previous_raids.get(raid_name, 0)
                    if current_count > previous_count:
                        clear_time = datetime.utcnow()
                        logger.info(f"--- {name} が {raid_name} をクリア ({previous_count} -> {current_count})")
                        server = get_latest_server_before(uuid, clear_time)
                        history_to_add.append((uuid, name, raid_name, current_count, server, clear_time))

        add_server_history(server_history_to_add)

        if history_to_add:
            add_raid_history(history_to_add)

        self.previous_raid_counts = current_raid_counts
        logger.info("--- データ収集完了")
        
        # --- 2. 分析 ---
        logger.info("--- [RaidTrackerTask] レイドパーティの分析を開始します...")
        await self._analyze_and_notify()

    async def _analyze_and_notify(self):
        loop = asyncio.get_running_loop()
        # RaidAnalyzer.analyze_raids() は重い処理なので executorで非同期化
        parties = await loop.run_in_executor(None, self.analyzer.analyze_raids)
        if not parties:
            logger.info("--- [RaidTrackerTask] 通知対象のパーティは見つかりませんでした。"); return

        channel_id_str = get_setting("raid_notification_channel")
        if not channel_id_str:
            logger.warning("--- [RaidTrackerTask] 通知チャンネルが設定されていません。"); return
        
        channel = self.bot.get_channel(int(channel_id_str))
        if not channel:
            logger.error(f"--- [RaidTrackerTask] ID {channel_id_str} のチャンネルが見つかりません。"); return

        for p_info in parties:
            party = p_info['party']
            raid_name = party[0][3]
            player_names = [f"`{p[2]}`" for p in party]
            clear_times = [p[4] for p in party if len(p) > 4]
            if clear_times:
                clear_time_str = max(clear_times)
                try:
                    clear_time_str = datetime.fromisoformat(clear_time_str).strftime("%Y-%m-%d %H:%M:%S")
                except Exception:
                    pass
            else:
                clear_time_str = "不明"
            
            embed = discord.Embed(
                title="Guild Raid Clear",
                color=discord.Color.blue()
            )
            embed.add_field(
                name=f"**{raid_name}** - `{clear_time_str}`",
                value=f"**Members**: {', '.join(player_names)}",
                inline=False
            )
            embed.set_footer(text=f"Guild Raid Tracker | Minister Chikuwa")
            await channel.send(embed=embed)
    
    @collect_raid_data_task.before_loop
    async def before_task(self):
        await self.bot.wait_until_ready()

async def setup(bot: commands.Bot):
    await bot.add_cog(RaidTrackerTask(bot))
