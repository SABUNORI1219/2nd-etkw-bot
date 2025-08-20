import discord
from discord import app_commands
from discord.ext import commands
import logging
import os

from lib.wynncraft_api import WynncraftAPI
from config import AUTHORIZED_USER_IDS
from lib.cache_handler import CacheHandler
from lib.banner_renderer import BannerRenderer
from lib.profile_renderer import generate_profile_card  # データ→画像生成だけ担当

logger = logging.getLogger(__name__)

class PlayerCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.wynn_api = WynncraftAPI()
        self.banner_renderer = BannerRenderer()
        self.cache = CacheHandler()

    def _safe_get(self, data: dict, keys: list, default=None):
        v = data
        for key in keys:
            if not isinstance(v, dict):
                return default
            v = v.get(key)
            if v is None:
                return default
        return v

    @app_commands.command(name="player", description="プレイヤーのステータスを表示")
    @app_commands.describe(player="MCID or UUID")
    async def player(self, interaction: discord.Interaction, player: str):
        await interaction.response.defer()
        if interaction.user.id not in AUTHORIZED_USER_IDS:
            await interaction.followup.send("権限なし")
            return

        cache_key = f"player_{player.lower()}"
        cached_data = self.cache.get_cache(cache_key)
        if cached_data:
            data = cached_data
        else:
            api_data = await self.wynn_api.get_official_player_data(player)
            if not api_data or (isinstance(api_data, dict) and "error" in api_data):
                await interaction.followup.send(f"プレイヤー「{player}」が見つかりませんでした。")
                return
            data = api_data
            self.cache.set_cache(cache_key, api_data)

        first_join_str = self._safe_get(data, ['firstJoin'], "N/A")
        first_join_date = first_join_str.split('T')[0] if 'T' in first_join_str else first_join_str

        last_join_str = self._safe_get(data, ['lastJoin'], "1970-01-01T00:00:00.000Z")
        try:
            last_join_dt = datetime.fromisoformat(last_join_str.replace('Z', '+00:00'))
            last_join_date = last_join_dt.strftime('%Y-%m-%d')
        except Exception:
            last_join_date = last_join_str.split('T')[0] if 'T' in last_join_str else last_join_str

        guild_prefix = self._safe_get(data, ['guild', 'prefix'], "")
        guild_data = await self.wynn_api.get_guild_by_prefix(guild_prefix)
        banner_bytes = self.banner_renderer.create_banner_image(guild_data.get('banner'))

        # 必要な情報だけdictでまとめる
        profile_info = {
            "username": data.get("username"),
            "support_rank_display": data.get("supportRank", "Player").capitalize(),
            "guild_prefix": guild_prefix,
            "banner_bytes": banner_bytes,
            "guild_name": self._safe_get(data, ['guild', 'name'], ""),
            "guild_rank": self._safe_get(data, ['guild', 'rank'], ""),
            "guild_rank_stars": self._safe_get(data, ['guild', 'rankStars'], ""),
            "first_join": first_join_date,
            "last_join": last_join_date,
            "mobs_killed": self._safe_get(data, ['globalData', 'mobsKilled'], 0),
            "playtime": data.get("playtime", 0),
            "wars": self._safe_get(data, ['globalData', 'wars'], 0),
            "war_rank_display": self._safe_get(data, ['ranking', 'warsCompletion'], "N/A"),
            "quests": self._safe_get(data, ['globalData', 'completedQuests'], 0),
            "world_events": self._safe_get(data, ['globalData', 'worldEvents'], 0),
            "total_level": self._safe_get(data, ['globalData', 'totalLevel'], 0),
            "chests": self._safe_get(data, ['globalData', 'chestsFound'], 0),
            "pvp_kill": f"{self._safe_get(data, ['globalData', 'pvp', 'kills'], 0)}",
            "pvp_death": f"{self._safe_get(data, ['globalData', 'pvp', 'deaths'], 0)}",
            "notg": self._safe_get(data, ['globalData', 'raids', 'list', 'Nest of the Grootslangs'], 0),
            "nol": self._safe_get(data, ['globalData', 'raids', 'list', "Orphion's Nexus of Light"], 0),
            "tcc": self._safe_get(data, ['globalData', 'raids', 'list', 'The Canyon Colossus'], 0),
            "tna": self._safe_get(data, ['globalData', 'raids', 'list', 'The Nameless Anomaly'], 0),
            "dungeons": self._safe_get(data, ['globalData', 'dungeons', 'total'], 0),
            "all_raids": self._safe_get(data, ['globalData', 'raids', 'total'], 0),
            "uuid": data.get("uuid"),
        }

        # 画像生成（profile_renderer.pyに情報だけ渡す）
        output_path = f"profile_card_{profile_info['uuid']}.png" if profile_info['uuid'] else "profile_card.png"
        try:
            generate_profile_card(profile_info, output_path)
            file = discord.File(output_path, filename=os.path.basename(output_path))
            await interaction.followup.send(file=file)
            if os.path.exists(output_path):
                os.remove(output_path)
        except Exception as e:
            logger.error(f"画像生成または送信失敗: {e}")
            await interaction.followup.send("プロフィール画像生成に失敗しました。")

async def setup(bot: commands.Bot):
    await bot.add_cog(PlayerCog(bot))
