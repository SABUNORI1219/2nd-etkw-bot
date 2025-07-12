import discord
from discord import app_commands
from discord.ext import commands
from io import BytesIO
import logging

# libとconfigから専門家と設定をインポート
from lib.wynncraft_api import WynncraftAPI
from lib.banner_renderer import BannerRenderer

logger = logging.getLogger(__name__)

class TestCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.wynn_api = WynncraftAPI()
        self.banner_renderer = BannerRenderer()
        logger.info(f"--- [Cog] {self.__class__.__name__} が読み込まれました。")

    @app_commands.command(name="testbanner", description="ギルドバナーの生成機能だけをテストします。")
    @app_commands.describe(prefix="ギルドのプレフィックス (例: ETKW)")
    async def test_banner(self, interaction: discord.Interaction, prefix: str):
        await interaction.response.defer()

        # 1. 公式API担当に、プレフィックスでギルドデータを依頼
        logger.info(f"--- [Test] 公式APIから '{prefix}' のデータを取得します。")
        guild_data = await self.wynn_api.get_guild_by_prefix(prefix)

        if not guild_data or 'banner' not in guild_data:
            await interaction.followup.send(f"ギルド「{prefix}」のデータ、またはバナー情報が見つかりませんでした。")
            return
        
        # 2. バナー担当者に、画像の生成を依頼
        logger.info(f"--- [Test] '{prefix}' のバナーを生成します。")
        banner_bytes = self.banner_renderer.create_banner_image(guild_data.get('banner'))

        # 3. 画像を送信
        if banner_bytes:
            banner_file = discord.File(fp=banner_bytes, filename="guild_banner.png")
            await interaction.followup.send(f"「{guild_data.get('name')}」のバナー生成に成功しました。", file=banner_file)
        else:
            await interaction.followup.send("バナー画像の生成に失敗しました。")

# BotにCogを登録するためのセットアップ関数
async def setup(bot: commands.Bot):
    await bot.add_cog(TestCog(bot))
