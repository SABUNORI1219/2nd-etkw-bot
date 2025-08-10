import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timezone, timedelta
import logging

logger = logging.getLogger(__name__)

from lib.wynncraft_api import WynncraftAPI
from config import EMBED_COLOR_BLUE, EMBED_COLOR_GREEN, AUTHORIZED_USER_IDS
from lib.cache_handler import CacheHandler

class PlayerSelectView(discord.ui.View):
    def __init__(self, player_collision_dict: dict, cog_instance, owner_id):
        super().__init__(timeout=60.0)
        self.cog_instance = cog_instance
        self.owner_id = owner_id

        options = []
        for uuid, player_info in player_collision_dict.items():
            if isinstance(player_info, dict):
                
                raw_support_rank = player_info.get('supportRank')
                if raw_support_rank and raw_support_rank.lower() == "vipplus":
                    rank_display = "Vip+"
                else:
                    rank_display = (raw_support_rank or 'Player').capitalize()

                stored_name = player_info.get('storedName', 'Unknown')
                label_text = f"{stored_name} [{rank_display}]"
                
                options.append(discord.SelectOption(
                    label=label_text, 
                    value=uuid,
                    description=f"UUID: {uuid}"
                ))

        if options:
            self.select_menu = discord.ui.Select(placeholder="プレイヤーを選択してください...", options=options)
            self.select_menu.callback = self.select_callback
            self.add_item(self.select_menu)
            
    async def select_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                "この操作はコマンドを実行したユーザーのみ有効です。", ephemeral=True
            )
            return
        selected_uuid = self.select_menu.values[0]
        
        self.select_menu.disabled = True
        await interaction.response.edit_message(content="プレイヤー情報を取得中...", view=self)
        
        data = await self.cog_instance.wynn_api.get_nori_player_data(selected_uuid)
        
        if not data or 'uuid' not in data:
            await interaction.message.edit(content="選択されたプレイヤーの情報を取得できませんでした。", embed=None, view=None)
            return
            
        embed = self.cog_instance._create_player_embed(data)
        await interaction.message.edit(content=None, embed=embed, view=None)

class PlayerCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.wynn_api = WynncraftAPI()
        self.cache = CacheHandler()
        logger.info("--- [CommandsCog] プレイヤーCogが読み込まれました。")

    # 指定されたデータを安全に取得するためのヘルパー関数
    def _safe_get(self, data: dict, keys: list, default: any = "N/A"):
        for key in keys:
            if not isinstance(data, dict):
                return default
            data = data.get(key)
        return data if data is not None else default

    def _create_player_embed(self, data: dict) -> discord.Embed:
        username = self._safe_get(data, ['username'])
        escaped_username = discord.utils.escape_markdown(username)
        
        uuid = self._safe_get(data, ['uuid'])
        raw_support_rank = self._safe_get(data, ['supportRank'], "Player")
        if raw_support_rank.lower() == "vipplus":
            support_rank_display = "Vip+"
        else:
            support_rank_display = raw_support_rank.capitalize()
        is_online = self._safe_get(data, ['online'], False)
        server = self._safe_get(data, ['server'], "Unknown")
        
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

        # serverがnull、かつ最終ログインが1分以内(60秒)の場合のみストリーム中と判断
        if server_value_for_stream is None and time_diff.total_seconds() < 60:
            stream_status = "🟢Stream"
        else:
            stream_status = "❌Stream"
        
        last_join_display = f"{last_join_str.split('T')[0]} [{stream_status}]"

        active_char_uuid = self._safe_get(data, ['activeCharacter'])
        
        char_obj = self._safe_get(data, ['characters', active_char_uuid], {})
        char_type = self._safe_get(char_obj, ['type'])
        nickname = self._safe_get(char_obj, ['nickname'])
        reskin = self._safe_get(char_obj, ['reskin'])

        if reskin != "N/A":
            active_char_info = f"{reskin} ({nickname}) on {server}"
        else:
            active_char_info = f"{char_type} ({nickname}) on {server}"

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

        description = f"""
    [公式サイトへのリンク](https://wynncraft.com/stats/player/{username})
```python
[{support_rank_display}] {username} is {'online' if is_online else 'offline'}
Active Character: {active_char_info}
Guild: {guild_display}
First Joined: {first_join}
Last Seen: {last_join_display}
Mobs Killed: {killed_mobs:,}
Chests Looted: {chests_found:,}
Playtime: {playtime:,} hours
War Count: {wars:,} [{war_rank_display}]
PvP: {pvp_kills:,} K / {pvp_deaths:,} D
Quests Total: {quests:,}
Total Level: {total_level:,}
╔═══════════╦════════╗
║  Content  ║ Clears ║
╠═══════════╬════════╣
║ NOTG      ║ {notg:>6,} ║
║ NOL       ║ {nol:>6,} ║
║ TCC       ║ {tcc:>6,} ║
║ TNA       ║ {tna:>6,} ║
║ Dungeons  ║ {dungeons:>6,} ║
║ All Raids ║ {total_raids:>6,} ║
╚═══════════╩════════╝
```
**UUID: {uuid}**
"""
        color = discord.Color.green() if is_online else discord.Color.dark_red()
        embed = discord.Embed(
            description=description,
            color=color
        )
        
        embed.title = f"{escaped_username}"
        
        embed.set_thumbnail(url=f"https://www.mc-heads.net/body/{uuid}/right")
        
        embed.set_footer(
            text=f"{username}'s Stats | Minister Chikuwa",
            icon_url=f"https://www.mc-heads.net/avatar/{uuid}"
        )
        return embed

    @app_commands.checks.cooldown(1, 5.0, key=lambda i: i.user.id)
    @app_commands.command(name="player", description="プレイヤーのステータスを表示")
    @app_commands.describe(player="MCID or UUID")
    async def player(self, interaction: discord.Interaction, player: str):
        await interaction.response.defer()

        # 権限チェック
        if interaction.user.id not in AUTHORIZED_USER_IDS:
            await interaction.followup.send(
                "`/player`コマンドは現在APIの仕様変更によりリワーキング中です。\n"
                "`/player` command is reworking due to API feature rework right now."
            )
            return

        cache_key = f"player_{player.lower()}"
        cached_data = self.cache.get_cache(cache_key)
        if cached_data:
            logger.info(f"--- [Cache] プレイヤー'{player}'のキャッシュを使用しました。")
            embed = self._create_player_embed(cached_data)
            await interaction.followup.send(embed=embed)
            return

        logger.info(f"--- [API] プレイヤー'{player}'のデータをAPIから取得します。")
        api_data = await self.wynn_api.get_official_player_data(player)

        # 1. エラー返却なら即「見つかりませんでした」
        if not api_data or (isinstance(api_data, dict) and "Error" in api_data):
            await interaction.followup.send(f"プレイヤー「{player}」が見つかりませんでした。")
            return

        # 2. 単一プレイヤーデータ（usernameキーあり）ならembed
        if isinstance(api_data, dict) and 'username' in api_data:
            embed = self._create_player_embed(api_data)
            self.cache.set_cache(cache_key, api_data)
            await interaction.followup.send(embed=embed)
            return

        # 3. UUIDキーのみ1件ならembed
        if (
            isinstance(api_data, dict) and
            all(len(k) == 36 for k in api_data.keys()) and
            len(api_data) == 1 and
            all(isinstance(v, dict) for v in api_data.values())
        ):
            player_data = list(api_data.values())[0]
            embed = self._create_player_embed(player_data)
            await interaction.followup.send(embed=embed)
            return

        # 4. UUIDキーのみ2件以上・値が全部dictならView。空ならエラー
        if (
            isinstance(api_data, dict) and
            all(len(k) == 36 for k in api_data.keys()) and
            len(api_data) >= 2 and
            all(isinstance(v, dict) for v in api_data.values())
        ):
            view = PlayerSelectView(player_collision_dict=api_data, cog_instance=self, owner_id=interaction.user.id)
            # optionsが実際にあるかチェック
            if hasattr(view, "select_menu") and view.select_menu.options:
                await interaction.followup.send("複数のプレイヤーが見つかりました。どちらの情報を表示しますか？", view=view)
            else:
                await interaction.followup.send(f"プレイヤー「{player}」が見つかりませんでした。")
            return

        # 5. それ以外は全部「見つかりませんでした」
        await interaction.followup.send(f"プレイヤー「{player}」が見つかりませんでした。")

# BotにCogを登録するためのセットアップ関数
async def setup(bot: commands.Bot):
    await bot.add_cog(PlayerCog(bot))
