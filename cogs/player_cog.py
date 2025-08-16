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

    def _safe_get(self, data: dict, keys: list, default: any = "N/A"):
        v = data
        for key in keys:
            if not isinstance(v, dict):
                return default
            v = v.get(key)
            if v is None:
                return default
        return v

    def _fallback_stat(self, data: dict, keys_global: list, keys_ranking: list, keys_prev: list, default="非公開"):
        # globalData優先、ranking→previousRanking→default
        val = self._safe_get(data, keys_global, None)
        if val is not None:
            return val
        val = self._safe_get(data, keys_ranking, None)
        if val is not None:
            return val
        val = self._safe_get(data, keys_prev, None)
        if val is not None:
            return val
        return default

    def format_stat(val):
        if isinstance(val, int) or isinstance(val, float):
            return f"{val:,}"
        return str(val)

    def _create_player_embed(self, data: dict) -> discord.Embed:
        username = self._safe_get(data, ['username'])
        escaped_username = discord.utils.escape_markdown(username)
        uuid = self._safe_get(data, ['uuid'])
        raw_support_rank = self._safe_get(data, ['supportRank'], "Player")
        support_rank_display = "Vip+" if raw_support_rank.lower() == "vipplus" else raw_support_rank.capitalize()
        is_online = self._safe_get(data, ['online'], False)
        server = self._safe_get(data, ['server'], "Unknown")

        guild_name = self._safe_get(data, ['guild', 'name'], "N/A")
        guild_prefix = self._safe_get(data, ['guild', 'prefix'], "")
        guild_rank = self._safe_get(data, ['guild', 'rank'], "")
        guild_rank_stars = self._safe_get(data, ['guild', 'rankStars'], "")
        guild_display = f"[{guild_prefix}] {guild_name} / {guild_rank}[{guild_rank_stars}]" if guild_name != "N/A" else "N/A"

        first_join = self._safe_get(data, ['firstJoin'], "N/A")
        first_join_display = first_join.split('T')[0] if first_join != "N/A" else "非公開"

        last_join_str = self._safe_get(data, ['lastJoin'], "1970-01-01T00:00:00.000Z")
        try:
            last_join_dt = datetime.fromisoformat(last_join_str.replace('Z', '+00:00'))
            time_diff = datetime.now(timezone.utc) - last_join_dt
        except Exception:
            last_join_dt = datetime(1970, 1, 1, tzinfo=timezone.utc)
            time_diff = timedelta(days=0)

        server_value_for_stream = self._safe_get(data, ['server'], None)
        stream_status = "🟢Stream" if server_value_for_stream is None and time_diff.total_seconds() < 60 else "❌Stream"
        last_join_display = f"{last_join_str.split('T')[0]} [{stream_status}]" if last_join_str else "非公開"

        restrictions = self._safe_get(data, ['restrictions'], {})
        is_partial_private = False

        # fallback取得
        killed_mobs = self._fallback_stat(data, ['globalData', 'mobsKilled'], ['ranking', 'mobsKilled'], ['previousRanking', 'mobsKilled'])
        if killed_mobs == "非公開": is_partial_private = True
        chests_found = self._fallback_stat(data, ['globalData', 'chestsFound'], ['ranking', 'chestsFound'], ['previousRanking', 'chestsFound'])
        if chests_found == "非公開": is_partial_private = True
        playtime = self._fallback_stat(data, ['playtime'], ['ranking', 'playtime'], ['previousRanking', 'playtime'])
        if playtime == "非公開": is_partial_private = True
        wars = self._fallback_stat(data, ['globalData', 'wars'], ['ranking', 'warsCompletion'], ['previousRanking', 'warsCompletion'])
        if wars == "非公開": is_partial_private = True

        war_rank = self._safe_get(data, ['ranking', 'warsCompletion'], '非公開')
        if war_rank == "非公開": is_partial_private = True
        war_rank_display = f"#{war_rank:,}" if isinstance(war_rank, int) else war_rank

        pvp_kills = self._fallback_stat(data, ['globalData', 'pvp', 'kills'], ['ranking', 'pvpKills'], ['previousRanking', 'pvpKills'])
        pvp_deaths = self._fallback_stat(data, ['globalData', 'pvp', 'deaths'], ['ranking', 'pvpDeaths'], ['previousRanking', 'pvpDeaths'])
        quests = self._fallback_stat(data, ['globalData', 'completedQuests'], ['ranking', 'completedQuests'], ['previousRanking', 'completedQuests'])
        total_level = self._fallback_stat(data, ['globalData', 'totalLevel'], ['ranking', 'totalLevel'], ['previousRanking', 'totalLevel'])

        # Raids/dungeons
        raid_list = self._safe_get(data, ['globalData', 'raids', 'list'], {})
        notg = self._safe_get(raid_list, ["Nest of the Grootslangs"], "非公開")
        nol = self._safe_get(raid_list, ["Orphion's Nexus of Light"], "非公開")
        tcc = self._safe_get(raid_list, ["The Canyon Colossus"], "非公開")
        tna = self._safe_get(raid_list, ["The Nameless Anomaly"], "非公開")
        if notg == "非公開" or nol == "非公開" or tcc == "非公開" or tna == "非公開": is_partial_private = True

        dungeons = self._safe_get(data, ['globalData', 'dungeons', 'total'], "非公開")
        total_raids = self._safe_get(data, ['globalData', 'raids', 'total'], "非公開")
        if dungeons == "非公開" or total_raids == "非公開": is_partial_private = True

        # キャラ情報
        active_char_uuid = self._safe_get(data, ['activeCharacter'])
        char_obj = self._safe_get(data, ['characters', active_char_uuid], {})
        char_type = self._safe_get(char_obj, ['type'], "非公開")
        nickname = self._safe_get(char_obj, ['nickname'], "非公開")
        reskin = self._safe_get(char_obj, ['reskin'], "非公開")
        active_char_info = f"{reskin} ({nickname}) on {server}" if reskin != "非公開" else f"{char_type} ({nickname}) on {server}"

        description = f"""
    [公式サイトへのリンク](https://wynncraft.com/stats/player/{username})
```python
[{support_rank_display}] {username} is {'online' if is_online else 'offline'}
Active Character: {active_char_info}
Guild: {guild_display}
First Joined: {first_join}
Last Seen: {last_join_display}
Mobs Killed: {self.format_stat(killed_mobs)}
Playtime: {self.format_stat(playtime)} hours
War Count: {self.format_stat(wars)} [{war_rank_display}]
PvP: {self.format_stat(pvp_kills)} K / {self.format_stat(pvp_deaths)} D
Quests Total: {self.format_stat(quests)}
Total Level: {self.format_stat(total_level)}
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

        footer_text = f"{username}'s Stats | Minister Chikuwa"
        if is_partial_private:
            footer_text += " | ※一部の情報は非公開です"
        embed.set_footer(
            text=footer_text,
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
            logger.info("[player command] 権限なし")
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

async def setup(bot: commands.Bot): await bot.add_cog(PlayerCog(bot))
