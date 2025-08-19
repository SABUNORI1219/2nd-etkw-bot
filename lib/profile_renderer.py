from PIL import Image, ImageDraw, ImageFont
import requests
from io import BytesIO
import logging
import os

logger = logging.getLogger(__name__)

FONT_PATH = os.path.join(os.path.dirname(__file__), "../assets/fonts/times.ttf")
BASE_IMG_PATH = os.path.join(os.path.dirname(__file__), "../assets/profile/5bf8ec18-6901-4825-9125-d8aba4d6a4b8.png")

def calc_max_fontsize(draw, text1, text2, font_path, area_width, max_fontsize=90, min_fontsize=28):
    """
    area_width: (int) 右端x座標 - 左端x座標
    両方のテキストがこの幅内に収まる最大のフォントサイズを返す
    """
    for size in range(max_fontsize, min_fontsize-1, -1):
        font = ImageFont.truetype(font_path, size)
        bbox1 = draw.textbbox((0, 0), text1, font=font)
        bbox2 = draw.textbbox((0, 0), text2, font=font)
        w1 = bbox1[2] - bbox1[0]
        w2 = bbox2[2] - bbox2[0]
        if w1 < area_width and w2 < area_width:
            return size
    return min_fontsize

def generate_profile_card(info, output_path="profile_card.png"):
    img = Image.open(BASE_IMG_PATH).convert("RGBA")
    draw = ImageDraw.Draw(img)
    W, H = img.size

    # 線の左端と右端
    line_left_x = 80
    line_right_x = 720
    line_y = 90  # 適宜調整

    # 見出しのy座標
    headline_y = 60

    # それぞれのテキスト
    rank_text = f"[{info['support_rank_display']}]"
    player_text = info['username']

    # 最大フォントサイズを計算
    max_width = line_right_x - line_left_x
    font_size = calc_max_fontsize(draw, rank_text, player_text, FONT_PATH, max_width)
    font_title = ImageFont.truetype(FONT_PATH, font_size)

    # [ゲーム内ランク]は左揃えで描画
    draw.text((line_left_x, headline_y), rank_text, font=font_title, fill=(60,40,30,255))

    # プレイヤー名は中央揃え
    bbox_player = draw.textbbox((0, 0), player_text, font=font_title)
    player_w = bbox_player[2] - bbox_player[0]
    center_x = (line_left_x + line_right_x) // 2
    player_x = center_x - player_w // 2
    draw.text((player_x, headline_y), player_text, font=font_title, fill=(60,40,30,255))

    # ギルドなどの描画
    x0 = 300
    y0 = headline_y + font_size + 20
    dy = 44
    draw.text((x0, y0), f"[{info['guild_prefix']}] {info['guild_name']}", font=ImageFont.truetype(FONT_PATH, 38), fill=(60,40,30,255))
    y = y0 + dy
    draw.text((x0, y), f"GuildRank: {info['guild_rank']} [{info['guild_rank_stars']}]", font=ImageFont.truetype(FONT_PATH, 38), fill=(60,40,30,255))
    y += dy + 10
    draw.text((x0, y), f"Mobs killed: {info['mobs_killed']:,}", font=ImageFont.truetype(FONT_PATH, 38), fill=(60,40,30,255))
    y += dy
    draw.text((x0, y), f"Playtime: {info['playtime']:,} h", font=ImageFont.truetype(FONT_PATH, 38), fill=(60,40,30,255))
    y += dy
    draw.text((x0, y), f"Wars: {info['wars']:,} [{info['war_rank_display']}]", font=ImageFont.truetype(FONT_PATH, 38), fill=(60,40,30,255))
    y += dy
    draw.text((x0, y), f"Quests: {info['quests']:,}", font=ImageFont.truetype(FONT_PATH, 38), fill=(60,40,30,255))
    y += dy
    draw.text((x0, y), f"Total Level: {info['total_level']:,}", font=ImageFont.truetype(FONT_PATH, 38), fill=(60,40,30,255))
    y += dy
    draw.text((x0, y), f"Chests: {info['chests']:,}", font=ImageFont.truetype(FONT_PATH, 38), fill=(60,40,30,255))
    y += dy
    draw.text((x0, y), f"PvP: {info['pvp']}", font=ImageFont.truetype(FONT_PATH, 38), fill=(60,40,30,255))
    y += dy + 10

    # Raid/Dungeon
    font_small = ImageFont.truetype(FONT_PATH, 28)
    draw.text((x0, y), f"NOTG: {info['notg']}", font=font_small, fill=(60,40,30,255))
    y += dy - 16
    draw.text((x0, y), f"NOL: {info['nol']}", font=font_small, fill=(60,40,30,255))
    y += dy - 16
    draw.text((x0, y), f"TCC: {info['tcc']}", font=font_small, fill=(60,40,30,255))
    y += dy - 16
    draw.text((x0, y), f"TNA: {info['tna']}", font=font_small, fill=(60,40,30,255))
    y += dy - 16
    draw.text((x0, y), f"Dungeons: {info['dungeons']}", font=font_small, fill=(60,40,30,255))
    y += dy - 16
    draw.text((x0, y), f"All Raids: {info['all_raids']}", font=font_small, fill=(60,40,30,255))
    y += dy

    # UUID
    draw.text((x0, y), f"UUID: {info['uuid']}", font=font_small, fill=(90,90,90,255))

    # スキン画像貼り付け
    uuid = info.get("uuid")
    if uuid:
        try:
            skin_url = f"https://vzge.me/bust/256/{uuid}"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
                "Accept": "image/webp,image/apng,image/*,*/*;q=0.8",
                "Referer": "https://vzge.me/"
            }
            skin_res = requests.get(skin_url, headers=headers)
            if skin_res.status_code != 200:
                raise Exception(f"skin url response: {skin_res.status_code}")
            skin = Image.open(BytesIO(skin_res.content)).convert("RGBA")
            skin = skin.resize((196, 196), Image.LANCZOS)
            img.paste(skin, (106, 336), mask=skin)
        except Exception as e:
            logger.error(f"Skin image load failed: {e}")
            draw.rectangle([60, 120, 180, 240], fill=(160,160,160))

    img.save(output_path)
    logger.info(f"Profile card saved to {output_path}")
    return output_path
