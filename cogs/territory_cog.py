import discord
from discord import app_commands
from discord.ext import commands, tasks
import asyncio
import logging

# libフォルダから専門家たちをインポート
from lib.wynncraft_api import WynncraftAPI
from lib.map_renderer import MapRenderer

logger = logging.getLogger(__name__)

# allowed_installsとallowed_contextsは、Botをどこで使えるかを定義するデコレータです
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
class Territory(commands.GroupCog, name="territory"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.wynn_api = WynncraftAPI()
        self.map_renderer = MapRenderer()
        self.territory_guilds_cache = [] # ギルド名のリスト
        self.update_territory_cache.start() # 定期更新タスクを開始
        logger.info(f"--- [Cog] {self.__class__.__name__} が読み込まれました。")

    def cog_unload(self):
        self.update_territory_cache.cancel()

    # ▼▼▼【キャッシュを10分おきに更新するタスクを追加】▼▼▼
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

    # ▼▼▼【オートコンプリートは、APIではなくキャッシュを参照するように修正】▼▼▼
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

    @app_commands.command(name="map", description="現在のWynncraftテリトリーマップを生成します。")
    @app_commands.autocomplete(guild=guild_autocomplete) # guild引数にオートコンプリートを適用
    @app_commands.describe(guild="ギルドのプレフィックス（任意）")
    async def map(self, interaction: discord.Interaction, guild: str = None):
        await interaction.response.defer()
        logger.info(f"--- [TerritoryCmd] /territory map が実行されました by {interaction.user}")

        territory_data = await self.wynn_api.get_territory_list()
        if not territory_data:
            await interaction.followup.send("テリトリー情報の取得に失敗しました。")
            return

        # 指定されたギルドのテリトリーのみをフィルタリングする
        if guild:
            filtered_territories = {
                name: data for name, data in territory_data.items()
                if data['guild']['prefix'].upper() == guild.upper()
            }
            if not filtered_territories:
                await interaction.followup.send(f"ギルド「{guild}」は現在テリトリーを所有していません。")
                return
            territory_data_to_render = filtered_territories
        else:
            territory_data_to_render = territory_data
            
        # 地図職人に、非同期で画像の生成を依頼
        loop = asyncio.get_running_loop()
        file, embed = await loop.run_in_executor(
            None, self.map_renderer.create_territory_map, territory_data_to_render, {} # カラーマップは後で実装
        )

        if file and embed:
            await interaction.followup.send(file=file, embed=embed)
        else:
            await interaction.followup.send("マップの生成中にエラーが発生しました。")


async def setup(bot: commands.Bot):
    await bot.add_cog(Territory(bot))
