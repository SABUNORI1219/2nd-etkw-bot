from PIL import Image, ImageDraw, ImageFont
import requests
from io import BytesIO
import logging
import os

logger = logging.getLogger(__name__)

FONT_PATH = os.path.join(os.path.dirname(__file__), "../assets/fonts/Minecraftia-Regular.ttf")
BASE_IMG_PATH = os.path.join(os.path.dirname(__file__), "../assets/profile/5bf8ec18-6901-4825-9125-d8aba4d6a4b8.png")
PLAYER_BACKGROUND_PATH = os.path.join(os.path.dirname(__file__), "../assets/profile/IMG_1493.png")

def generate_profile_card(info, output_path="profile_card.png"):
    img = Image.open(BASE_IMG_PATH).convert("RGBA")
    PLAYER_BACKGROUND = Image.open(PLAYER_BACKGROUND_PATH).convert("RGBA")
    draw = ImageDraw.Draw(img)
    W, H = img.size

    # フォント設定
    font_title = ImageFont.truetype(FONT_PATH, 50)
    font_main = ImageFont.truetype(FONT_PATH, 45)
    font_sub = ImageFont.truetype(FONT_PATH, 43)
    font_small = ImageFont.truetype(FONT_PATH, 40)
    font_hours = ImageFont.truetype(FONT_PATH, 25)

    # 描画（profile_infoの内容を全部使う）
    draw.text((90, 140), f"[{info['support_rank_display']}] {info['username']}", font=font_title, fill=(60,40,30,255))
    
    draw.text((330, 250), f"[{info['guild_prefix']}] {info['guild_name']}", font=font_main, fill=(60,40,30,255))

    draw.text((330, 325), f"{info['guild_rank']} [{info['guild_rank_stars']}]", font=font_main, fill=(60,40,30,255))
    
    draw.text((330, 400), f"First Join: {info['first_join']}", font=font_main, fill=(60,40,30,255))
    
    draw.text((330, 475), f"Last Seen: {info['last_join']}", font=font_main, fill=(60,40,30,255))

    draw.text((90, 600), "Mobs", font=font_sub, fill=(60,40,30,255))
    draw.text((330, 600), f"{info['mobs_killed']:,}", font=font_sub, fill=(60,40,30,255))

    draw.text((90, 675), "Playtime", font=font_sub, fill=(60,40,30,255))
    playtime_text = f"{info['playtime']:,}"
    draw.text((330, 675), playtime_text, font=font_sub, fill=(60,40,30,255))
    bbox = draw.textbbox((330, 675), playtime_text, font=font_sub)
    x_hours = bbox[2] + 6
    draw.text((x_hours, 675 + 8), "hours", font=font_hours, fill=(60,40,30,255))

    draw.text((90, 800), "Wars", font=font_sub, fill=(60,40,30,255))
    draw.text((330, 800), f"{info['wars']:,} (#{info['war_rank_display']})", font=font_sub, fill=(60,40,30,255))

    draw.text((90, 875), "Quests", font=font_sub, fill=(60,40,30,255))
    draw.text((330, 875), f"{info['quests']:,}", font=font_sub, fill=(60,40,30,255))

    draw.text((90, 950), "Total Level", font=font_sub, fill=(60,40,30,255))
    draw.text((330, 950), f"{info['total_level']:,}", font=font_sub, fill=(60,40,30,255))

    draw.text((700, 600), "Chests", font=font_sub, fill=(60,40,30,255))
    draw.text((700, 650), f"{info['chests']:,}", font=font_sub, fill=(60,40,30,255))

    draw.text((700, 725), "PvP", font=font_sub, fill=(60,40,30,255))
    draw.text((700, 775), f"{info['pvp']}", font=font_sub, fill=(60,40,30,255))

    # Raid/Dungeon
    draw.text((100, 1150), "NOTG", font=font_small, fill=(60,40,30,255))
    draw.text((330, 1150), f"{info['notg']}", font=font_small, fill=(60,40,30,255))

    draw.text((100, 1200), "NOL", font=font_small, fill=(60,40,30,255))
    draw.text((330, 1200), f"{info['nol']}", font=font_small, fill=(60,40,30,255))

    draw.text((100, 1250), "TCC", font=font_small, fill=(60,40,30,255))
    draw.text((330, 1250), f"{info['tcc']}", font=font_small, fill=(60,40,30,255))

    draw.text((100, 1300), "TNA", font=font_small, fill=(60,40,30,255))
    draw.text((330, 1300), f"{info['tna']}", font=font_small, fill=(60,40,30,255))
  
    draw.text((100, 1350), "Dungeons", font=font_small, fill=(60,40,30,255))
    draw.text((330, 1350), f"{info['dungeons']}", font=font_small, fill=(60,40,30,255))

    draw.text((100, 1400), "All Raids", font=font_small, fill=(60,40,30,255))
    draw.text((330, 1400), f"{info['all_raids']}", font=font_small, fill=(60,40,30,255))

    # UUID
    uuid = info['uuid']
    parts = uuid.split('-')
    line1 = f"{parts[0]}-{parts[1]}"
    line2 = f"{parts[2]}-{parts[3]}-{parts[4]}"
    draw.text((475, 1150), f"UUID   {line1}", font=font_small, fill=(90,90,90,255))
    draw.text((475, 1200), line2, font=font_small, fill=(90,90,90,255))

    # スキン画像貼り付け
    img.paste(PLAYER_BACKGROUND, (110, 280), mask=PLAYER_BACKGROUND)
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
    return output_path
