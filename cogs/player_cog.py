import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timezone, timedelta
import logging
import os
import requests
import random
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from io import BytesIO

logger = logging.getLogger(__name__)

# フォントパス（arial.ttf優先・なければデフォルト）
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONT_PATH = os.path.join(project_root, "assets", "fonts", "times.ttf")

from lib.wynncraft_api import WynncraftAPI
from config import EMBED_COLOR_BLUE, EMBED_COLOR_GREEN, AUTHORIZED_USER_IDS
from lib.cache_handler import CacheHandler

def generate_profile_card_with_skin(data, output="profile_card_with_skin.png"):
    username = data.get("username", "Player")
    rank = data.get("rank", "Champion")
    guild = data.get("guild", "[ETKW] Empire of TKW")
    guild_rank = data.get("guild_rank", "CHIEF ★★★★")
    first_join = data.get("first_join", "2022-10-29")
    last_seen = data.get("last_seen", "2025-07-11")
    mobs = data.get("mobs", 1120452)
    playtime = data.get("playtime", 2495.83)
    chests = data.get("chests", 9056)
    war_count = data.get("war_count", 5644)
    war_rank = data.get("war_rank", "#140")
    pvp_k = data.get("pvp_k", 0)
    pvp_d = data.get("pvp_d", 0)
    quests_done = data.get("quests_done", 736)
    quests_total = data.get("quests_total", 735)
    total_level = data.get("total_level", 7406)
    clears = data.get("clears", {
        "NOTG": 176, "NOL": 2, "TCC": 236, "TNA": 568,
        "Dungeons": 601, "All Raids": 982
    })
    uuid = data.get("uuid", "")
    footer = f"{username}'s Stats | Minister Chikuwa"

    # キャンバスサイズ
    W, H = 800, 1100
    img = Image.new("RGB", (W, H), (233, 223, 197))
    draw = ImageDraw.Draw(img)

    # 背景にノイズで紙質っぽさを追加
    for _ in range(30000):
        x, y = random.randint(0, W - 1), random.randint(0, H - 1)
        c = random.randint(200, 235)
        img.putpixel((x, y), (c, c, c))
    img = img.filter(ImageFilter.GaussianBlur(0.4))

    # フォント（なければデフォルト）
    try:
        title_font = ImageFont.truetype(FONT_PATH, 44)
        header_font = ImageFont.truetype(FONT_PATH, 32)
        text_font = ImageFont.truetype(FONT_PATH, 28)
        small_font = ImageFont.truetype(FONT_PATH, 22)
    except:
        logger.warning(f"Font not found: {FONT_PATH}, using default.")
        title_font = ImageFont.truetype("arial.ttf", 44)
        header_font = ImageFont.truetype("arial.ttf", 32)
        text_font = ImageFont.truetype("arial.ttf", 28)
        small_font = ImageFont.truetype("arial.ttf", 22)
        
    # 外枠
    margin = 30
    draw.rectangle([margin, margin, W - margin, H - margin], outline=(60, 40, 20), width=4)

    # プレイヤー名とランク
    draw.text((50, 50), f"[{rank}] {username}", font=title_font, fill=(120, 20, 20))

    # スキン画像
    if uuid:
        try:
            skin_url = f"https://vzge.me/bust/128/{uuid}"
            headers = {"User-Agent": "Mozilla/5.0"}
            skin_res = requests.get(skin_url, headers=headers)
            if skin_res.status_code == 200:
                skin = Image.open(BytesIO(skin_res.content)).convert("RGBA")
                skin = skin.resize((120, 120), Image.LANCZOS)
                img.paste(skin, (50, 110), mask=skin)
        except:
            draw.rectangle([50, 110, 170, 230], fill=(160, 0, 0))

    # ギルド・日時
    draw.text((200, 110), guild, font=header_font, fill=(30, 20, 20))
    draw.text((200, 150), guild_rank, font=text_font, fill=(30, 20, 20))
    draw.text((200, 190), f"First Joined: {first_join}", font=text_font, fill=(30, 20, 20))
    draw.text((200, 220), f"Last Seen: {last_seen}", font=text_font, fill=(30, 20, 20))

    # セクション線
    draw.line((50, 280, W - 50, 280), fill=(50, 30, 20), width=2)

    # 左右カラム（統計）
    left_stats = [
        f"Mobs {mobs:,}",
        f"Playtime {playtime} hours",
        f"War {war_count} {war_rank}",
        f"Quests {quests_done}",
        f"Total Level {total_level}"
    ]
    right_stats = [
        f"Chests {chests:,}",
        f"PvP {pvp_k} K/{pvp_d} D",
        f"Quests Total {quests_total}",
        f"Total Level {total_level}"
    ]

    y = 310
    for text in left_stats:
        draw.text((60, y), text, font=text_font, fill=(20, 20, 20))
        y += 40

    y = 310
    for text in right_stats:
        draw.text((400, y), text, font=text_font, fill=(20, 20, 20))
        y += 40

    # Raids & Dungeons
    draw.line((50, 530, W - 50, 530), fill=(50, 30, 20), width=2)
    draw.text((60, 550), "Content Clears", font=header_font, fill=(30, 20, 20))

    y = 600
    for k, v in clears.items():
        draw.text((80, y), f"{k}", font=text_font, fill=(20, 20, 20))
        draw.text((280, y), f"{v}", font=text_font, fill=(20, 20, 20))
        y += 40

    # UUID & Footer
    draw.line((50, H - 150, W - 50, H - 150), fill=(50, 30, 20), width=2)
    draw.text((60, H - 130), f"UUID {uuid}", font=small_font, fill=(20, 20, 20))
    draw.text((60, H - 100), footer, font=small_font, fill=(20, 20, 20))

    # TEST
    draw.text((50, 50), "TEST", fill=(0,0,0), font=ImageFont.load_default())

    # 保存
    img.save(output)
    logger.info(f"--- [PlayerCog] Saved {output}")

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

        username = data.get("username", "Player")
        rank = data.get("supportRank", "Player")
        guild_name = self._safe_get(data, ['guild', 'name'], "")
        guild_prefix = self._safe_get(data, ['guild', 'prefix'], "")
        guild = f"[{guild_prefix}] {guild_name}" if guild_name else ""
        guild_rank = self._safe_get(data, ['guild', 'rank'], "")
        guild_rank_stars = self._safe_get(data, ['guild', 'rankStars'], "")
        guild_rank_full = f"{guild_rank} {guild_rank_stars}" if guild_rank or guild_rank_stars else ""
        first_join = self.format_datetime_iso(self._safe_get(data, ['firstJoin'], None))
        last_seen = self.format_datetime_iso(self._safe_get(data, ['lastJoin'], None))
        mobs = self._fallback_stat(data, ['globalData', 'mobsKilled'], ['ranking', 'mobsKilled'], ['previousRanking', 'mobsKilled'])
        playtime = self._fallback_stat(data, ['playtime'], ['ranking', 'playtime'], ['previousRanking', 'playtime'])
        chests = self._fallback_stat(data, ['globalData', 'chestsFound'], ['ranking', 'chestsFound'], ['previousRanking', 'chestsFound'])
        war_count = self._fallback_stat(data, ['globalData', 'wars'], ['ranking', 'wars'], ['previousRanking', 'wars'])
        war_rank = self._safe_get(data, ['ranking', 'warsCompletion'], '非公開')
        if isinstance(war_rank, int):
            war_rank = f"#{war_rank:,}"
        pvp_k = self._fallback_stat(data, ['globalData', 'pvp', 'kills'], ['ranking', 'pvpKills'], ['previousRanking', 'pvpKills'])
        pvp_d = self._fallback_stat(data, ['globalData', 'pvp', 'deaths'], ['ranking', 'pvpDeaths'], ['previousRanking', 'pvpDeaths'])
        quests_done = self._fallback_stat(data, ['globalData', 'completedQuests'], ['ranking', 'completedQuests'], ['previousRanking', 'completedQuests'])
        quests_total = self._safe_get(data, ['globalData', 'questsTotal'], 0)
        total_level = self._fallback_stat(data, ['globalData', 'totalLevel'], ['ranking', 'totalLevel'], ['previousRanking', 'totalLevel'])
        uuid = data.get("uuid", "")

        # Raids/dungeons
        has_raid_list = (
            'globalData' in data and
            isinstance(data['globalData'], dict) and
            'raids' in data['globalData'] and
            isinstance(data['globalData']['raids'], dict) and
            'list' in data['globalData']['raids']
        )
        if has_raid_list:
            raid_list = data['globalData']['raids']['list']
            if raid_list == {}:
                notg = 0
                nol = 0
                tcc = 0
                tna = 0
            else:
                notg = self._safe_get(raid_list, ["Nest of the Grootslangs"], "非公開")
                nol = self._safe_get(raid_list, ["Orphion's Nexus of Light"], "非公開")
                tcc = self._safe_get(raid_list, ["The Canyon Colossus"], "非公開")
                tna = self._safe_get(raid_list, ["The Nameless Anomaly"], "非公開")
        else:
            notg = "非公開"
            nol = "非公開"
            tcc = "非公開"
            tna = "非公開"
        dungeons = self._safe_get(data, ['globalData', 'dungeons', 'total'], "非公開")
        total_raids = self._safe_get(data, ['globalData', 'raids', 'total'], "非公開")

        clears = {
            "NOTG": notg, "NOL": nol, "TCC": tcc, "TNA": tna,
            "Dungeons": dungeons, "All Raids": total_raids
        }

        player_data = {
            "username": username,
            "rank": rank,
            "guild": guild,
            "guild_rank": guild_rank_full,
            "first_join": first_join,
            "last_seen": last_seen,
            "mobs": mobs if isinstance(mobs, int) else 0,
            "playtime": playtime if isinstance(playtime, (int, float)) else 0,
            "chests": chests if isinstance(chests, int) else 0,
            "war_count": war_count if isinstance(war_count, int) else 0,
            "war_rank": war_rank,
            "pvp_k": pvp_k if isinstance(pvp_k, int) else 0,
            "pvp_d": pvp_d if isinstance(pvp_d, int) else 0,
            "quests_done": quests_done if isinstance(quests_done, int) else 0,
            "quests_total": quests_total if isinstance(quests_total, int) else 0,
            "total_level": total_level if isinstance(total_level, int) else 0,
            "clears": clears,
            "uuid": uuid
        }

        output_path = f"profile_card_{uuid}.png" if uuid else "profile_card.png"
        try:
            generate_profile_card_with_skin(player_data, output=output_path)
            file = discord.File(output_path, filename=os.path.basename(output_path))
            await interaction.followup.send(file=file)
            if os.path.exists(output_path):
                os.remove(output_path)
        except Exception as e:
            logger.error(f"画像生成または送信失敗: {e}")
            await interaction.followup.send("プロフィール画像生成に失敗しました。")

async def setup(bot: commands.Bot): await bot.add_cog(PlayerCog(bot))
