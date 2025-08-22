from PIL import Image, ImageDraw, ImageFont, ImageFilter
import requests
from io import BytesIO
import logging
import os

logger = logging.getLogger(__name__)

FONT_PATH = os.path.join(os.path.dirname(__file__), "../assets/fonts/Minecraftia-Regular.ttf")
BASE_IMG_PATH = os.path.join(os.path.dirname(__file__), "../assets/profile/profile_card.png")
WYNN_ICON_PATH = os.path.join(os.path.dirname(__file__), "../assets/profile/wynn_icon.png")
PLAYER_BACKGROUND_PATH = os.path.join(os.path.dirname(__file__), "../assets/profile/IMG_1493.png")
RANK_STAR_PATH = os.path.join(os.path.dirname(__file__), "../assets/profile/rankStar.png")
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

def paste_wynn_icon_bg(base_img, icon_path, pos=(0,0), target_size=(120,120), alpha=160):
    try:
        icon_img = Image.open(icon_path).convert("RGBA")
        icon_img = icon_img.resize(target_size, Image.LANCZOS)
        alpha_layer = icon_img.split()[3].point(lambda p: alpha)
        icon_img.putalpha(alpha_layer)
        base_img.alpha_composite(icon_img, pos)
    except Exception as e:
        logger.error(f"Wynncraftアイコン読み込み失敗: {e}")

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

    paste_wynn_icon_bg(img, WYNN_ICON_PATH, pos=(650, 1320), target_size=(120,120), alpha=160)

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
            draw.rectangle([60, 120, 180, 240], fill=(160,160,160,255))

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
    
    rank_box_x = skin_x + (skin_w // 2) - (rank_box_w // 2)
    rank_box_y = skin_y + skin_h - 6

    shadow = Image.new("RGBA", (rank_box_w+8, rank_box_h+8), (0,0,0,0))
    shadow_draw = ImageDraw.Draw(shadow)
    shadow_draw.rounded_rectangle([4,4,rank_box_w+4,rank_box_h+4], radius=16, fill=(0,0,0,80))
    shadow = shadow.filter(ImageFilter.GaussianBlur(3))
    img.paste(shadow, (rank_box_x-4, rank_box_y-4), mask=shadow)

    rect_img = gradient_rect((rank_box_w, rank_box_h), rank_colors[0], rank_colors[1], radius=14)
    img.paste(rect_img, (rank_box_x, rank_box_y), mask=rect_img)

    if icon_img:
        icon_y = rank_box_y + (rank_box_h - icon_h)//2
        img.paste(icon_img, (rank_box_x + rank_padding_x//2, icon_y), mask=icon_img)
        rank_text_x = rank_box_x + icon_w + rank_padding_x
    else:
        rank_text_x = rank_box_x + rank_padding_x
    rank_text_y = rank_box_y + (rank_box_h - rank_text_h) // 2
    draw.text((rank_text_x, rank_text_y), rank_text, font=rank_font, fill=(255,255,255,255))

    text_base_x = banner_x + banner_size[0] + 10
    guild_name_lines = split_guild_name_by_pixel_and_word(guild_name_display, font_main, text_base_x, 1000, draw)
    if len(guild_name_lines) == 1:
        draw.text((text_base_x, banner_y), guild_name_lines[0], font=font_main, fill=(60,40,30,255))
    else:
        try:
            font_guild_small = ImageFont.truetype(FONT_PATH, 33)
        except Exception:
            font_guild_small = ImageFont.load_default()
        draw.text((text_base_x, banner_y), guild_name_lines[0], font=font_guild_small, fill=(60,40,30,255))
        draw.text((text_base_x, banner_y + 33 + 5), guild_name_lines[1], font=font_guild_small, fill=(60,40,30,255))
        banner_y += 10

    guild_rank_text = str(info.get('guild_rank', ''))
    star_num = 0
    if guild_rank_text == "OWNER":
        star_num = 5
    elif guild_rank_text == "CHIEF":
        star_num = 4
    elif guild_rank_text == "STRATEGIST":
        star_num = 3
    elif guild_rank_text == "CAPTAIN":
        star_num = 2
    elif guild_rank_text == "RECRUITER":
        star_num = 1
    draw.text((text_base_x, banner_y + 75), f"{guild_rank_text}", font=font_main, fill=(60,40,30,255))
    bbox = draw.textbbox((text_base_x, banner_y + 75), f"{guild_rank_text}", font=font_main)
    x_grank = bbox[2] + 10
    y_star = banner_y + 80
    for i in range(star_num):
        x = x_grank + i * (star_size)
        img.paste(rank_star_img, (x, y_star), mask=rank_star_img)

    server_display = info.get('server_display', 'Unknown')
    active_char_info = info.get('active_char_info', 'Unknown')
    # 左側にステータス丸（オンライン：緑、オフライン：赤）を描画
    status_circle_x = 330
    status_circle_y = 410 + 35
    text_x = status_circle_x + 45
    text_y = 413
    if not server_display.lower() == "offline":
        draw_status_circle(img, status_circle_x, status_circle_y, status="online")
    else:
        draw_status_circle(img, status_circle_x, status_circle_y, status="offline")
    draw.text((text_x, text_y), f"{server_display}", font=font_main, fill=(60,40,30,255))
    draw.text((330, text_y+75), f"Class: {active_char_info}", font=font_main, fill=(60,40,30,255))

    draw.text((90, 610), f"First Join: {info.get('first_join', 'N/A')}", font=font_raids, fill=(60,40,30,255))
    draw.text((90, 685), f"Last Seen: {info.get('last_join', 'N/A')}", font=font_raids, fill=(60,40,30,255))
    
    draw.text((90, 800), "Mobs", font=font_sub, fill=(60,40,30,255))
    draw.text((330, 800), fmt_num(info.get('mobs_killed', 0)), font=font_sub, fill=(60,40,30,255))

    draw.text((90, 875), "Chests", font=font_sub, fill=(60,40,30,255))
    draw.text((330, 875), fmt_num(info.get('chests', 0)), font=font_sub, fill=(60,40,30,255))

    draw.text((90, 950), "Quests", font=font_sub, fill=(60,40,30,255))
    draw.text((330, 950), fmt_num(info.get('quests', 0)), font=font_sub, fill=(60,40,30,255))

    draw.text((650, 600), "Playtime", font=font_sub, fill=(60,40,30,255))
    playtime_text = fmt_num(info.get('playtime', 0))
    draw.text((650, 675), playtime_text, font=font_small, fill=(60,40,30,255))
    bbox = draw.textbbox((650, 675), playtime_text, font=font_small)
    x_hours = bbox[2] + 3
    draw.text((x_hours, 675 + 18), "hours", font=font_mini, fill=(60,40,30,255))

    draw.text((650, 750), "PvP", font=font_main, fill=(60,40,30,255))
    pk_text = fmt_num(info.get('pvp_kill', 0))
    pd_text = fmt_num(info.get('pvp_death', 0))
    draw.text((650, 825), pk_text, font=font_small, fill=(60,40,30,255))
    bbox = draw.textbbox((650, 825), pk_text, font=font_small)
    x_k = bbox[2] + 3
    draw.text((x_k, 825 + 18), "K", font=font_mini, fill=(60,40,30,255))
    draw.text((650, 875), pd_text, font=font_small, fill=(60,40,30,255))
    bbox = draw.textbbox((650, 875), pd_text, font=font_small)
    x_d = bbox[2] + 3
    draw.text((x_d, 875 + 18), "D", font=font_mini, fill=(60,40,30,255))

    draw.text((650, 950), "Total Level", font=font_main, fill=(60,40,30,255))
    total_text = fmt_num(info.get('total_level', 0))
    draw.text((650, 1025), total_text, font=font_small, fill=(60,40,30,255))
    bbox = draw.textbbox((650, 1025), total_text, font=font_small)
    x_lvl = bbox[2] + 3
    draw.text((x_lvl, 1025 + 18), "lv.", font=font_mini, fill=(60,40,30,255))

    draw.text((90, 1065), "Content Clears", font=font_main, fill=(60,40,30,255))

    right_edge_x = 440
    raid_keys = [("NOTG", "notg", 1150), ("NOL", "nol", 1200), ("TCC", "tcc", 1250),
                 ("TNA", "tna", 1300), ("Dungeons", "dungeons", 1350), ("All Raids", "all_raids", 1400)]
    for label, key, y in raid_keys:
        draw.text((100, y), label, font=font_raids, fill=(60,40,30,255))
        num_text = fmt_num(info.get(key, 0))
        bbox = draw.textbbox((0,0), num_text, font=font_raids)
        text_width = bbox[2] - bbox[0]
        x = right_edge_x - text_width
        draw.text((x, y), num_text, font=font_raids, fill=(60,40,30,255))

    wars_text = fmt_num(info.get('wars', 0))
    war_rank_display_text = f"#{info.get('war_rank_display', 'N/A')}"
    world_events_text = fmt_num(info.get('world_events', 0))
    draw.text((475, 1150), "Wars", font=font_raids, fill=(60,40,30,255))
    draw.text((475, 1200), "WEs", font=font_raids, fill=(60,40,30,255))
    y_wars = 1150
    y_world_events = 1200
    x_right_align = 775

    bbox_wars = draw.textbbox((0,0), wars_text, font=font_raids)
    wars_width = bbox_wars[2] - bbox_wars[0]
    draw.text((x_right_align - wars_width, y_wars), wars_text, font=font_raids, fill=(60,40,30,255))

    bbox_war_rank = draw.textbbox((0,0), war_rank_display_text, font=font_mini)
    war_rank_width = bbox_war_rank[2] - bbox_war_rank[0]
    draw.text((x_right_align + 12, y_wars + 12), war_rank_display_text, font=font_mini, fill=(60,40,30,255))

    bbox_we = draw.textbbox((0,0), world_events_text, font=font_raids)
    we_width = bbox_we[2] - bbox_we[0]
    draw.text((x_right_align - we_width, y_world_events), world_events_text, font=font_raids, fill=(60,40,30,255))

    uuid = info.get("uuid", "")
    if uuid and '-' in uuid:
        parts = uuid.split('-')
        if len(parts) == 5:
            line1 = f"{parts[0]}-{parts[1]}"
            line2 = f"{parts[2]}-{parts[3]}-{parts[4]}"
        else:
            line1 = uuid
            line2 = ""
    else:
        line1 = line2 = ""
    draw.text((475, 1275), "UUID", font=font_raids, fill=(90,90,90,255))
    draw.text((600, 1280), line1, font=font_uuid, fill=(90,90,90,255))
    draw.text((475, 1320), line2, font=font_uuid, fill=(90,90,90,255))

    draw.text((585, 1400), "Generated by", font=font_mini, fill=(60,40,30,255))
    draw.text((635, 1435), "Minister Chikuwa#5740", font=font_mini, fill=(60,40,30,255))

    try:
        img.save(output_path)
    except Exception as e:
        logger.error(f"画像保存失敗: {e}")
    return output_path
