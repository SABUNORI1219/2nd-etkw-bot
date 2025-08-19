from PIL import Image, ImageDraw, ImageFont
import requests
from io import BytesIO
import logging
import os

logger = logging.getLogger(__name__)

FONT_PATH = os.path.join(os.path.dirname(__file__), "../assets/fonts/times.ttf")
BASE_IMG_PATH = os.path.join(os.path.dirname(__file__), "../assets/profile/5bf8ec18-6901-4825-9125-d8aba4d6a4b8.png")

def get_exact_fontsize(draw, text, font_path, target_width, max_fontsize=90, min_fontsize=28):
    """
    target_widthピッタリになるフォントサイズを計算（小数点サイズも許容）
    """
    # まず、最大・最小サイズで幅を計測
    font_max = ImageFont.truetype(font_path, max_fontsize)
    w_max = draw.textbbox((0, 0), text, font=font_max)[2]
    font_min = ImageFont.truetype(font_path, min_fontsize)
    w_min = draw.textbbox((0, 0), text, font=font_min)[2]

    logger.info(f"[get_exact_fontsize] w_max={w_max} (size={max_fontsize}), w_min={w_min} (size={min_fontsize})")

    # 幅がmaxでもtarget_widthより小さい場合はmaxを返す
    if w_max <= target_width:
        logger.info(f"[get_exact_fontsize] max_fontsize fits target_width, use {max_fontsize}")
        return max_fontsize
    # 幅がminでもtarget_widthより大きい場合はminを返す
    if w_min > target_width:
        logger.info(f"[get_exact_fontsize] min_fontsize too big, use {min_fontsize}")
        return min_fontsize

    # 2点間で線形補間
    # (f1, w1), (f2, w2) → target_width になる f
    # f = f1 + (target_width - w1) / (w2 - w1) * (f2 - f1)
    f1, w1 = min_fontsize, w_min
    f2, w2 = max_fontsize, w_max
    # w2 > w1なので計算
    font_size = f1 + (target_width - w1) / (w2 - w1) * (f2 - f1)
    font_size = max(min_fontsize, min(max_fontsize, font_size))

    # Pillowは小数点サイズも受け付ける
    font_exact = ImageFont.truetype(font_path, int(font_size))
    w_exact = draw.textbbox((0, 0), text, font=font_exact)[2]
    logger.info(f"[get_exact_fontsize] font_size={font_size}, w_exact={w_exact}, target_width={target_width}")

    # 640px超の場合は1小さいサイズで再計算
    if w_exact > target_width:
        font_exact = ImageFont.truetype(font_path, int(font_size)-1)
        font_size = int(font_size)-1
        w_exact = draw.textbbox((0, 0), text, font=font_exact)[2]
        logger.info(f"[get_exact_fontsize] font_size adjusted to {font_size}, w_exact={w_exact}")

    return font_size

def generate_profile_card(info, output_path="profile_card.png"):
    img = Image.open(BASE_IMG_PATH).convert("RGBA")
    draw = ImageDraw.Draw(img)
    W, H = img.size
    area_width = 640
    left_x = (W - area_width) // 2
    right_x = left_x + area_width
    headline_y = 150

    combined_text = f"[{info['support_rank_display']}] {info['username']}"
    font_size = get_exact_fontsize(draw, combined_text, FONT_PATH, area_width)
    font_title = ImageFont.truetype(FONT_PATH, int(font_size))
    bbox = draw.textbbox((0, 0), combined_text, font=font_title)
    text_w = bbox[2] - bbox[0]
    center_x = (left_x + right_x) // 2
    text_x = center_x - (text_w // 2)
    logger.info(f"[generate_profile_card] image_size: {W}x{H}")
    logger.info(f"[generate_profile_card] draw区間: left_x={left_x}, right_x={right_x}, area_width={area_width}")
    logger.info(f"[generate_profile_card] combined_text: '{combined_text}'")
    logger.info(f"[generate_profile_card] font_size: {font_size}, text_w: {text_w}")
    logger.info(f"[generate_profile_card] center_x: {center_x}, text_x: {text_x}")
    logger.info(f"[generate_profile_card] 右余白: {right_x - (text_x + text_w)}px, 左余白: {text_x - left_x}px")

    draw.text((text_x, headline_y), combined_text, font=font_title, fill=(60,40,30,255))

    # ギルドなどの描画
    x0 = 300
    y0 = headline_y + font_size + 20
    dy = 44
    font_main = ImageFont.truetype(FONT_PATH, 38)
    draw.text((x0, y0), f"[{info['guild_prefix']}] {info['guild_name']}", font=font_main, fill=(60,40,30,255))
    y = y0 + dy
    draw.text((x0, y), f"GuildRank: {info['guild_rank']} [{info['guild_rank_stars']}]", font=font_main, fill=(60,40,30,255))
    y += dy + 10
    draw.text((x0, y), f"Mobs killed: {info['mobs_killed']:,}", font=font_main, fill=(60,40,30,255))
    y += dy
    draw.text((x0, y), f"Playtime: {info['playtime']:,} h", font=font_main, fill=(60,40,30,255))
    y += dy
    draw.text((x0, y), f"Wars: {info['wars']:,} [{info['war_rank_display']}]", font=font_main, fill=(60,40,30,255))
    y += dy
    draw.text((x0, y), f"Quests: {info['quests']:,}", font=font_main, fill=(60,40,30,255))
    y += dy
    draw.text((x0, y), f"Total Level: {info['total_level']:,}", font=font_main, fill=(60,40,30,255))
    y += dy
    draw.text((x0, y), f"Chests: {info['chests']:,}", font=font_main, fill=(60,40,30,255))
    y += dy
    draw.text((x0, y), f"PvP: {info['pvp']}", font=font_main, fill=(60,40,30,255))
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
