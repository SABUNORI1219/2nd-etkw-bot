from PIL import Image, ImageDraw, ImageFont, ImageFilter
import requests
from io import BytesIO
import logging
import os
import asyncio
from lib.api_stocker import OtherAPI

logger = logging.getLogger(__name__)

FONT_PATH = os.path.join(os.path.dirname(__file__), "../assets/fonts/Minecraftia-Regular.ttf")
BASE_IMG_PATH = os.path.join(os.path.dirname(__file__), "../assets/profile/profile_card.png")
PLAYER_BACKGROUND_PATH = os.path.join(os.path.dirname(__file__), "../assets/profile/IMG_1493.png")
RANK_STAR_PATH = os.path.join(os.path.dirname(__file__), "../assets/profile/rankStar.png")
UNKNOWN_SKIN_PATH = os.path.join(os.path.dirname(__file__), "../assets/profile/unknown_skin.png")
RANK_ICON_MAP = {
    "Champion": os.path.join(os.path.dirname(__file__), "../assets/profile/champ_icon.png"),
    "Hero+": os.path.join(os.path.dirname(__file__), "../assets/profile/heroplus_icon.png"),
    "Hero": os.path.join(os.path.dirname(__file__), "../assets/profile/hero_icon.png"),
    "Vip+": os.path.join(os.path.dirname(__file__), "../assets/profile/vipplus_icon.png"),
    "Vip": os.path.join(os.path.dirname(__file__), "../assets/profile/vip_icon.png"),
}
RANK_COLOR_MAP = {
    "Champion": ((255, 255, 80, 230), (255, 210, 60, 200)),     # 黄色グラデ
    "Hero+": ((255, 40, 255, 230), (180, 0, 120, 200)),         # マゼンタ
    "Hero": ((170, 90, 255, 230), (60, 0, 160, 200)),           # 紫
    "Vip+": ((80, 255, 255, 230), (40, 170, 255, 200)),         # 水色
    "Vip": ((80, 255, 120, 230), (0, 190, 40, 200)),            # 緑
    "None": ((160, 160, 160, 220), (80, 80, 80, 200)),          # 灰色
}

def gradient_rect(size, color_top, color_bottom, radius):
    w, h = size
    base = Image.new("RGBA", (w, h), (0,0,0,0))
    for y in range(h):
        ratio = y / h
        r = int(color_top[0] * (1-ratio) + color_bottom[0] * ratio)
        g = int(color_top[1] * (1-ratio) + color_bottom[1] * ratio)
        b = int(color_top[2] * (1-ratio) + color_bottom[2] * ratio)
        a = int(color_top[3] * (1-ratio) + color_bottom[3] * ratio)
        ImageDraw.Draw(base).line([(0, y), (w, y)], fill=(r, g, b, a))
    mask = Image.new("L", (w, h), 0)
    draw_mask = ImageDraw.Draw(mask)
    draw_mask.rounded_rectangle([0, 0, w, h], radius=radius, fill=255)
    base.putalpha(mask)
    return base

def resize_icon_keep_ratio(img, target_height):
    w, h = img.size
    scale = target_height / h
    target_w = int(w * scale)
    return img.resize((target_w, target_height), Image.LANCZOS)

def fmt_num(val):
    if isinstance(val, int) or isinstance(val, float):
        return f"{val:,}"
    return str(val)

def split_guild_name_by_pixel_and_word(guild_name, font, text_base_x, threshold_x, draw):
    words = guild_name.split()
    # 判定は開始位置+テキスト幅
    if text_base_x + draw.textlength(guild_name, font=font) <= threshold_x:
        return [guild_name]
    # 2単語以上なら均等分割
    if len(words) > 1:
        best_split = 1
        min_diff = float('inf')
        for i in range(1, len(words)):
            line1 = " ".join(words[:i])
            line2 = " ".join(words[i:])
            l1_len = draw.textlength(line1, font=font)
            l2_len = draw.textlength(line2, font=font)
            diff = abs(l1_len - l2_len)
            if diff < min_diff:
                min_diff = diff
                best_split = i
        return [" ".join(words[:best_split]), " ".join(words[best_split:])]
    else:
        # 1単語しかない場合は強制分割
        # 文字数の半分で分割する例（実際はピクセル長で分割した方がよい）
        text = words[0]
        for i in range(1, len(text)):
            part1 = text[:i]
            part2 = text[i:]
            if text_base_x + draw.textlength(part1, font=font) > threshold_x:
                return [part1, part2]
        # 最後まで行っても分割しないなら（すごく小さい単語）、そのまま
        return [text]

