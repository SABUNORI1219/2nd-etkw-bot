import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import logging

from lib.wynncraft_api import WynncraftAPI
from lib.map_renderer import MapRenderer

logger = logging.getLogger(__name__)

@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
class Territory(commands.GroupCog, name="territory"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.wynn_api = WynncraftAPI()
        self.map_renderer = MapRenderer()
        logger.info(f"--- [Cog] {self.__class__.__name__} が読み込まれました。")

    @app_commands.command(name="map", description="現在のWynncraftテリトリーマップを生成します。")
    async def map(self, interaction: discord.Interaction):
        await interaction.response.defer()
        logger.info(f"--- [TerritoryCmd] /territory map が実行されました by {interaction.user}")

        # ▼▼▼【修正箇所】必要なデータを2種類取得する▼▼▼
        # 1. テリトリー所有者リストを取得
        territory_data = await self.wynn_api.get_territory_list()
        # 2. ギルドカラーの対応表を取得
        guild_color_map = await self.wynn_api.get_guild_color_map()

        if not territory_data or not guild_color_map:
            await interaction.followup.send("テリトリー情報の取得に失敗しました。")
            return

        # 地図職人に、非同期で画像の生成を依頼
        # run_in_executorに複数の引数を渡すには、functools.partialを使う
        import functools
        loop = asyncio.get_running_loop()
        file, embed = await loop.run_in_executor(
            None, 
            functools.partial(self.map_renderer.create_territory_map, territory_data, guild_color_map)
        )
        # ▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲

        if file and embed:
            await interaction.followup.send(file=file, embed=embed)
        else:
            await interaction.followup.send("マップの生成中にエラーが発生しました。")

async def setup(bot: commands.Bot):
    await bot.add_cog(Territory(bot))
