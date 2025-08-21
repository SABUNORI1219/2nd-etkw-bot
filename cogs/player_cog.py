import discord
from discord import app_commands
from discord.ext import commands
import logging
import os
from datetime import datetime

from lib.wynncraft_api import WynncraftAPI
from config import AUTHORIZED_USER_IDS
from lib.cache_handler import CacheHandler
from lib.banner_renderer import BannerRenderer
from lib.profile_renderer import generate_profile_card  # プロファイル画像生成

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
                else:
                    rank_display = (raw_support_rank or 'None').capitalize()
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
        # 画像送信形式に変更
        data = await self.cog_instance.wynn_api.get_official_player_data(selected_uuid)
        if not data or 'uuid' not in data:
            await interaction.message.edit(content="選択されたプレイヤーの情報を取得できませんでした。", embed=None, view=None)
            return

        # --- 画像送信に必要なprofile_info生成 ---
        raw_support_rank = data.get('supportRank', 'Player')
        if raw_support_rank and raw_support_rank.lower() == "vipplus":
            support_rank_display = "Vip+"
        else:
            support_rank_display = (raw_support_rank or 'None').capitalize()
        first_join_str = data.get('firstJoin', "N/A")
        first_join_date = first_join_str.split('T')[0] if 'T' in first_join_str else first_join_str
        last_join_str = data.get('lastJoin', "1970-01-01T00:00:00.000Z")
        try:
            last_join_dt = datetime.fromisoformat(last_join_str.replace('Z', '+00:00'))
            last_join_date = last_join_dt.strftime('%Y-%m-%d')
        except Exception:
            last_join_date = last_join_str.split('T')[0] if 'T' in last_join_str else last_join_str
        guild_prefix = data.get('guild', {}).get('prefix', "")
        guild_data = await self.wynn_api.get_guild_by_prefix(guild_prefix)
        banner_bytes = self.banner_renderer.create_banner_image(guild_data.get('banner') if guild_data else None)

        profile_info = {
            "username": data.get("username"),
            "support_rank_display": support_rank_display,
            "guild_prefix": guild_prefix,
            "banner_bytes": banner_bytes,
            "guild_name": data.get('guild', {}).get('name', ""),
            "guild_rank": data.get('guild', {}).get('rank', ""),
            "guild_rank_stars": data.get('guild', {}).get('rankStars', ""),
            "first_join": first_join_date,
            "last_join": last_join_date,
            "mobs_killed": data.get('globalData', {}).get('mobsKilled', 0),
            "playtime": data.get("playtime", 0),
            "wars": data.get('globalData', {}).get('wars', 0),
            "war_rank_display": data.get('ranking', {}).get('warsCompletion', "N/A"),
            "quests": data.get('globalData', {}).get('completedQuests', 0),
            "world_events": data.get('globalData', {}).get('worldEvents', 0),
            "total_level": data.get('globalData', {}).get('totalLevel', 0),
            "chests": data.get('globalData', {}).get('chestsFound', 0),
            "pvp_kill": f"{data.get('globalData', {}).get('pvp', {}).get('kills', 0)}",
            "pvp_death": f"{data.get('globalData', {}).get('pvp', {}).get('deaths', 0)}",
            "notg": data.get('globalData', {}).get('raids', {}).get('list', {}).get('Nest of the Grootslangs', 0),
            "nol": data.get('globalData', {}).get('raids', {}).get('list', {}).get("Orphion's Nexus of Light", 0),
            "tcc": data.get('globalData', {}).get('raids', {}).get('list', {}).get('The Canyon Colossus', 0),
            "tna": data.get('globalData', {}).get('raids', {}).get('list', {}).get('The Nameless Anomaly', 0),
            "dungeons": data.get('globalData', {}).get('dungeons', {}).get('total', 0),
            "all_raids": data.get('globalData', {}).get('raids', {}).get('total', 0),
            "uuid": data.get("uuid"),
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
            # 1. エラー返却なら即「見つかりませんでした」
            if not api_data or (isinstance(api_data, dict) and "error" in api_data and api_data.get("error") != "MultipleObjectsReturned"):
                await interaction.followup.send(f"プレイヤー「{player}」が見つかりませんでした。")
                return

            # 2. API更新対応: 複数プレイヤーの場合
            if isinstance(api_data, dict) and api_data.get("error") == "MultipleObjectsReturned" and "objects" in api_data:
                player_collision_dict = api_data["objects"]
                view = PlayerSelectView(player_collision_dict=player_collision_dict, cog_instance=self, owner_id=interaction.user.id)
                if hasattr(view, "select_menu") and view.select_menu.options:
                    await interaction.followup.send(
                        "複数のプレイヤーが見つかりました。どちらの情報を表示しますか？", view=view
                    )
                else:
                    await interaction.followup.send(f"プレイヤー「{player}」が見つかりませんでした。")
                return

            # 3. 単一プレイヤーデータ（usernameキーあり）ならprofile_info
            if isinstance(api_data, dict) and 'username' in api_data:
                data = api_data
                self.cache.set_cache(cache_key, api_data)
            else:
                await interaction.followup.send(f"プレイヤー「{player}」が見つかりませんでした。")
                return

        # サポートランク取得（バグ防止のためEmbed版のロジックを流用）
        raw_support_rank = data.get('supportRank', 'Player')
        if raw_support_rank and raw_support_rank.lower() == "vipplus":
            support_rank_display = "Vip+"
        else:
            support_rank_display = (raw_support_rank or 'None').capitalize()

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
        banner_bytes = self.banner_renderer.create_banner_image(guild_data.get('banner') if guild_data else None)

        profile_info = {
            "username": data.get("username"),
            "support_rank_display": support_rank_display,
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
