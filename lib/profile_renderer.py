from PIL import Image, ImageDraw, ImageFont
import requests
from io import BytesIO
import logging
import os

logger = logging.getLogger(__name__)

FONT_PATH = os.path.join(os.path.dirname(__file__), "../assets/fonts/Minecraftia-Regular.ttf")
BASE_IMG_PATH = os.path.join(os.path.dirname(__file__), "../assets/profile/5bf8ec18-6901-4825-9125-d8aba4d6a4b8.png")
PLAYER_BACKGROUND_PATH = os.path.join(os.path.dirname(__file__), "../assets/profile/IMG_1493.png")
RANK_STAR_PATH = os.path.join(os.path.dirname(__file__), "../assets/profile/rankStar.png")

def generate_profile_card(info, output_path="profile_card.png"):
    try:
        img = Image.open(BASE_IMG_PATH).convert("RGBA")
    except Exception as e:
        logger.error(f"BASE_IMG_PATH 読み込み失敗: {e}")
        img = Image.new("RGBA", (900, 1600), (255, 255, 255, 255))  # fallback
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
        font_prefix = ImageFont.truetype(FONT_PATH, 56)
    except Exception as e:
        logger.error(f"FONT_PATH 読み込み失敗: {e}")
        font_title = font_main = font_sub = font_small = font_uuid = font_mini = font_prefix = ImageFont.load_default()

    # 描画（profile_infoの内容を全部使う）
    draw.text((90, 140), f"[{info.get('support_rank_display', 'Player')}] {info.get('username', 'NoName')}", font=font_title, fill=(60,40,30,255))

    # ギルドバナー描画
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

    # guildバナー描画座標
    banner_x = 330
    banner_y = 250
    banner_size = (76, 150)
    if guild_banner_img:
        guild_banner_img = guild_banner_img.resize(banner_size, Image.LANCZOS)
        img.paste(guild_banner_img, (banner_x, banner_y), mask=guild_banner_img)
    else:
        dummy = Image.new("RGBA", banner_size, (0, 0, 0, 0))
        img.paste(dummy, (banner_x, banner_y), mask=dummy)

    # ギルドプレフィックス用の薄黒色四角＋テキスト（バナーのすぐ下）
    guild_prefix = info.get('guild_prefix', '')
    if guild_prefix:
        # プレフィックス長さに応じて四角サイズ調整
        prefix_len = len(guild_prefix)
        # フォントで実際のサイズを測る
        prefix_text = guild_prefix
        prefix_font = font_prefix
        bbox = draw.textbbox((0,0), prefix_text, font=prefix_font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        # 余白設定
        padding_x = 24
        padding_y = 12
        box_w = text_w + padding_x * 2
        box_h = text_h + padding_y * 2
        # バナー中央下に配置（バナーに少し重ねる位置）
        box_x = banner_x + (banner_size[0] - box_w) // 2
        box_y = banner_y + banner_size[1] - int(box_h * 0.4)
        # 薄黒色四角形（透明度180/255くらい）
        box_color = (30, 30, 30, 180)
        draw.rectangle([box_x, box_y, box_x + box_w, box_y + box_h], fill=box_color)
        # テキスト中央揃え
        text_x = box_x + (box_w - text_w) // 2
        text_y = box_y + (box_h - text_h) // 2
        draw.text((text_x, text_y), prefix_text, font=prefix_font, fill=(240,240,240,255))

    # guild_name
    text_base_x = banner_x + banner_size[0] + 10
    draw.text((text_base_x, banner_y), f"{info.get('guild_name', '')}", font=font_main, fill=(60,40,30,255))

    # guild_rank + rankstars
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
    
    draw.text((330, 400), f"First Join: {info.get('first_join', 'N/A')}", font=font_main, fill=(60,40,30,255))
    draw.text((330, 475), f"Last Seen: {info.get('last_join', 'N/A')}", font=font_main, fill=(60,40,30,255))

    draw.text((90, 600), "Mobs", font=font_sub, fill=(60,40,30,255))
    draw.text((330, 600), f"{info.get('mobs_killed', 0):,}", font=font_sub, fill=(60,40,30,255))

    draw.text((90, 675), "Chests", font=font_sub, fill=(60,40,30,255))
    draw.text((330, 675), f"{info.get('chests', 0):,}", font=font_sub, fill=(60,40,30,255))

    draw.text((90, 800), "Wars", font=font_sub, fill=(60,40,30,255))
    wars_text = f"{info.get('wars', 0):,}"
    draw.text((330, 800), wars_text, font=font_sub, fill=(60,40,30,255))
    bbox = draw.textbbox((330, 800), wars_text, font=font_sub)
    x_wars = bbox[2] + 6
    draw.text((x_wars, 800 + 18), f" #{info.get('war_rank_display', 'N/A')}", font=font_mini, fill=(60,40,30,255))

    draw.text((90, 875), "Quests", font=font_sub, fill=(60,40,30,255))
    draw.text((330, 875), f"{info.get('quests', 0):,}", font=font_sub, fill=(60,40,30,255))

    draw.text((90, 950), f"World Events   {info.get('world_events', 0):,}", font=font_sub, fill=(60,40,30,255))

    draw.text((650, 600), "Playtime", font=font_sub, fill=(60,40,30,255))
    playtime_text = f"{info.get('playtime', 0):,}"
    draw.text((650, 675), playtime_text, font=font_small, fill=(60,40,30,255))
    bbox = draw.textbbox((650, 675), playtime_text, font=font_small)
    x_hours = bbox[2] + 3
    draw.text((x_hours, 675 + 18), "hours", font=font_mini, fill=(60,40,30,255))

    draw.text((650, 750), "PvP", font=font_main, fill=(60,40,30,255))
    pk_text = str(info.get('pvp_kill', 0))
    pd_text = str(info.get('pvp_death', 0))
    draw.text((650, 825), pk_text, font=font_small, fill=(60,40,30,255))
    bbox = draw.textbbox((650, 825), pk_text, font=font_small)
    x_k = bbox[2] + 3
    draw.text((x_k, 825 + 18), "K", font=font_mini, fill=(60,40,30,255))
    draw.text((650, 875), pd_text, font=font_small, fill=(60,40,30,255))
    bbox = draw.textbbox((650, 875), pd_text, font=font_small)
    x_d = bbox[2] + 3
    draw.text((x_d, 875 + 18), "D", font=font_mini, fill=(60,40,30,255))

    draw.text((650, 950), "Total Level", font=font_main, fill=(60,40,30,255))
    total_text = f"{info.get('total_level', 0):,}"
    draw.text((650, 1025), total_text, font=font_small, fill=(60,40,30,255))
    bbox = draw.textbbox((650, 1025), total_text, font=font_small)
    x_lvl = bbox[2] + 3
    draw.text((x_lvl, 1025 + 18), "lv.", font=font_mini, fill=(60,40,30,255))
    
    # Raid/Dungeon
    right_edge_x = 440
    raid_keys = [("NOTG", "notg", 1150), ("NOL", "nol", 1200), ("TCC", "tcc", 1250),
                 ("TNA", "tna", 1300), ("Dungeons", "dungeons", 1350), ("All Raids", "all_raids", 1400)]
    for label, key, y in raid_keys:
        draw.text((100, y), label, font=font_raids, fill=(60,40,30,255))
        num_text = f"{info.get(key, 0)}"
        bbox = draw.textbbox((0,0), num_text, font=font_raids)
        text_width = bbox[2] - bbox[0]
        x = right_edge_x - text_width
        draw.text((x, y), num_text, font=font_raids, fill=(60,40,30,255))

    # UUID
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
    draw.text((475, 1150), "UUID", font=font_raids, fill=(90,90,90,255))
    draw.text((600, 1155), line1, font=font_uuid, fill=(90,90,90,255))
    draw.text((475, 1205), line2, font=font_uuid, fill=(90,90,90,255))

    # スキン画像貼り付け
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

    try:
        img.save(output_path)
    except Exception as e:
        logger.error(f"画像保存失敗: {e}")
    return output_path
