import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime
from urllib.parse import quote
import logging

# libとconfigから必要なものをインポート
from lib.wynncraft_api import WynncraftAPI
from lib.cache_handler import CacheHandler
from config import EMBED_COLOR_BLUE

logger = logging.getLogger(__name__)

class GuildCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.wynn_api = WynncraftAPI()
        self.cache = CacheHandler()
        logger.info("--- [CommandsCog] ギルドコマンドCogが読み込まれました。")

    def _safe_get(self, data: dict, keys: list, default: any = "N/A"):
        for key in keys:
            if not isinstance(data, dict): return default
            data = data.get(key)
        return data if data is not None else default

    def _create_online_players_table(self, online_players_list: list) -> tuple[str, int]:
        if not online_players_list: return "（現在オンラインのメンバーはいません）", 0
        max_name_len = max((len(p.get('name','')) for p in online_players_list), default=6)
        max_server_len = max((len(p.get('server','')) for p in online_players_list), default=2)
        max_rank_len = max((len(p.get('rank','')) for p in online_players_list), default=5)
        max_name_len = max(max_name_len, 6); max_server_len = max(max_server_len, 2); max_rank_len = max(max_rank_len, 5)
        header = f"║ {'WC'.center(max_server_len)} ║ {'Player'.center(max_name_len)} ║ {'Rank'.center(max_rank_len)} ║"
        divider = f"╠═{'═'*max_server_len}═╬═{'═'*max_name_len}═╬═{'═'*max_rank_len}═╣"
        top_border = f"╔═{'═'*max_server_len}═╦═{'═'*max_name_len}═╦═{'═'*max_rank_len}═╗"
        bottom_border = f"╚═{'═'*max_server_len}═╩═{'═'*max_name_len}═╩═{'═'*max_rank_len}═╝"
        player_rows = []
        for p in sorted(online_players_list, key=lambda x: len(x.get('rank', '')), reverse=True):
            server = p.get('server', 'N/A').center(max_server_len)
            name = p.get('name', 'N/A').ljust(max_name_len)
            rank = p.get('rank', '').center(max_rank_len)
            player_rows.append(f"║ {server} ║ {name} ║ {rank} ║")
        return "\n".join([top_border, header, divider] + player_rows + [bottom_border]), len(online_players_list)

    def _create_guild_embed(self, data: dict, interaction: discord.Interaction, from_cache: bool = False, is_stale: bool = False) -> discord.Embed:
        name = self._safe_get(data, ['name'])
        prefix = self._safe_get(data, ['prefix'])
        owner = self._safe_get(data, ['owner'])
        created_date = self._safe_get(data, ['created_date'])
        level = self._safe_get(data, ['level'], 0)
        xp_percent = self._safe_get(data, ['xp_percent'], 0)
        wars = self._safe_get(data, ['wars'], 0)
        territories = self._safe_get(data, ['territories'], 0)
        season_ranks = self._safe_get(data, ['seasonRanks'], {})
        latest_season = str(max([int(k) for k in season_ranks.keys()])) if season_ranks else "N/A"
        rating = self._safe_get(season_ranks, [latest_season, 'rating'], "N/A")
        rating_display = f"{rating:,}" if isinstance(rating, int) else rating
        total_members = self._safe_get(data, ['total_members'], 0)
        online_players_list = self._safe_get(data, ['online_players'], [])
        online_players_table, online_count = self._create_online_players_table(online_players_list)
        description = f"""[公式サイトへのリンク](https://wynncraft.com/stats/guild/{quote(name)})\n```python\nOwner: {owner}\nCreated on: {created_date}\nLevel: {level} [{xp_percent}%]\nWar count: {wars}\nLatest SR: {rating_display} [Season {latest_season}]\nTerritory count: {territories}\nMembers: {total_members}\nOnline Players: {online_count}/{total_members}\n{online_players_table}\n```"""
        embed = discord.Embed(description=description, color=EMBED_COLOR_BLUE)
        embed.title = f"[{prefix}] {name}"
        footer_text = f"Requested by {interaction.user.display_name}"
        if from_cache: footer_text += " | ⚡️Data from Cache"
        if is_stale: footer_text += " (古いデータ)"
        embed.set_footer(text=footer_text)
        return embed

    @app_commands.command(name="guild", description="ギルドの詳細情報を表示します。")
    @app_commands.describe(guild="ギルド名またはプレフィックス")
    async def guild(self, interaction: discord.Interaction, guild: str):
        await interaction.response.defer()
        cache_key = f"guild_{guild.upper()}"
        
        cached_data = self.cache.get_cache(cache_key)
        if cached_data:
            logger.info(f"--- [Cache] ギルド'{guild}'のキャッシュを使用しました。")
            embed = self._create_guild_embed(cached_data, interaction, from_cache=True, is_stale=False)
            await interaction.followup.send(embed=embed)
            return

        logger.info(f"--- [API] ギルド'{guild}'のデータをAPIから取得します。")
        api_data = await self.wynn_api.get_nori_guild_data(guild)

        if api_data and 'name' in api_data:
            self.cache.set_cache(cache_key, api_data)
            embed = self._create_guild_embed(api_data, interaction, from_cache=False, is_stale=False)
            await interaction.followup.send(embed=embed)
            return

        stale_cache = self.cache.get_cache(cache_key, ignore_freshness=True)
        if stale_cache:
            logger.warning(f"--- [API] APIアクセスに失敗。ギルド'{guild}'の古いキャッシュを使用。")
            embed = self._create_guild_embed(stale_cache, interaction, from_cache=True, is_stale=True)
            await interaction.followup.send(embed=embed)
            return
            
        await interaction.followup.send(f"ギルド「{guild}」が見つかりませんでした。APIが応答しないか、存在しないギルドです。")

async def setup(bot: commands.Bot):
    await bot.add_cog(GuildCog(bot))