def draw_status_circle(base_img, left_x, center_y, status="online"):
    circle_radius = 15
    circle_img = Image.new("RGBA", (2*circle_radius, 2*circle_radius), (0,0,0,0))
    draw = ImageDraw.Draw(circle_img)

    # ラジアルグラデーション（中央明るめ、外側暗め）
    for r in range(circle_radius, 0, -1):
        ratio = r / circle_radius
        if status == "online":
            col = (
                int(60 + 140 * ratio),
                int(230 - 60 * ratio),
                int(60 + 20 * ratio),
                255
            )
        else:
            col = (
                int(220 - 40 * ratio),
                int(60 + 40 * ratio),
                int(60 + 40 * ratio),
                255
            )
        draw.ellipse([circle_radius-r, circle_radius-r, circle_radius+r, circle_radius+r], fill=col)

    # 輪郭（アウトライン）を描画
    if status == "online":
        outline_color = (16, 100, 16, 255)
    else:
        outline_color = (180, 32, 32, 255)
    # 1px太さで外周に楕円描画
    draw.ellipse([0, 0, 2*circle_radius-1, 2*circle_radius-1], outline=outline_color, width=2)

    # 影は描画しない（絵文字風にシャープに仕上げる）
    base_img.alpha_composite(circle_img, (left_x, center_y - circle_radius))

