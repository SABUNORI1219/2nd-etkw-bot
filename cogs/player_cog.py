import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timezone, timedelta
import logging
import os

from lib.wynncraft_api import WynncraftAPI
from config import EMBED_COLOR_BLUE, EMBED_COLOR_GREEN, AUTHORIZED_USER_IDS
from lib.cache_handler import CacheHandler

from lib.profile_renderer import generate_profile_card

logger = logging.getLogger(__name__)

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONT_PATH = os.path.join(project_root, "assets", "fonts", "times.ttf")

class PlayerCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.wynn_api = WynncraftAPI()
        self.cache = CacheHandler()
        logger.info("--- [PlayerCog] プレイヤーCogが読み込まれました。")

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

    def format_stat(self, val):
        if isinstance(val, int) or isinstance(val, float):
            return f"{val:,}"
        return str(val)

    def format_datetime_iso(self, dt_str):
        if not dt_str or "T" not in dt_str:
            return "非公開"
        try:
            dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return "非公開"

    @app_commands.command(name="player", description="プレイヤーのステータスを表示")
    @app_commands.describe(player="MCID or UUID")
    async def player(self, interaction: discord.Interaction, player: str):
        await interaction.response.defer()

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
            data = cached_data
        else:
            logger.info(f"--- [API] プレイヤー'{player}'のデータをAPIから取得します。")
            api_data = await self.wynn_api.get_official_player_data(player)
            if not api_data or (isinstance(api_data, dict) and "error" in api_data and api_data.get("error") != "MultipleObjectsReturned"):
                await interaction.followup.send(f"プレイヤー「{player}」が見つかりませんでした。")
                return
            if isinstance(api_data, dict) and 'username' in api_data:
                data = api_data
                self.cache.set_cache(cache_key, api_data)
            else:
                await interaction.followup.send(f"プレイヤー「{player}」が見つかりませんでした。")
                return

        # --- 画像生成 ---
        uuid = data.get("uuid", "")
        output_path = f"profile_card_{uuid}.png" if uuid else "profile_card.png"
        try:
            # ここでWanted風背景画像を生成（今後はプレイヤー情報も描画予定）
            generate_profile_card(data, output_path)
            file = discord.File(output_path, filename=os.path.basename(output_path))
            await interaction.followup.send(file=file)
            if os.path.exists(output_path):
                os.remove(output_path)
        except Exception as e:
            logger.error(f"画像生成または送信失敗: {e}")
            await interaction.followup.send("プロフィール画像生成に失敗しました。")

async def setup(bot: commands.Bot): await bot.add_cog(PlayerCog(bot))
