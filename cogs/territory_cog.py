import discord
from discord import app_commands
from discord.ext import commands, tasks
import asyncio
import logging
import json
import os
from datetime import datetime, timezone

# libフォルダから専門家たちをインポート
from lib.wynncraft_api import WynncraftAPI
from lib.map_renderer import MapRenderer
from lib.cache_handler import CacheHandler
from config import EMBED_COLOR_BLUE, RESOURCE_EMOJIS

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

# allowed_installsとallowed_contextsは、Botをどこで使えるかを定義するデコレータです
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
class Territory(commands.GroupCog, name="territory"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.wynn_api = WynncraftAPI()
        self.map_renderer = MapRenderer()
        self.cache = CacheHandler()
        self.territory_guilds_cache = [] # ギルド名のリスト
        self.update_territory_cache.start() # 定期更新タスクを開始
        logger.info(f"--- [Cog] {self.__class__.__name__} が読み込まれました。")

        try:
            with open(TERRITORIES_JSON_PATH, "r", encoding='utf-8') as f:
                self.territory_names = list(json.load(f).keys())
        except Exception as e:
            self.territory_names = []
            logger.error(f"territories.jsonの読み込みに失敗: {e}")

        logger.info(f"--- [Cog] {self.__class__.__name__} が読み込まれました。")

    def _create_status_embed(self, interaction: discord.Interaction, territory: str, live_data: dict, static_data: dict) -> discord.Embed:
        # --- 所有期間を計算 ---
        acquired_dt = datetime.fromisoformat(live_data['acquired'].replace("Z", "+00:00"))
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

        # --- 生産情報を整形 ---
        production_data = static_data.get('resources', {})
        production_text_list = []
        # ▼▼▼【修正点1】amountを数値に変換して比較▼▼▼
        for res_name, amount in production_data.items():
            if int(amount) > 0: # amountが0より大きいものだけを追加
                emoji = RESOURCE_EMOJIS.get(res_name.upper(), '❓')
                
                # 表示用の名前を作成する際に、末尾の's'を削除
                display_res_name = res_name.capitalize()
                if display_res_name.endswith('s'):
                    display_res_name = display_res_name[:-1]
                    
                production_text_list.append(f"{emoji} {display_res_name}: `+{amount}/h`")
        
        production_text = "\n".join(production_text_list) if production_text_list else "None"
        
        # --- 接続数を計算 ---
        conns_count = len(static_data.get('Trading Routes', []))

        # --- 埋め込みを作成 ---
        embed = discord.Embed(title=f"{territory}", color=discord.Color.dark_teal())
        guild_name = live_data['guild']['name']
        guild_prefix = live_data['guild']['prefix']
        embed.add_field(name="Guild", value=f"[{guild_prefix}] {guild_name}", inline=False)
        embed.add_field(name="Time Held for", value=f"`{held_for}`", inline=False)
        embed.add_field(name="Production", value=production_text, inline=False)
        embed.add_field(name="Original Conns", value=f"{conns_count} Conns", inline=False)
        embed.set_footer(text="Territory Status | Minister Chikuwa")
        return embed

    def cog_unload(self):
        self.update_territory_cache.cancel()

    @tasks.loop(minutes=10.0)
    async def update_territory_cache(self):
        logger.info("--- [TerritoryCache] テリトリー所有ギルドのキャッシュを更新します...")
        territory_data = await self.wynn_api.get_territory_list()
        if territory_data:
            guild_names = set(data['guild']['prefix'] for data in territory_data.values())
            self.territory_guilds_cache = sorted(list(guild_names))
            logger.info(f"--- [TerritoryCache] ✅ {len(self.territory_guilds_cache)}個のギルドをキャッシュしました。")

    @update_territory_cache.before_loop
    async def before_cache_update(self):
        await self.bot.wait_until_ready() # Botの準備が完了するまで待つ
        
    async def guild_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        
        # APIではなく、メモリ上のキャッシュから候補を検索する
        return [
            app_commands.Choice(name=name, value=name)
            for name in self.territory_guilds_cache if current.lower() in name.lower()
        ][:25]

    @app_commands.checks.cooldown(1, 20.0)
    @app_commands.command(name="map", description="現在のWynncraftのテリトリーマップを生成")
    @app_commands.autocomplete(guild=guild_autocomplete) # guild引数にオートコンプリートを適用
    @app_commands.describe(guild="マップ上のギルドのPrefix(任意)")
    async def map(self, interaction: discord.Interaction, guild: str = None):
        await interaction.response.defer()
        logger.info(f"--- [TerritoryCmd] /territory map が実行されました by {interaction.user}")

        # ▼▼▼【修正点】必要なAPIデータを両方取得する▼▼▼
        # 1. テリトリー所有者リストを取得
        territory_data = await self.wynn_api.get_territory_list()
        # 2. ギルドカラーの対応表を取得
        guild_color_map = await self.wynn_api.get_guild_color_map()

        if not territory_data or not guild_color_map:
            await interaction.followup.send("テリトリーまたはギルドカラー情報の取得に失敗しました。コマンドをもう一度お試しください。")
            return

        # ギルドが指定されているかによって、描画するデータを切り替える
        if guild:
            # 指定されたギルドのテリトリーのみをフィルタリング
            territories_to_render = {
                name: data for name, data in territory_data.items()
                if data['guild']['prefix'].upper() == guild.upper()
            }
            if not territories_to_render:
                await interaction.followup.send(f"ギルド「{guild}」は現在テリトリーを所有していません。")
                return
        else:
            # 指定がなければ、全てのテリトリーを描画
            territories_to_render = territory_data
            
        # 地図職人に、非同期で画像の生成を依頼
        # 必要な情報を全て渡す
        loop = asyncio.get_running_loop()
        file, embed = await loop.run_in_executor(
            None, 
            self.map_renderer.create_territory_map,
            territory_data,
            territories_to_render, 
            guild_color_map
        )
        # ▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲

        if file and embed:
            await interaction.followup.send(file=file, embed=embed)
        else:
            await interaction.followup.send("マップの生成中にエラーが発生しました。コマンドをもう一度お試しください。")

    @app_commands.checks.cooldown(1, 5.0, key=lambda i: i.user.id)
    @app_commands.command(name="status", description="指定されたテリトリーのステータスを表示")
    @app_commands.autocomplete(territory=territory_autocomplete)
    @app_commands.describe(territory="Territory Name")
    async def status(self, interaction: discord.Interaction, territory: str):
        await interaction.response.defer()

        static_data = self.map_renderer.local_territories.get(territory)

        # --- ステップ1: データの取得 ---
        cache_key = "wynn_territory_list"
        territory_list_data = self.cache.get_cache(cache_key)
        if not territory_list_data:
            logger.info("--- [API] テリトリーリストのキャッシュがないため、APIから取得します。")
            territory_list_data = await self.wynn_api.get_territory_list()
            if territory_list_data:
                self.cache.set_cache(cache_key, territory_list_data)

        if not territory_list_data:
            await interaction.followup.send("テリトリー情報の取得に失敗しました。")
            return
            
        # --- ステップ2: データの整形 ---
        target_territory_live_data = territory_list_data.get(territory)
        if not target_territory_live_data:
            await interaction.followup.send(f"「{territory}」は無効なテリトリーか、現在どのギルドも所有していません。")
            return

        embed = self._create_status_embed(interaction, territory, target_territory_live_data, static_data)

        # --- ステップ3: 画像の生成と送信 ---
        image_bytes = self.map_renderer.create_single_territory_image(territory)
        if image_bytes:
            filename = f"{territory.replace(' ', '_')}.png"
            image_file = discord.File(fp=image_bytes, filename=filename)
            embed.set_image(url=f"attachment://{filename}")
            await interaction.followup.send(embed=embed, file=image_file)
        else:
            await interaction.followup.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Territory(bot))
