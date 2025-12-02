import discord
from discord import app_commands
from discord.ext import commands
import logging
from io import BytesIO
from urllib.parse import quote

from lib.api_stocker import WynncraftAPI
from lib.cache_handler import CacheHandler
from lib.banner_renderer import BannerRenderer
from lib.guild_profile_renderer import create_guild_image
from lib.utils import create_embed

logger = logging.getLogger(__name__)

class GuildImageCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.wynn_api = WynncraftAPI()
        self.cache = CacheHandler()
        self.banner_renderer = BannerRenderer()
        self.system_name = "Wynncraft Guild's Stats"
        logger.info("--- [CommandsCog] ギルドコマンドCogが読み込まれました。")

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
    @app_commands.command(name="guild", description="ギルドのステータスカードを表示")
    @app_commands.describe(guild="Name or Prefix")
    async def test(self, interaction: discord.Interaction, guild: str):
        await interaction.response.defer()

        cache_key = f"guild_{guild}"
        data_to_use = None
        found_by_prefix = False  # prefixで見つかったかどうかを追跡

        cached = self.cache.get_cache(cache_key)
        if cached:
            data_to_use = cached
            # キャッシュの場合は検索方法を推測（後で改良可能）
            # とりあえずギルド名に一致するかチェック
            guild_name = self._safe_get(data_to_use, ["name"], "")
            found_by_prefix = guild.upper() != guild_name.upper()
        else:
            # 二段検索（prefix -> name）
            data_as_prefix = await self.wynn_api.get_guild_by_prefix(guild)
            if data_as_prefix and data_as_prefix.get("name"):
                data_to_use = data_as_prefix
                found_by_prefix = True
            else:
                data_as_name = await self.wynn_api.get_guild_by_name(guild)
                if data_as_name and data_as_name.get("name"):
                    data_to_use = data_as_name
                    found_by_prefix = False

            if data_to_use:
                self.cache.set_cache(cache_key, data_to_use)

        if not data_to_use:
            embed = create_embed(description=f"ギルド **{guild}** が見つかりませんでした。", title="🔴 エラーが発生しました", color=discord.Color.red(), footer_text=f"{self.system_name} | Minister Chikuwa")
            await interaction.followup.send(embed=embed)
            return

        # 画像生成
        try:
            img_io: BytesIO = await create_guild_image(data_to_use, self.banner_renderer)
            file = discord.File(fp=img_io, filename="guild_card.png")
            await interaction.followup.send(file=file)
            
            # 公式サイトリンクのEmbed送信
            guild_name = self._safe_get(data_to_use, ["name"], "Unknown Guild")
            guild_prefix = self._safe_get(data_to_use, ["prefix"], "")
            
            # URLエンコード
            encoded_name = quote(guild_name)
            
            # 検索方法に応じてURL生成
            if found_by_prefix:
                url = f"https://wynncraft.com/stats/guild/{encoded_name}?prefix=true"
                search_method = f"プレフィックス「{guild_prefix}」"
            else:
                url = f"https://wynncraft.com/stats/guild/{encoded_name}"
                search_method = f"ギルド名「{guild_name}」"
            
            # リンクEmbed作成
            link_embed = create_embed(
                title="🔗 Wynncraftでギルド詳細を見る",
                description=f"{search_method}で検索されました\n[**{guild_name}** の公式ページ]({url})",
                color=discord.Color.blue(),
                footer_text=f"{self.system_name} | Minister Chikuwa"
            )
            
            await interaction.followup.send(embed=link_embed)
            
        except Exception as e:
            logger.exception("ギルド画像生成中に例外が発生しました")
            embed = create_embed(description="画像生成中にエラーが発生しました。", title="🔴 エラー", color=discord.Color.red(), footer_text=f"{self.system_name} | Minister Chikuwa")
            await interaction.followup.send(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(GuildImageCog(bot))
