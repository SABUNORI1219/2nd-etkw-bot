import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime
from urllib.parse import quote
from io import BytesIO
import logging

logger = logging.getLogger(__name__)

from lib.wynncraft_api import WynncraftAPI
from lib.cache_handler import CacheHandler
from lib.banner_renderer import BannerRenderer
from config import EMBED_COLOR_BLUE

class GuildCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.wynn_api = WynncraftAPI()
        self.cache = CacheHandler()
        self.banner_renderer = BannerRenderer()
        logger.info("--- [CommandsCog] ギルドコマンドCogが読み込まれました。")

    def _safe_get(self, data: dict, keys: list, default: any = "N/A"):
        """辞書から安全に値を取得するヘルパー関数"""
        for key in keys:
            if not isinstance(data, dict):
                return default
            data = data.get(key)
        return data if data is not None else default

    def _create_online_players_table(self, online_players_list: list) -> tuple[str, int]:
        """オンラインプレイヤーのリストからASCIIテーブルと人数を生成する"""
        
        # ▼▼▼【ロジック修正箇所】APIからのonline_playersリストを直接使う▼▼▼
        if not online_players_list:
            return "（現在オンラインのメンバーはいません）", 0

        # 安全なデータアクセスに修正
        max_name_len = max((len(p.get('name','')) for p in online_players_list), default=6)
        max_server_len = max((len(p.get('server','')) for p in online_players_list), default=2)
        max_rank_len = max((len(p.get('rank','')) for p in online_players_list), default=5)
        
        max_name_len = max(max_name_len, 6)
        max_server_len = max(max_server_len, 2)
        max_rank_len = max(max_rank_len, 5)
        
        header = f"║ {'WC'.center(max_server_len)} ║ {'Player'.center(max_name_len)} ║ {'Rank'.center(max_rank_len)} ║"
        divider = f"╠═{'═'*max_server_len}═╬═{'═'*max_name_len}═╬═{'═'*max_rank_len}═╣"
        top_border = f"╔═{'═'*max_server_len}═╦═{'═'*max_name_len}═╦═{'═'*max_rank_len}═╗"
        bottom_border = f"╚═{'═'*max_server_len}═╩═{'═'*max_name_len}═╩═{'═'*max_rank_len}═╝"

        player_rows = []
        for p in sorted(online_players_list, key=lambda x: len(x.get('rank', '')), reverse=True):
            server = p.get('server', 'N/A').center(max_server_len)
            name = p.get('name', 'N/A').center(max_name_len)
            rank = p.get('rank', '').ljust(max_rank_len)
            player_rows.append(f"║ {server} ║ {name} ║ {rank} ║")

        return "\n".join([top_border, header, divider] + player_rows + [bottom_border]), len(online_players_list)

    def _create_guild_embed(self, data: dict, interaction: discord.Interaction, from_cache: bool = False, is_stale: bool = False) -> discord.Embed:
        name = self._safe_get(data, ['name'])
        encoded_name = quote(name)
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
        
        # ▼▼▼【ロジック修正箇所】正しいデータソースを参照する▼▼▼
        total_members = self._safe_get(data, ['total_members'], 0)
        online_players_list = self._safe_get(data, ['online_players'], []) # online_playersリストを直接取得
        online_players_table, online_count = self._create_online_players_table(online_players_list)
        # ▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲
        
        # 埋め込みメッセージを作成
        description = f"""
    [公式サイトへのリンク](https://wynncraft.com/stats/guild/{encoded_name})
```python
Owner: {owner}
Created on: {created_date}
Level: {level} [{xp_percent}%]
War count: {wars}
Latest SR: {rating_display} [Season {latest_season}]
Territory count: {territories}
Members: {total_members}
Online Players: {online_count}/{total_members}
{online_players_table}
```
"""
        embed = discord.Embed(
            description=description,
            color=EMBED_COLOR_BLUE
        )
        
        embed.title = f"[{prefix}] {name}"
        
        embed.set_footer(text=f"{name}'s Stats | Minister Chikuwa")

        return embed

    @app_commands.checks.cooldown(1, 5.0, key=lambda i: i.user.id)
    @app_commands.command(name="guild", description="ギルドの詳細情報を表示")
    @app_commands.describe(guild="Name or Prefix")
    async def guild(self, interaction: discord.Interaction, guild: str):
        await interaction.response.defer()

        cache_key = f"nori_{guild.upper()}" # のりAPIの方のキャッシュ
        cache_guild = f"official_{guild.upper()}" # 公式APIの方のキャッシュ
        
        data_to_use = None
        from_cache = False
        is_stale = False
        guild_data = None
        
        # --- ステップ1: まずキャッシュを確認 ---
        cached_guild_data = self.cache.get_cache(cache_guild)
        if cached_guild_data:
            logger.info(f"--- [Cache] ギルド'{guild}'のキャッシュを使用します。")
            guild_data = cached_guild_data
            from_cache = True
        
        # --- ステップ2: キャッシュがなければ、二段構えでAPIを検索 ---
        if not guild_data:
            # まずプレフィックスとして検索
            logger.info(f"--- [API] プレフィックス '{guild}' として検索します...")
            data_as_prefix = await self.wynn_api.get_guild_by_prefix(guild)
            if data_as_prefix and data_as_prefix.get('name'):
                guild_data = data_as_prefix
                logger.info(f"--- [GuildCmd] ✅ プレフィックスとして'{guild}'が見つかりました。")
            else:
                # 見つからなければフルネームで再検索
                logger.info(f"--- [API] プレフィックスとして見つからず。フルネーム '{guild}' として再検索します...")
                data_as_name = await self.wynn_api.get_guild_by_name(guild)
                if data_as_name and data_as_name.get('name'):
                    guild_data = data_as_name
                    logger.info(f"--- [GuildCmd] ✅ フルネームとして'{guild}'が見つかりました。")

            # APIでデータが取得できたら、キャッシュに保存
            if guild_data:
                self.cache.set_cache(cache_guild, guild_data)

        # 1. キャッシュを探す
        cached_data = self.cache.get_cache(cache_key)
        if cached_data:
            logger.info(f"--- [Cache] ギルド'{guild}'のキャッシュを使用しました。")
            data_to_use = cached_data
            from_cache = True
        else:
            # 2. キャッシュがなければAPIを叩く
            logger.info(f"--- [API] ギルド'{guild}'のデータをAPIから取得します。")
            api_data = await self.wynn_api.get_nori_guild_data(guild)
            if api_data and 'name' in api_data:
                self.cache.set_cache(cache_key, api_data)
                data_to_use = api_data
            else:
                # 3. APIがダメなら古いキャッシュを探す
                stale_cache = self.cache.get_cache(cache_key, ignore_freshness=True)
                if stale_cache:
                    logger.warning(f"--- [API] APIアクセスに失敗。ギルド'{guild}'の古いキャッシュを使用。")
                    data_to_use = stale_cache
                    from_cache = True
                    is_stale = True

        # 4. データが何もなければ、ここで終了
        if not data_to_use:
            await interaction.edit_original_response(
                content=f"ギルド「{guild}」が見つかりませんでした。",
                ephemeral=True
            )
            return

        embed = self._create_guild_embed(data_to_use, interaction, from_cache, is_stale)
        banner_bytes = self.banner_renderer.create_banner_image(guild_data.get('banner'))

        if banner_bytes:
            banner_file = discord.File(fp=banner_bytes, filename="guild_banner.png")
            embed.set_thumbnail(url="attachment://guild_banner.png")
            logger.info(f"--- [ばなー] バナーの画像生成に成功！")
            await interaction.followup.send(embed=embed, file=banner_file)
        else:
            logger.error(f"--- [ばなー] バナーの画像生成に失敗！")
            await interaction.followup.send(embed=embed)

            
# BotにCogを登録するためのセットアップ関数
async def setup(bot: commands.Bot):
    await bot.add_cog(GuildCog(bot))