def generate_profile_card(info, output_path="profile_card.png"):
    try:
        img = Image.open(BASE_IMG_PATH).convert("RGBA")
    except Exception as e:
        logger.error(f"BASE_IMG_PATH 読み込み失敗: {e}")
        img = Image.new("RGBA", (900, 1600), (255, 255, 255, 255))
    try:
        PLAYER_BACKGROUND = Image.open(PLAYER_BACKGROUND_PATH).convert("RGBA")
    except Exception as e:
        logger.error(f"PLAYER_BACKGROUND_PATH 読み込み失敗: {e}")
        PLAYER_BACKGROUND = Image.new("RGBA", (200, 200), (200, 200, 200, 255))
    try:
        rank_star_img = Image.open(RANK_STAR_PATH).convert("RGBA")
    except Exception as e:
        logger.error(f"RANK_STAR_PATH 読み込み失敗: {e}")
        rank_star_img = Image.new("RGBA", (200, 200), (200, 200, 200, 255))
    draw = ImageDraw.Draw(img)
    W, H = img.size
    star_size = 50
    rank_star_img = rank_star_img.resize((star_size, star_size), Image.LANCZOS)

    # フォント設定
    try:
        font_title = ImageFont.truetype(FONT_PATH, 50)
        font_main = ImageFont.truetype(FONT_PATH, 45)
        font_sub = ImageFont.truetype(FONT_PATH, 43)
        font_small = ImageFont.truetype(FONT_PATH, 40)
        font_raids = ImageFont.truetype(FONT_PATH, 35)
        font_uuid = ImageFont.truetype(FONT_PATH, 30)
        font_mini = ImageFont.truetype(FONT_PATH, 25)
        font_rank = ImageFont.truetype(FONT_PATH, 16)
        font_prefix = ImageFont.truetype(FONT_PATH, 12)
    except Exception as e:
        logger.error(f"FONT_PATH 読み込み失敗: {e}")
        font_title = font_main = font_sub = font_small = font_uuid = font_mini = font_prefix = font_rank = ImageFont.load_default()

    draw.text((90, 140), f"{info.get('username', 'No Name')}", font=font_title, fill=(60,40,30,255))

    banner_bytes = info.get("banner_bytes")
    guild_banner_img = None
    if banner_bytes and isinstance(banner_bytes, BytesIO):
        try:
            guild_banner_img = Image.open(banner_bytes).convert("RGBA")
        except Exception as e:
            logger.error(f"guild_banner_img読み込み失敗: {e}")
            guild_banner_img = None
    elif banner_bytes and isinstance(banner_bytes, str):
        guild_banner_img = None

    banner_x = 330
    banner_y = 250
    banner_size = (76, 150)
    if guild_banner_img:
        guild_banner_img = guild_banner_img.resize(banner_size, Image.LANCZOS)
        img.paste(guild_banner_img, (banner_x, banner_y), mask=guild_banner_img)
    else:
        dummy = Image.new("RGBA", banner_size, (0, 0, 0, 0))
        img.paste(dummy, (banner_x, banner_y), mask=dummy)

    guild_prefix = info.get('guild_prefix', '')
    guild_name = info.get('guild_name', '')
    if not guild_name or guild_name == "Hidden":
        guild_name_display = "No Guild"
    else:
        guild_name_display = guild_name
        
    if guild_prefix:
        prefix_text = guild_prefix
        prefix_font = font_prefix
        bbox = draw.textbbox((0,0), prefix_text, font=prefix_font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        padding_x = 6
        padding_y = 2
        box_w = text_w + padding_x * 2
        box_h = text_h + padding_y * 2
        box_x = banner_x + (banner_size[0] - box_w) // 2
        box_y = banner_y + banner_size[1] - int(box_h * 0.4)
        shadow = Image.new("RGBA", (box_w+8, box_h+8), (0,0,0,0))
        shadow_draw = ImageDraw.Draw(shadow)
        shadow_draw.rounded_rectangle([4,4,box_w+4,box_h+4], radius=16, fill=(0,0,0,80))
        shadow = shadow.filter(ImageFilter.GaussianBlur(3))
        img.paste(shadow, (box_x-4, box_y-4), mask=shadow)
        rect_img = gradient_rect((box_w, box_h), (30,30,30,220), (60,60,60,160), radius=14)
        img.paste(rect_img, (box_x, box_y), mask=rect_img)
        text_x = box_x + (box_w - text_w) // 2
        text_y = box_y + (box_h - text_h) // 2
        draw.text((text_x, text_y), prefix_text, font=prefix_font, fill=(240,240,240,255))
        
    img.paste(PLAYER_BACKGROUND, (110, 280), mask=PLAYER_BACKGROUND)
    uuid = info.get("uuid", "")
    if uuid:
        try:
            other_api = OtherAPI()
            skin_bytes = None
            try:
                skin_bytes = asyncio.run(other_api.get_vzge_skin(uuid))
            except Exception as e:
                logger.error(f"Skin image async get failed: {e}")
                skin_bytes = None

            if skin_bytes:
                skin = Image.open(BytesIO(skin_bytes)).convert("RGBA")
                skin = skin.resize((196, 196), Image.LANCZOS)
                img.paste(skin, (106, 340), mask=skin)
            else:
                # fallback: unknown_skin
                unknown_skin = Image.open(UNKNOWN_SKIN_PATH).convert("RGBA")
                unknown_skin = unknown_skin.resize((196, 196), Image.LANCZOS)
                img.paste(unknown_skin, (106, 340), mask=unknown_skin)
        except Exception as e:
            logger.error(f"Skin image load failed: {e}")
            try:
                unknown_skin = Image.open(UNKNOWN_SKIN_PATH).convert("RGBA")
                unknown_skin = unknown_skin.resize((196, 196), Image.LANCZOS)
                img.paste(unknown_skin, (106, 340), mask=unknown_skin)
            except Exception as ee:
                logger.error(f"Unknown skin image load failed: {ee}")

    rank_text = info.get('support_rank_display')
    rank_colors = RANK_COLOR_MAP.get(rank_text, RANK_COLOR_MAP['None'])
    rank_font = font_rank
    rank_bbox = draw.textbbox((0,0), rank_text, font=rank_font)
    rank_text_w = rank_bbox[2] - rank_bbox[0]
    rank_text_h = rank_bbox[3] - rank_bbox[1]
    icon_path = RANK_ICON_MAP.get(rank_text)
    icon_img = None
    icon_w, icon_h = 0, 0
    target_icon_h = 24
    if icon_path and os.path.exists(icon_path):
        try:
            original_icon = Image.open(icon_path).convert("RGBA")
            icon_img = resize_icon_keep_ratio(original_icon, target_icon_h)
            icon_w, icon_h = icon_img.size
        except Exception as e:
            logger.error(f"Rank icon load failed: {e}")
    else:
        icon_w, icon_h = 0, target_icon_h

    rank_padding_x = 12
    rank_padding_y = 4
    rank_box_w = icon_w + rank_padding_x + rank_text_w + rank_padding_x
    rank_box_h = max(icon_h, rank_text_h + rank_padding_y*2)
    skin_x = 106
    skin_y = 336
    skin_w = 196
    skin_h = 196
