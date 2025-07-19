import discord
from discord.ext import commands, tasks
import logging

from lib.wynncraft_api import WynncraftAPI
from lib.database_handler import add_raid_history, get_setting
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
                logger.info(f"[DEBUG] メンバー抽出: {name}, info: {info}")
                all_names.append((name, info))

        current_raid_counts = {}
        history_to_add = []

        for name, member in all_names:
            uuid = member.get("uuid")
            if not uuid:
                continue

            # ✅ WynncraftAPIを通してNori Player APIにアクセス
            player_data = await self.wynn_api.get_nori_player_data(name)
            if not player_data:
                logger.warning(f"--- {name} のプレイヤーデータ取得に失敗")
                continue

            raids = player_data.get('globalData', {}).get('raids', {}).get('list', {})
            server = player_data.get("server")

            current_raid_counts[uuid] = raids

            if uuid in self.previous_raid_counts:
                previous_raids = self.previous_raid_counts[uuid]
                for raid_name, current_count in raids.items():
                    previous_count = previous_raids.get(raid_name, 0)
                    if current_count > previous_count:
                        logger.info(f"--- {name} が {raid_name} をクリア ({previous_count} -> {current_count})")
                        history_to_add.append((uuid, name, raid_name, current_count, server))

        if history_to_add:
            add_raid_history(history_to_add)

        self.previous_raid_counts = current_raid_counts
        logger.info("--- データ収集完了")
        
        # --- 2. 分析 ---
        logger.info("--- [RaidTrackerTask] レイドパーティの分析を開始します...")
        parties = self.analyzer.analyze_raids()
        if not parties:
            logger.info("--- [RaidTrackerTask] 通知対象のパーティは見つかりませんでした。"); return

        # --- 3. 通知 ---
        channel_id_str = get_setting("raid_notification_channel")
        if not channel_id_str:
            logger.warning("--- [RaidTrackerTask] 通知チャンネルが設定されていません。"); return
        
        channel = self.bot.get_channel(int(channel_id_str))
        if not channel:
            logger.error(f"--- [RaidTrackerTask] ID {channel_id_str} のチャンネルが見つかりません。"); return

        for p_info in parties:
            party = p_info['party']
            score = p_info['score']
            raid_name = party[0][3]
            
            player_names = [f"`{p[2]}`" for p in party]
            
            embed = discord.Embed(
                title=f"🎉 Guild Raid Clear: {raid_name}",
                description="**パーティメンバー:**\n- " + "\n- ".join(player_names),
                color=discord.Color.gold()
            )
            embed.set_footer(text=f"信頼スコア: {score}")
            await channel.send(embed=embed)

    @collect_raid_data_task.before_loop
    async def before_task(self):
        await self.bot.wait_until_ready()

async def setup(bot: commands.Bot):
    await bot.add_cog(RaidTrackerTask(bot))
