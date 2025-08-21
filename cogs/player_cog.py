import discord
from discord import app_commands
from discord.ext import commands
import logging
import os
from datetime import datetime, timezone, timedelta

from lib.wynncraft_api import WynncraftAPI
from config import AUTHORIZED_USER_IDS
from lib.cache_handler import CacheHandler
from lib.banner_renderer import BannerRenderer
from lib.profile_renderer import generate_profile_card

logger = logging.getLogger(__name__)

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
                elif raw_support_rank and raw_support_rank.lower() == "heroplus":
                    rank_display = "Hero+"
                else:
                    rank_display = (raw_support_rank or 'None').capitalize()

                stored_name = player_info.get('username', 'Unknown')
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
        data = await self.cog_instance.wynn_api.get_official_player_data(selected_uuid)
        if not data or 'uuid' not in data:
            await interaction.message.edit(content="選択されたプレイヤーの情報を取得できませんでした。", embed=None, view=None)
            return

        def safe_get(d, keys, default="???"):
            v = d
            for k in keys:
                if not isinstance(v, dict):
                    return default
                v = v.get(k)
                if v is None:
                    return default
            return v

        # fallback_statはglobalDataのみ参照
        def fallback_stat(data, keys_global, default="???"):
            val = safe_get(data, keys_global, None)
            if val is not None:
                return val
            return default

        # --- レイド数取得専用 ---
        def get_raid_stat(data, raid_key):
            global_data = data.get("globalData")
            if not global_data or not isinstance(global_data, dict):
                return "???"
            raids = global_data.get("raids")
            if not raids or not isinstance(raids, dict):
                return "???"
            raid_list = raids.get("list")
            if raid_list == {}:
                return 0
            if not raid_list or not isinstance(raid_list, dict):
                return "???"
            # キーが無ければ未プレイ
            return raid_list.get(raid_key, 0)

        raw_support_rank = safe_get(data, ['supportRank'], "None")
        if raw_support_rank and raw_support_rank.lower() == "vipplus":
            support_rank_display = "Vip+"
        elif raw_support_rank and raw_support_rank.lower() == "heroplus":
            support_rank_display = "Hero+"
        else:
            support_rank_display = (raw_support_rank or 'None').capitalize()

        first_join_str = safe_get(data, ['firstJoin'], "???")
        first_join_date = first_join_str.split('T')[0] if first_join_str and 'T' in first_join_str else first_join_str

        last_join_str = safe_get(data, ['lastJoin'], "???")
        if last_join_str and isinstance(last_join_str, str) and 'T' in last_join_str:
            try:
                last_join_dt = datetime.fromisoformat(last_join_str.replace('Z', '+00:00'))
                last_join_date = last_join_dt.strftime('%Y-%m-%d')
            except Exception:
                last_join_date = last_join_str.split('T')[0]
        else:
            last_join_date = last_join_str if last_join_str else "???"

        guild_prefix = safe_get(data, ['guild', 'prefix'], "")
        guild_name = safe_get(data, ['guild', 'name'], "")
        guild_rank = safe_get(data, ['guild', 'rank'], "")
        guild_data = await self.cog_instance.wynn_api.get_guild_by_prefix(guild_prefix)
        banner_bytes = self.cog_instance.banner_renderer.create_banner_image(guild_data.get('banner') if guild_data and isinstance(guild_data, dict) else None)

        is_online = self._safe_get(data, ['online'], False)
        server = self._safe_get(data, ['server'], "???")
        if is_online:
            server_display = f"Online on {server}"
        else:
            server_display = "Offline"

        char_obj = self._safe_get(data, ['characters', active_char_uuid], {})
        char_type = self._safe_get(char_obj, ['type'])
        nickname = self._safe_get(char_obj, ['nickname'])
        reskin = self._safe_get(char_obj, ['reskin'])
        if reskin != "N/A":
            active_char_info = f"{reskin} ({nickname})"
        else:
            active_char_info = f"{char_type} ({nickname})"

        # globalData系ステータス
        mobs_killed = fallback_stat(data, ['globalData', 'mobsKilled'])
        playtime = data.get("playtime", "???") if data.get("playtime", None) is not None else "???"
        wars = fallback_stat(data, ['globalData', 'wars'])
        quests = fallback_stat(data, ['globalData', 'completedQuests'])
        world_events = fallback_stat(data, ['globalData', 'worldEvents'])
        total_level = fallback_stat(data, ['globalData', 'totalLevel'])
        chests = fallback_stat(data, ['globalData', 'chestsFound'])
        pvp_kill = str(safe_get(data, ['globalData', 'pvp', 'kills'], "???"))
        pvp_death = str(safe_get(data, ['globalData', 'pvp', 'deaths'], "???"))
        dungeons = fallback_stat(data, ['globalData', 'dungeons', 'total'])
        all_raids = fallback_stat(data, ['globalData', 'raids', 'total'])

        # war_rank_displayのみranking参照
        war_rank_display = safe_get(data, ['ranking', 'warsCompletion'], "???")

        # レイド数系
        notg = get_raid_stat(data, 'Nest of the Grootslangs')
        nol = get_raid_stat(data, "Orphion's Nexus of Light")
        tcc = get_raid_stat(data, 'The Canyon Colossus')
        tna = get_raid_stat(data, 'The Nameless Anomaly')

        uuid = data.get("uuid")

        profile_info = {
            "username": data.get("username"),
            "support_rank_display": support_rank_display,
            "guild_prefix": guild_prefix,
            "banner_bytes": banner_bytes,
            "guild_name": guild_name,
            "guild_rank": guild_rank,
            "server_display": server_display,
            "active_char_info": active_char_info,
            "first_join": first_join_date,
            "last_join": last_join_date,
            "mobs_killed": mobs_killed,
            "playtime": playtime,
            "wars": wars,
            "war_rank_display": war_rank_display,
            "quests": quests,
            "world_events": world_events,
            "total_level": total_level,
            "chests": chests,
            "pvp_kill": pvp_kill,
            "pvp_death": pvp_death,
            "notg": notg,
            "nol": nol,
            "tcc": tcc,
            "tna": tna,
            "dungeons": dungeons,
            "all_raids": all_raids,
            "uuid": uuid,
        }

        output_path = f"profile_card_{profile_info['uuid']}.png" if profile_info['uuid'] else "profile_card.png"
        try:
            generate_profile_card(profile_info, output_path)
            file = discord.File(output_path, filename=os.path.basename(output_path))
            await interaction.message.edit(content=None, attachments=[file], embed=None, view=None)
            if os.path.exists(output_path):
                os.remove(output_path)
        except Exception as e:
            logger.error(f"画像生成または送信失敗: {e}")
            await interaction.message.edit(content="プロフィール画像生成に失敗しました。", embed=None, view=None)

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
        return v if v is not None else default

    def _fallback_stat(self, data: dict, keys_global: list, default="???"):
        val = self._safe_get(data, keys_global, None)
        if val is not None:
            return val
        return default

    def _get_raid_stat(self, data: dict, raid_key: str):
        global_data = data.get("globalData")
        if not global_data or not isinstance(global_data, dict):
            return "???"
        raids = global_data.get("raids")
        if not raids or not isinstance(raids, dict):
            return "???"
        raid_list = raids.get("list")
        if raid_list == {}:
            return 0
        if not raid_list or not isinstance(raid_list, dict):
            return "???"
        return raid_list.get(raid_key, 0)

    @app_commands.command(name="player", description="プレイヤーのステータスを表示")
    @app_commands.describe(player="MCID or UUID")
    async def player(self, interaction: discord.Interaction, player: str):
        await interaction.response.defer()
        if interaction.user.id not in AUTHORIZED_USER_IDS:
            await interaction.followup.send("sbadkita")
            return

        cache_key = f"player_{player.lower()}"
        cached_data = self.cache.get_cache(cache_key)
        if cached_data:
            data = cached_data
        else:
            data = await self.wynn_api.get_official_player_data(player)
            if not data or (isinstance(data, dict) and "error" in data and data.get("error") != "MultipleObjectsReturned"):
                await interaction.followup.send(f"プレイヤー「{player}」が見つかりませんでした。")
                return

            if isinstance(data, dict) and data.get("error") == "MultipleObjectsReturned" and "objects" in data:
                player_collision_dict = data["objects"]
                view = PlayerSelectView(player_collision_dict=player_collision_dict, cog_instance=self, owner_id=interaction.user.id)
                if hasattr(view, "select_menu") and view.select_menu.options:
                    await interaction.followup.send(
                        "複数のプレイヤーが見つかりました。どちらの情報を表示しますか？", view=view
                    )
                else:
                    await interaction.followup.send(f"プレイヤー「{player}」が見つかりませんでした。")
                return
            if isinstance(data, dict) and 'username' in data:
                self.cache.set_cache(cache_key, data)
            else:
                await interaction.followup.send(f"プレイヤー「{player}」が見つかりませんでした。")
                return

        def safe_get(d, keys, default="???"):
            v = d
            for k in keys:
                if not isinstance(v, dict):
                    return default
                v = v.get(k)
                if v is None:
                    return default
            return v

        raw_support_rank = safe_get(data, ['supportRank'], "None")
        if raw_support_rank and raw_support_rank.lower() == "vipplus":
            support_rank_display = "Vip+"
        elif raw_support_rank and raw_support_rank.lower() == "heroplus":
            support_rank_display = "Hero+"
        else:
            support_rank_display = (raw_support_rank or 'None').capitalize()

        first_join_str = safe_get(data, ['firstJoin'], "???")
        first_join_date = first_join_str.split('T')[0] if first_join_str and 'T' in first_join_str else first_join_str

        last_join_str = safe_get(data, ['lastJoin'], "???")
        if last_join_str and isinstance(last_join_str, str) and 'T' in last_join_str:
            try:
                last_join_dt = datetime.fromisoformat(last_join_str.replace('Z', '+00:00'))
                last_join_date = last_join_dt.strftime('%Y-%m-%d')
            except Exception:
                last_join_date = last_join_str.split('T')[0]
        else:
            last_join_date = last_join_str if last_join_str else "???"

        guild_prefix = safe_get(data, ['guild', 'prefix'], "")
        guild_name = safe_get(data, ['guild', 'name'], "")
        guild_rank = safe_get(data, ['guild', 'rank'], "")
        guild_data = await self.wynn_api.get_guild_by_prefix(guild_prefix)
        banner_bytes = self.banner_renderer.create_banner_image(guild_data.get('banner') if guild_data and isinstance(guild_data, dict) else None)

        is_online = self._safe_get(data, ['online'], False)
        server = self._safe_get(data, ['server'], "???")
        if is_online:
            server_display = f"Online on {server}"
        else:
            server_display = "Offline"

        char_obj = self._safe_get(data, ['characters', active_char_uuid], {})
        char_type = self._safe_get(char_obj, ['type'])
        nickname = self._safe_get(char_obj, ['nickname'])
        reskin = self._safe_get(char_obj, ['reskin'])
        if reskin != "N/A":
            active_char_info = f"{reskin} ({nickname})"
        else:
            active_char_info = f"{char_type} ({nickname})"

        mobs_killed = self._fallback_stat(data, ['globalData', 'mobsKilled'])
        playtime = data.get("playtime", "???") if data.get("playtime", None) is not None else "???"
        wars = self._fallback_stat(data, ['globalData', 'wars'])
        quests = self._fallback_stat(data, ['globalData', 'completedQuests'])
        world_events = self._fallback_stat(data, ['globalData', 'worldEvents'])
        total_level = self._fallback_stat(data, ['globalData', 'totalLevel'])
        chests = self._fallback_stat(data, ['globalData', 'chestsFound'])
        pvp_kill = str(safe_get(data, ['globalData', 'pvp', 'kills'], "???"))
        pvp_death = str(safe_get(data, ['globalData', 'pvp', 'deaths'], "???"))
        dungeons = self._fallback_stat(data, ['globalData', 'dungeons', 'total'])
        all_raids = self._fallback_stat(data, ['globalData', 'raids', 'total'])

        war_rank_display = safe_get(data, ['ranking', 'warsCompletion'], "???")

        notg = self._get_raid_stat(data, 'Nest of the Grootslangs')
        nol = self._get_raid_stat(data, "Orphion's Nexus of Light")
        tcc = self._get_raid_stat(data, 'The Canyon Colossus')
        tna = self._get_raid_stat(data, 'The Nameless Anomaly')

        uuid = data.get("uuid")

        profile_info = {
            "username": data.get("username"),
            "support_rank_display": support_rank_display,
            "guild_prefix": guild_prefix,
            "banner_bytes": banner_bytes,
            "guild_name": guild_name,
            "guild_rank": guild_rank,
            "server_display": server_display,
            "active_char_info": active_char_info,
            "first_join": first_join_date,
            "last_join": last_join_date,
            "mobs_killed": mobs_killed,
            "playtime": playtime,
            "wars": wars,
            "war_rank_display": war_rank_display,
            "quests": quests,
            "world_events": world_events,
            "total_level": total_level,
            "chests": chests,
            "pvp_kill": pvp_kill,
            "pvp_death": pvp_death,
            "notg": notg,
            "nol": nol,
            "tcc": tcc,
            "tna": tna,
            "dungeons": dungeons,
            "all_raids": all_raids,
            "uuid": uuid,
        }

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
