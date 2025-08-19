from PIL import Image, ImageDraw, ImageFont
import requests
from io import BytesIO
import logging

# loggingセット
logger = logging.getLogger(__name__)

# 画像やフォントのパス
BASE_IMG_PATH = "assets/profile/5bf8ec18-6901-4825-9125-d8aba4d6a4b8.png"
FONT_PATH = "assets/fonts/times.ttf"

def draw_profile_card(data, output_path="profile_card_output.png"):
    # ベース画像読み込み
    img = Image.open(BASE_IMG_PATH).convert("RGBA")
    draw = ImageDraw.Draw(img)
    W, H = img.size

    # フォント（調整はsizeを変えて）
    font_main = ImageFont.truetype(FONT_PATH, 38)
    font_small = ImageFont.truetype(FONT_PATH, 28)
    font_title = ImageFont.truetype(FONT_PATH, 46)

    # テキスト描画座標（調整用）
    x0 = 220
    y0 = 70
    dy = 44

    # データ取得
    username = data.get("username")
    support_rank_display = data.get("support_rank_display")
    guild_prefix = data.get("guild_prefix")
    guild_name = data.get("guild_name")
    guild_rank = data.get("guild_rank")
    guild_rank_stars = data.get("guild_rank_stars")
    mobs_killed = data.get("mobs_killed")
    playtime = data.get("playtime")
    wars = data.get("wars")
    war_rank_display = data.get("war_rank_display")
    quests = data.get("quests")
    total_level = data.get("total_level")
    chests = data.get("chests")
    pvp = data.get("pvp")
    notg = data.get("notg")
    nol = data.get("nol")
    tcc = data.get("tcc")
    tna = data.get("tna")
    dungeons = data.get("dungeons")
    all_raids = data.get("all_raids")
    uuid = data.get("uuid")

    # 1. タイトル行
    draw.text((x0, y0), f"[{support_rank_display}] {username}", font=font_title, fill=(60,40,30,255))
    y = y0 + dy + 20

    # 2. ギルド情報
    draw.text((x0, y), f"[{guild_prefix}] {guild_name}", font=font_main, fill=(60,40,30,255))
    y += dy
    draw.text((x0, y), f"GuildRank: {guild_rank} [{guild_rank_stars}]", font=font_main, fill=(60,40,30,255))
    y += dy + 10

    # 3. 各種情報
    draw.text((x0, y), f"Mobs killed: {mobs_killed:,}", font=font_main, fill=(60,40,30,255))
    y += dy
    draw.text((x0, y), f"Playtime: {playtime:,} h", font=font_main, fill=(60,40,30,255))
    y += dy
    draw.text((x0, y), f"Wars: {wars:,} [{war_rank_display}]", font=font_main, fill=(60,40,30,255))
    y += dy
    draw.text((x0, y), f"Quests: {quests:,}", font=font_main, fill=(60,40,30,255))
    y += dy
    draw.text((x0, y), f"Total Level: {total_level:,}", font=font_main, fill=(60,40,30,255))
    y += dy
    draw.text((x0, y), f"Chests: {chests:,}", font=font_main, fill=(60,40,30,255))
    y += dy
    draw.text((x0, y), f"PvP: {pvp}", font=font_main, fill=(60,40,30,255))
    y += dy + 10

    # 4. Raid/Dungeon情報
    draw.text((x0, y), f"NOTG: {notg}", font=font_small, fill=(60,40,30,255))
    y += dy - 16
    draw.text((x0, y), f"NOL: {nol}", font=font_small, fill=(60,40,30,255))
    y += dy - 16
    draw.text((x0, y), f"TCC: {tcc}", font=font_small, fill=(60,40,30,255))
    y += dy - 16
    draw.text((x0, y), f"TNA: {tna}", font=font_small, fill=(60,40,30,255))
    y += dy - 16
    draw.text((x0, y), f"Dungeons: {dungeons}", font=font_small, fill=(60,40,30,255))
    y += dy - 16
    draw.text((x0, y), f"All Raids: {all_raids}", font=font_small, fill=(60,40,30,255))
    y += dy

    # 5. UUID
    draw.text((x0, y), f"UUID: {uuid}", font=font_small, fill=(90,90,90,255))

    # 6. Skin画像貼り付け
    if uuid:
        try:
            skin_url = f"https://vzge.me/bust/256/{uuid}"
            headers = {"User-Agent": "Mozilla/5.0"}
            skin_res = requests.get(skin_url, headers=headers)
            logger.info(f"Skin GET url: {skin_url} status: {skin_res.status_code}")
            if skin_res.status_code != 200:
                raise Exception(f"skin url response: {skin_res.status_code}")
            skin = Image.open(BytesIO(skin_res.content)).convert("RGBA")
            skin = skin.resize((120, 120), Image.LANCZOS)
            img.paste(skin, (60, 120), mask=skin)
        except Exception as e:
            logger.error(f"Skin image load failed: {e}")
            draw.rectangle([60, 120, 180, 240], fill=(160,160,160))

    img.save(output_path)
    logger.info(f"Profile card saved to {output_path}")
    return output_path

# 使用例（APIデータをdataとして渡す）
# draw_profile_card(data, output_path="profile_card_output.png")
