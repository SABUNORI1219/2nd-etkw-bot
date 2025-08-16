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

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONT_PATH = os.path.join(project_root, "assets", "fonts", "times.ttf")

from lib.wynncraft_api import WynncraftAPI
from config import EMBED_COLOR_BLUE, EMBED_COLOR_GREEN, AUTHORIZED_USER_IDS
from lib.cache_handler import CacheHandler

def generate_profile_card_with_skin(data, output="profile_card_with_skin.png"):
    # データ読み込み
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

    # キャンバスセットアップ
    W, H = 1000, 1400
    img = Image.new("RGB", (W, H), (233, 223, 197))
    draw = ImageDraw.Draw(img)

    # 背景にざらつきノイズ追加
    for _ in range(20000):
        x, y = random.randint(0, W-1), random.randint(0, H-1)
        c = random.randint(200, 235)
        img.putpixel((x, y), (c, c, c))
    img = img.filter(ImageFilter.GaussianBlur(0.3))

    # フォント準備    
    try:
        title_font = ImageFont.truetype(FONT_PATH, 72)
        header_font = ImageFont.truetype(FONT_PATH, 40)
        text_font = ImageFont.truetype(FONT_PATH, 28)
        small_font = ImageFont.truetype(FONT_PATH, 22)
    except Exception as e:
        # フォントエラーは必ずログ出力（重要）
        logger.error(f"Font load failed: {e}")
        # デフォルトフォント必須
        title_font = ImageFont.load_default()
        header_font = ImageFont.load_default()
        text_font = ImageFont.load_default()
        small_font = ImageFont.load_default()
    # 外枠
    margin = 40
    draw.rectangle([margin, margin, W - margin, H - margin], outline=(40, 30, 20), width=6)

    # --- タイトル ---
    draw.text((W//2 - 200, 60), f"The Wynncraft Gazette", font=title_font, fill=(20, 10, 10))

    # --- プレイヤー名 & ランク ---
    draw.text((60, 160), f"[{rank}] {username}", font=header_font, fill=(40, 20, 20))

    # --- ギルド情報 ---
    draw.text((250, 220), guild, font=header_font, fill=(30, 20, 20))
    draw.text((250, 270), guild_rank, font=text_font, fill=(30, 20, 20))
    draw.text((250, 320), f"First Joined: {first_join}", font=text_font, fill=(30, 20, 20))
    draw.text((250, 360), f"Last Seen: {last_seen}", font=text_font, fill=(30, 20, 20))

    # スキン画像取得＆貼り付け
    if uuid:
        try:
            skin_url = f"https://vzge.me/bust/256/{uuid}"
            headers = {'User-Agent': 'DiscordBot/1.0'}
            skin_res = requests.get(skin_url, headers=headers)
            if skin_res.status_code != 200:
                raise Exception(f"skin url response: {skin_res.status_code}")
            skin = Image.open(BytesIO(skin_res.content)).convert("RGBA")
            skin = skin.resize((120, 120), Image.LANCZOS)
            img.paste(skin, (60, 120), mask=skin)
        except Exception as e:
            draw.rectangle([60, 120, 180, 240], fill=(160,160,160))

    # --- セクション罫線 ---
    draw.line((60, 430, 940, 430), fill=(50, 30, 20), width=4)

    # --- 左右2カラム ---
    col1_x, col2_x = 80, 540
    y_start = 460
    spacing = 50

    left_stats = [
        f"Mobs {mobs:,}",
        f"Playtime {playtime} h",
        f"War {war_count} {war_rank}",
        f"Quests {quests_done}",
        f"Total Level {total_level}"
    ]

    right_stats = [
        f"Chests {chests:,}",
        f"Quests Total {quests_total}",
        f"Total Level {total_level}"
    ]

    y = y_start
    for text in left_stats:
        draw.text((col1_x, y), text, font=text_font, fill=(20, 20, 20))
        y += spacing

    y = y_start
    for text in right_stats:
        draw.text((col2_x, y), text, font=text_font, fill=(20, 20, 20))
        y += spacing

    # --- Raids & Dungeons ---
    draw.line((60, 720, 940, 720), fill=(50, 30, 20), width=4)
    draw.text((60, 740), "Content Clears", font=header_font, fill=(30, 20, 20))

    y = 800
    for k, v in clears.items():
        draw.text((80, y), f"{k}", font=text_font, fill=(20, 20, 20))
        draw.text((280, y), f"{v}", font=text_font, fill=(20, 20, 20))
        y += 40

    # --- フッター ---
    draw.line((60, H-120, 940, H-120), fill=(50, 30, 20), width=3)
    draw.text((80, H-100), f"UUID {uuid}", font=small_font, fill=(20, 20, 20))
    draw.text((80, H-70), footer, font=small_font, fill=(20, 20, 20))

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
