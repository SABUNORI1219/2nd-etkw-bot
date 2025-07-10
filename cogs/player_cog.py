import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timezone, timedelta
import logging

# libとconfigから必要なものをインポート
from lib.wynncraft_api import WynncraftAPI
from lib.cache_handler import CacheHandler
from config import EMBED_COLOR_GREEN

logger = logging.getLogger(__name__)

class PlayerSelectView(discord.ui.View):
    def __init__(self, player_collision_dict: dict, cog_instance):
        super().__init__(timeout=60.0)
        self.cog_instance = cog_instance
        options = []
        for uuid, player_info in player_collision_dict.items():
            if isinstance(player_info, dict):
                raw_support_rank = player_info.get('supportRank')
                rank_display = "Vip+" if raw_support_rank and raw_support_rank.lower() == "vipplus" else (raw_support_rank or 'Player').capitalize()
                stored_name = player_info.get('storedName', 'Unknown')
                label_text = f"{stored_name} [{rank_display}]"
                options.append(discord.SelectOption(label=label_text, value=uuid, description=f"UUID: {uuid}"))
        if options:
            self.select_menu = discord.ui.Select(placeholder="プレイヤーを選択してください...", options=options)
            self.select_menu.callback = self.select_callback
            self.add_item(self.select_menu)

    async def select_callback(self, interaction: discord.Interaction):
        selected_uuid = self.select_menu.values[0]
        await interaction.response.edit_message(content="プレイヤー情報を取得中...", view=None)
        # 選択後の処理も、キャッシュを考慮したplayerコマンド本体に任せる
        await self.cog_instance.player(interaction, player=selected_uuid, is_followup=True)

class PlayerCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.wynn_api = WynncraftAPI()
        self.cache = CacheHandler()
        logger.info("--- [CommandsCog] プレイヤーCogが読み込まれました。")

    def _safe_get(self, data: dict, keys: list, default: any = "N/A"):
        for key in keys:
            if not isinstance(data, dict): return default
            data = data.get(key)
        return data if data is not None else default

    def _create_player_embed(self, data: dict, interaction: discord.Interaction, from_cache: bool, is_stale: bool) -> discord.Embed:
        username = self._safe_get(data, ['username'])
        uuid = self._safe_get(data, ['uuid'])
        raw_support_rank = self._safe_get(data, ['supportRank'], "Player")
        support_rank_display = "Vip+" if raw_support_rank and raw_support_rank.lower() == "vipplus" else raw_support_rank.capitalize()
        is_online = self._safe_get(data, ['online'], False)
        server = self._safe_get(data, ['server'], "Offline")
        guild_name = self._safe_get(data, ['guild', 'name'], "N/A")
        guild_prefix = self._safe_get(data, ['guild', 'prefix'], "")
        guild_rank = self._safe_get(data, ['guild', 'rank'], "")
        guild_rank_stars = self._safe_get(data, ['guild', 'rankStars'], "")
        guild_display = f"[{guild_prefix}] {guild_name} / {guild_rank}[{guild_rank_stars}]" if guild_name != "N/A" else "N/A"
        first_join = self._safe_get(data, ['firstJoin'], "N/A").split('T')[0]
        last_join_str = self._safe_get(data, ['lastJoin'], "1970-01-01T00:00:00.000Z")
        last_join_dt = datetime.fromisoformat(last_join_str.replace('Z', '+00:00'))
        time_diff = datetime.now(timezone.utc) - last_join_dt
        server_value_for_stream = self._safe_get(data, ['server'], None)
        stream_status = "🟢Stream" if not is_online and server_value_for_stream is None and time_diff.total_seconds() < 60 else "❌Stream"
        last_join_display = f"{last_join_str.split('T')[0]} [{stream_status}]"
        active_char_uuid = self._safe_get(data, ['activeCharacter'])
        char_obj = self._safe_get(data, ['characters', active_char_uuid], {})
        char_type = self._safe_get(char_obj, ['type'])
        nickname = self._safe_get(char_obj, ['nickname'])
        reskin = self._safe_get(char_obj, ['reskin'])
        active_char_info = f"{reskin} ({nickname}) on {server}" if reskin != "N/A" else f"{char_type} ({nickname}) on {server}"
        killed_mobs = self._safe_get(data, ['globalData', 'killedMobs'], 0)
        chests_found = self._safe_get(data, ['globalData', 'chestsFound'], 0)
        playtime = self._safe_get(data, ['playtime'], 0)
        wars = self._safe_get(data, ['globalData', 'wars'], 0)
        war_rank = self._safe_get(data, ['ranking', 'warsCompletion'], 'N/A')
        war_rank_display = f"#{war_rank:,}" if isinstance(war_rank, int) else war_rank
        pvp_kills = self._safe_get(data, ['globalData', 'pvp', 'kills'], 0)
        pvp_deaths = self._safe_get(data, ['globalData', 'pvp', 'deaths'], 0)
        quests = self._safe_get(data, ['globalData', 'completedQuests'], 0)
        total_level = self._safe_get(data, ['globalData', 'totalLevel'], 0)
        raid_list = self._safe_get(data, ['globalData', 'raids', 'list'], {})
        notg = self._safe_get(raid_list, ["Nest of the Grootslangs"], 0)
        nol = self._safe_get(raid_list, ["Orphion's Nexus of Light"], 0)
        tcc = self._safe_get(raid_list, ["The Canyon Colossus"], 0)
        tna = self._safe_get(raid_list, ["The Nameless Anomaly"], 0)
        dungeons = self._safe_get(data, ['globalData', 'dungeons', 'total'], 0)
        total_raids = self._safe_get(data, ['globalData', 'raids', 'total'], 0)
        description = f"""[公式サイトへのリンク](https://wynncraft.com/stats/player/{username})\n```python\n[{support_rank_display}] {username} is {'online' if is_online else 'offline'}\nActive Character: {active_char_info}\nGuild: {guild_display}\nFirst Joined: {first_join}\nLast Seen: {last_join_display}\nMobs Killed: {killed_mobs:,}\nChests Looted: {chests_found:,}\nPlaytime: {playtime:,} hours\nWar Count: {wars:,} [{war_rank_display}]\nPvP: {pvp_kills:,} K / {pvp_deaths:,} D\nQuests Total: {quests:,}\nTotal Level: {total_level:,}\n╔═══════════╦════════╗\n║  Content  ║ Clears ║\n╠═══════════╬════════╣\n║ NOTG      ║ {notg:>6,} ║\n║ NOL       ║ {nol:>6,} ║\n║ TCC       ║ {tcc:>6,} ║\n║ TNA       ║ {tna:>6,} ║\n║ Dungeons  ║ {dungeons:>6,} ║\n║ All Raids ║ {total_raids:>6,} ║\n╚═══════════╩════════╝\n```\n**UUID: {uuid}**"""
        color = EMBED_COLOR_GREEN if is_online else discord.Color.dark_red()
        embed = discord.Embed(description=description, color=color)
        embed.title = f"{username}"
        embed.set_thumbnail(url=f"https://www.mc-heads.net/body/{username}/right")
        footer_text = f"Requested by {interaction.user.display_name}"
        if from_cache: footer_text += " | ⚡️Data from Cache"
        if is_stale: footer_text += " (古いデータ)"
        embed.set_footer(text=footer_text, icon_url=f"https://www.mc-heads.net/avatar/{username}")
        return embed

    @app_commands.command(name="player", description="プレイヤーのステータスを表示します。")
    @app_commands.describe(player="MCID or UUID")
    async def player(self, interaction: discord.Interaction, player: str, is_followup: bool = False):
        if not is_followup: await interaction.response.defer()
        
        responder = interaction.followup if is_followup else interaction.message
        cache_key = f"player_{player.lower()}"
        
        cached_data = self.cache.get_cache(cache_key)
        if cached_data:
            logger.info(f"--- [Cache] プレイヤー'{player}'の新鮮なキャッシュを使用。")
            embed = self._create_player_embed(cached_data, interaction, from_cache=True, is_stale=False)
            await responder.send(embed=embed) if is_followup else await interaction.followup.send(embed=embed)
            return

        logger.info(f"--- [API] プレイヤー'{player}'のデータをAPIから取得します。")
        api_data = await self.wynn_api.get_nori_player_data(player)

        if api_data:
            self.cache.set_cache(cache_key, api_data)
            if isinstance(api_data, dict) and 'username' in api_data:
                embed = self._create_player_embed(api_data, interaction, from_cache=False, is_stale=False)
                await responder.send(embed=embed) if is_followup else await interaction.followup.send(embed=embed)
            elif isinstance(api_data, dict):
                view = PlayerSelectView(player_collision_dict=api_data, cog_instance=self)
                await responder.send("複数のプレイヤーが見つかりました。どちらの情報を表示しますか？", view=view) if is_followup else await interaction.followup.send("複数のプレイヤーが見つかりました。どちらの情報を表示しますか？", view=view)
            else:
                await responder.send(f"プレイヤー「{player}」の情報を正しく取得できませんでした。") if is_followup else await interaction.followup.send(f"プレイヤー「{player}」の情報を正しく取得できませんでした。")
            return

        stale_cache = self.cache.get_cache(cache_key, ignore_freshness=True)
        if stale_cache:
            logger.warning(f"--- [API] APIアクセスに失敗。プレイヤー'{player}'の古いキャッシュを使用。")
            embed = self._create_player_embed(stale_cache, interaction, from_cache=True, is_stale=True)
            await responder.send(embed=embed) if is_followup else await interaction.followup.send(embed=embed)
            return

        await responder.send(f"プレイヤー「{player}」が見つかりませんでした。") if is_followup else await interaction.followup.send(f"プレイヤー「{player}」が見つかりませんでした。")

async def setup(bot: commands.Bot):
    await bot.add_cog(PlayerCog(bot))
