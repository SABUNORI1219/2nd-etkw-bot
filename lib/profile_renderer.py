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
    font_main = ImageFont.truetype(FONT_PATH, 45)
    font_small = ImageFont.truetype(FONT_PATH, 35)
    font_title = ImageFont.truetype(FONT_PATH, 50)

    # 位置など仮
    x0 = 300
    y0 = 500
    dy = 44

    # 描画（profile_infoの内容を全部使う）
    draw.text((90, 150), f"[{info['support_rank_display']}] {info['username']}", font=font_title, fill=(60,40,30,255))
    
    draw.text((330, 250), f"[{info['guild_prefix']}] {info['guild_name']}", font=font_main, fill=(60,40,30,255))

    draw.text((330, 325), f"GuildRank: {info['guild_rank']} [{info['guild_rank_stars']}]", font=font_main, fill=(60,40,30,255))
    
    draw.text((330, 400), f"First Join: {info['first_join']}", font=font_main, fill=(60,40,30,255))
    
    draw.text((330, 475), f"Last Seen: {info['last_join']}", font=font_main, fill=(60,40,30,255))

    draw.text((90, 700), f"Mobs killed      {info['mobs_killed']:,}", font=font_main, fill=(60,40,30,255))

    draw.text((90, 775), f"Playtime         {info['playtime']:,} hours", font=font_main, fill=(60,40,30,255))

    draw.text((90, 850), f"Wars             {info['wars']:,} [{info['war_rank_display']}]", font=font_main, fill=(60,40,30,255))

    draw.text((90, 925), f"Quests           {info['quests']:,}", font=font_main, fill=(60,40,30,255))

    draw.text((90, 1000), f"Total Level     {info['total_level']:,}", font=font_main, fill=(60,40,30,255))

    draw.text((600, 650), "Chests", font=font_main, fill=(60,40,30,255))
    draw.text((600, 725), f"{info['chests']:,}", font=font_main, fill=(60,40,30,255))

    draw.text((600, 810), "PvP", font=font_main, fill=(60,40,30,255))
    draw.text((600, 885), f"{info['pvp']}", font=font_main, fill=(60,40,30,255))

    # Raid/Dungeon
    draw.text((100, 1100), f"NOTG        {info['notg']}", font=font_small, fill=(60,40,30,255))

    draw.text((100, 1175), f"NOL:        {info['nol']}", font=font_small, fill=(60,40,30,255))

    draw.text((100, 1250), f"TCC:        {info['tcc']}", font=font_small, fill=(60,40,30,255))

    draw.text((100, 1325), f"TNA:        {info['tna']}", font=font_small, fill=(60,40,30,255))
  
    draw.text((100, 1400), f"Dungeons:   {info['dungeons']}", font=font_small, fill=(60,40,30,255))

    draw.text((100, 1475), f"All Raids:  {info['all_raids']}", font=font_small, fill=(60,40,30,255))

    # UUID
    draw.text((400, 1150), f"UUID   {info['uuid']}", font=font_small, fill=(90,90,90,255))

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
