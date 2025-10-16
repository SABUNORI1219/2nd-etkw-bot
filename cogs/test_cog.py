import discord
from discord import app_commands
from discord.ext import commands
import logging
from io import BytesIO

from lib.api_stocker import WynncraftAPI
from lib.cache_handler import CacheHandler
from lib.banner_renderer import BannerRenderer
from lib.guild_renderer import create_guild_image
from lib.utils import create_embed
from config import AUTHORIZED_USER_IDS, send_authorized_only_message

logger = logging.getLogger(__name__)

class GuildImageCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.wynn_api = WynncraftAPI()
        self.cache = CacheHandler()
        self.banner_renderer = BannerRenderer()
        logger.info("GuildImageCog loaded")

    def _safe_get(self, data, keys, default=None):
        v = data
        for k in keys:
            if not isinstance(v, dict):
                return default
            v = v.get(k)
            if v is None:
                return default
        return v if v is not None else default

    @app_commands.checks.cooldown(1, 5.0, key=lambda i: i.user.id)
    @app_commands.command(name="test", description="Test")
    @app_commands.describe(guild="Test")
    async def test(self, interaction: discord.Interaction, guild: str):
        await interaction.response.defer()

        # 権限チェック
        if interaction.user.id not in AUTHORIZED_USER_IDS:
            await send_authorized_only_message(interaction)
            return

        cache_key = f"guild_{guild}"
        data_to_use = None

        cached = self.cache.get_cache(cache_key)
        if cached:
            data_to_use = cached
        else:
            # 二段検索（prefix -> name）
            data_as_prefix = await self.wynn_api.get_guild_by_prefix(guild)
            if data_as_prefix and data_as_prefix.get("name"):
                data_to_use = data_as_prefix
            else:
                data_as_name = await self.wynn_api.get_guild_by_name(guild)
                if data_as_name and data_as_name.get("name"):
                    data_to_use = data_as_name

            if data_to_use:
                self.cache.set_cache(cache_key, data_to_use)

        if not data_to_use:
            embed = create_embed(description=f"ギルド **{guild}** が見つかりませんでした。", title="🔴 エラーが発生しました", color=discord.Color.red(), footer_text="Guild Test")
            await interaction.followup.send(embed=embed)
            return

        # 画像生成
        try:
            img_io: BytesIO = create_guild_image(data_to_use, self.banner_renderer)
            file = discord.File(fp=img_io, filename="guild_card.png")
            await interaction.followup.send(file=file)
        except Exception as e:
            logger.exception("ギルド画像生成中に例外が発生しました")
            embed = create_embed(description="画像生成中にエラーが発生しました。ログを確認してください。", title="🔴 エラー", color=discord.Color.red(), footer_text="Guild Test")
            await interaction.followup.send(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(GuildImageCog(bot))
