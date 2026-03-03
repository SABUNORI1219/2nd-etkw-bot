import discord
from discord import app_commands
from discord.ext import commands, tasks
import logging
import json
import os
import re
from datetime import datetime, timezone
import subprocess
import pickle
import tempfile
import sys
from io import BytesIO

from lib.api_stocker import WynncraftAPI, OtherAPI
from lib.map_renderer import MapRenderer
from lib.cache_handler import CacheHandler
from lib.utils import create_embed
from config import RESOURCE_EMOJIS

logger = logging.getLogger(__name__)

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TERRITORIES_JSON_PATH = os.path.join(project_root, "assets", "map", "territories.json")

async def territory_autocomplete(
    interaction: discord.Interaction,
    current: str,
) -> list[app_commands.Choice[str]]:
    try:
        with open(TERRITORIES_JSON_PATH, "r", encoding='utf-8') as f:
            territory_names = list(json.load(f).keys())
    except Exception:
        territory_names = []
    return [
        app_commands.Choice(name=name, value=name)
        for name in territory_names if current.lower() in name.lower()
    ][:25]

@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
class Territory(commands.GroupCog, name="territory"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.wynn_api = WynncraftAPI()
        self.other_api = OtherAPI()
        self.map_renderer = MapRenderer()
        self.cache = CacheHandler()
        self.system_name = "Territory Map"
        self.territory_guilds_cache = [] # ギルド名のリスト
        self.latest_territory_data = {}  # 最新の領地データを保存
        
        # 定期更新タスクを開始
        self.update_territory_data.start()
        self.update_territory_cache.start()
        
        logger.info(f"--- [Cog] {self.__class__.__name__} が読み込まれました。")

        try:
            with open(TERRITORIES_JSON_PATH, "r", encoding='utf-8') as f:
                self.territory_names = list(json.load(f).keys())
        except Exception as e:
            self.territory_names = []
            logger.error(f"territories.jsonの読み込みに失敗: {e}")

    def _create_status_embed(self, interaction: discord.Interaction, territory: str, target_territory_live_data: dict, static_data: dict) -> discord.Embed:
        acquired_dt = datetime.fromisoformat(target_territory_live_data['acquired'].replace("Z", "+00:00"))
        duration = datetime.now(timezone.utc) - acquired_dt
        days = duration.days
        hours, remainder = divmod(duration.seconds, 3600)
        minutes, _ = divmod(remainder, 60)
        held_for_parts = []
        if days > 0:
            held_for_parts.append(f"{days} days")
        if hours > 0:
            held_for_parts.append(f"{hours} hours")
        if minutes > 0:
            held_for_parts.append(f"{minutes} mins")
        held_for = " ".join(held_for_parts) if held_for_parts else "Just now"
        production_data = static_data.get('resources', {})
        production_text_list = []
        for res_name, amount in production_data.items():
            if int(amount) > 0:
                emoji = RESOURCE_EMOJIS.get(res_name.upper(), '❓')
                display_res_name = res_name.capitalize()
                if display_res_name.endswith('s'):
                    display_res_name = display_res_name[:-1]
                production_text_list.append(f"{emoji} {display_res_name}: `+{amount}/h`")
        production_text = "\n".join(production_text_list) if production_text_list else "None"
        conns_count = len(static_data.get('Trading Routes', []))
        embed = discord.Embed(title=f"{territory}", color=discord.Color.purple())
        guild_name = target_territory_live_data['guild']['name']
        guild_prefix = target_territory_live_data['guild']['prefix']
        embed.add_field(name="Guild", value=f"[{guild_prefix}] {guild_name}", inline=False)
        embed.add_field(name="Time Held for", value=f"`{held_for}`", inline=False)
        embed.add_field(name="Production", value=production_text, inline=False)
        embed.add_field(name="Original Conns", value=f"{conns_count} Conns", inline=False)
        embed.set_footer(text="Territory Status | Minister Chikuwa")
        return embed

    def cog_unload(self):
        self.update_territory_data.cancel()
        self.update_territory_cache.cancel()

    def safe_filename(self, name: str) -> str:
        return re.sub(r'[^a-zA-Z0-9_-]', '_', name)

    @tasks.loop(minutes=1.0)
    async def update_territory_data(self):
        """領地データを定期取得してインスタンス変数に保存"""
        logger.info("[TerritoryTracker] 領地データの取得を開始します...")
        territory_data = await self.wynn_api.get_territory_list()
        
        if not territory_data:
            logger.warning("[TerritoryTracker] 領地データ取得失敗。次回取得時に再試行します。")
            return
        
        self.latest_territory_data = territory_data
        logger.info(f"[TerritoryTracker] ✅ 領地データ更新完了: {len(territory_data)}個の領地")

    @update_territory_data.before_loop
    async def before_territory_data_update(self):
        await self.bot.wait_until_ready()

    @tasks.loop(minutes=1.0)
    async def update_territory_cache(self):
        """テリトリー所有ギルドのキャッシュを更新"""
        logger.info("--- [TerritoryCache] テリトリー所有ギルドのキャッシュを更新します...")
        
        if not self.latest_territory_data:
            logger.warning("latest_territory_dataが空のためキャッシュ更新をスキップ")
            return
            
        guild_names = set(
            data['guild']['prefix']
            for data in self.latest_territory_data.values()
            if data.get('guild', {}).get('prefix')
        )
        self.territory_guilds_cache = sorted(list(guild_names))
        logger.info(f"--- [TerritoryCache] ✅ {len(self.territory_guilds_cache)}個のギルドをキャッシュしました。")

    @update_territory_cache.before_loop
    async def before_cache_update(self):
        await self.bot.wait_until_ready()

    async def guild_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        result = [
            app_commands.Choice(name=name, value=name)
            for name in self.territory_guilds_cache if current.lower() in name.lower()
        ][:25]
        return result

    async def get_territory_data_with_cache(self):
        # インスタンス変数の最新データを優先的に使用
        if self.latest_territory_data:
            return self.latest_territory_data
            
        # フォールバック：キャッシュから取得
        cache_key = "wynn_territory_list"
        territory_data = self.cache.get_cache(cache_key)
        if not territory_data:
            territory_data = await self.wynn_api.get_territory_list()
            if territory_data:
                self.cache.set_cache(cache_key, territory_data)
                self.latest_territory_data = territory_data  # インスタンス変数にも保存
        return territory_data

    async def get_guild_color_map_with_cache(self):
        cache_key = "guild_color_map"
        color_map = self.cache.get_cache(cache_key)
        if not color_map:
            color_map = await self.other_api.get_guild_color_map()
            if color_map:
                self.cache.set_cache(cache_key, color_map)
        return color_map

    @app_commands.checks.cooldown(1, 20.0)
    @app_commands.command(name="map", description="現在のWynncraftのテリトリーマップを生成")
    @app_commands.autocomplete(guild=guild_autocomplete)
    @app_commands.describe(guild="On-map Guild Prefix")
    async def map(self, interaction: discord.Interaction, guild: str = None):
        await interaction.response.defer()

        territory_data = await self.get_territory_data_with_cache()
        guild_color_map = await self.get_guild_color_map_with_cache()
        if not territory_data or not guild_color_map:
            embed = create_embed(description="テリトリーまたはギルドカラー情報の取得に失敗しました。\nコマンドをもう一度お試しください。", title="🔴 エラーが発生しました", color=discord.Color.red(), footer_text=f"{self.system_name} | Onyx")
            await interaction.followup.send(embed=embed)
            return

        show_held_time = False
        if guild:
            territories_to_render = {
                name: data for name, data in territory_data.items()
                if data['guild']['prefix'].upper() == guild.upper()
            }
            if not territories_to_render:
                embed = create_embed(description=f"ギルド **{guild}** は現在、領地を所有していません。", title="🔴 エラーが発生しました", color=discord.Color.red(), footer_text=f"{self.system_name} | Onyx")
                await interaction.followup.send(embed=embed)
                return
            show_held_time = True  # 個別ギルド指定時は保持時間を表示
        else:
            territories_to_render = territory_data

        params = {
            'territory_data': territory_data,
            'territories_to_render': territories_to_render,
            'guild_color_map': guild_color_map,
            'show_held_time': show_held_time
        }
        with tempfile.TemporaryFile() as inpipe, tempfile.TemporaryFile() as outpipe:
            pickle.dump(params, inpipe)
            inpipe.seek(0)
            proc = subprocess.Popen(
                [sys.executable, 'lib/subproc_map_worker.py'],
                stdin=inpipe,
                stdout=outpipe,
                cwd=project_root
            )
            proc.wait()
            outpipe.seek(0)
            result = pickle.load(outpipe)

        map_bytes = result.get('map_bytes')
        embed_dict = result.get('embed_dict')
        if map_bytes and embed_dict:
            file = discord.File(fp=BytesIO(map_bytes), filename="wynn_map.png")
            embed = discord.Embed.from_dict(embed_dict)
            
            # guildが指定されていない場合のみ統計Embedを作成・送信
            if guild is None:
                stats_embed = self.map_renderer.create_territory_stats_embed(territory_data)
                await interaction.followup.send(file=file, embeds=[embed, stats_embed])
                del stats_embed
            else:
                await interaction.followup.send(file=file, embed=embed)
            
            file.close()
            del file, embed
        else:
            embed = create_embed(description="マップの生成中にエラーが発生しました。\nコマンドをもう一度お試しください。", title="🔴 エラーが発生しました", color=discord.Color.red(), footer_text=f"{self.system_name} | Onyx")
            await interaction.followup.send(embed=embed)

    @app_commands.checks.cooldown(1, 5.0, key=lambda i: i.user.id)
    @app_commands.command(name="status", description="指定されたテリトリーのステータスを表示")
    @app_commands.autocomplete(territory=territory_autocomplete)
    @app_commands.describe(territory="Territory Name")
    async def status(self, interaction: discord.Interaction, territory: str):
        await interaction.response.defer()

        static_data = self.map_renderer.local_territories.get(territory)
        guild_color_map = await self.get_guild_color_map_with_cache()
        territory_data = await self.get_territory_data_with_cache()
        if not territory_data:
            embed = create_embed(description="テリトリー情報の取得に失敗しました。", title="🔴 エラーが発生しました", color=discord.Color.red(), footer_text=f"{self.system_name} | Onyx")
            await interaction.followup.send(embed=embed)
            return
        target_territory_live_data = territory_data.get(territory)
        if not target_territory_live_data:
            embed = create_embed(description=f"**{territory}** は存在しない領地か、現在どのギルドも所有していません。", title="🔴 エラーが発生しました", color=discord.Color.red(), footer_text=f"{self.system_name} | Onyx")
            await interaction.followup.send(embed=embed)
            return
        embed = self._create_status_embed(
            interaction,
            territory,
            target_territory_live_data,
            static_data,
        )

        params = {
            'mode': 'single',
            'territory': territory,
            'territory_data': territory_data,
            'guild_color_map': guild_color_map,
        }
        with tempfile.TemporaryFile() as inpipe, tempfile.TemporaryFile() as outpipe:
            pickle.dump(params, inpipe)
            inpipe.seek(0)
            proc = subprocess.Popen(
                [sys.executable, 'lib/subproc_map_worker.py'],
                stdin=inpipe,
                stdout=outpipe,
                cwd=project_root
            )
            proc.wait()
            outpipe.seek(0)
            result = pickle.load(outpipe)

        img_bytes = result.get('image_bytes')
        if img_bytes:
            safe_name = self.safe_filename(territory)
            filename = f"{safe_name}.png"
            image_file = discord.File(fp=BytesIO(img_bytes), filename=filename)
            embed.set_image(url=f"attachment://{filename}")
            await interaction.followup.send(embed=embed, file=image_file)
            image_file.close()
            del image_file, embed
        else:
            await interaction.followup.send(embed=embed)
            del embed

async def setup(bot: commands.Bot):
    await bot.add_cog(Territory(bot))
