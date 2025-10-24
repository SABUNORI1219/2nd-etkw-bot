from PIL import Image, ImageDraw, ImageFont, ImageFilter
from io import BytesIO
import os
import logging
import random
import math
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)

FONT_PATH = os.path.join(os.path.dirname(__file__), "../assets/fonts/Minecraftia-Regular.ttf")
BANNER_PLACEHOLDER = None

CANVAS_WIDTH = 700
MARGIN = 28
LEFT_COLUMN_WIDTH = 460
RIGHT_COLUMN_WIDTH = CANVAS_WIDTH - LEFT_COLUMN_WIDTH - MARGIN * 2
LINE_COLOR = (40, 40, 40, 255)

BASE_BG_COLOR = (218, 179, 99)
TITLE_COLOR = (40, 30, 20, 255)
SUBTITLE_COLOR = (80, 60, 40, 255)
TABLE_HEADER_BG = (230, 230, 230, 255)

try:
    import numpy as np
    _HAS_NUMPY = True
except Exception:
    _HAS_NUMPY = False

def _load_icon(icon_path, size=None):
    try:
        im = Image.open(icon_path).convert("RGBA")
        if size:
            im = im.resize((size, size), Image.LANCZOS)
        return im
    except Exception:
        return None

ICON_DIR = os.path.join(os.path.dirname(__file__), "../assets/guild_profile")
ICON_PATHS = {
    "member": os.path.join(ICON_DIR, "Member_Icon.png"),
    "war": os.path.join(ICON_DIR, "WarCount_Icon.png"),
    "territory": os.path.join(ICON_DIR, "Territory_Icon.png"),
    "owner": os.path.join(ICON_DIR, "Owner_Icon.png"),
    "created": os.path.join(ICON_DIR, "CreatedOn_Icon.png"),
    "season": os.path.join(ICON_DIR, "SeasonRating_Icon.png"),
    "bow": os.path.join(ICON_DIR, "Bow_Icon.png"),
    "dagger": os.path.join(ICON_DIR, "Dagger_Icon.png"),
    "wand": os.path.join(ICON_DIR, "Wand_Icon.png"),
    "relik": os.path.join(ICON_DIR, "Relik_Icon.png"),
    "spear": os.path.join(ICON_DIR, "Spear_Icon.png"),
}

CLASS_ICON_MAP = {
    "ARCHER": ICON_PATHS["bow"],
    "ASSASSIN": ICON_PATHS["dagger"],
    "MAGE": ICON_PATHS["wand"],
    "SHAMAN": ICON_PATHS["relik"],
    "WARRIOR": ICON_PATHS["spear"],
}

def _fmt_num(v):
    try:
        if isinstance(v, int):
            return f"{v:,}"
        if isinstance(v, float):
            return f"{v:,.0f}"
        return str(v)
    except Exception:
        return str(v)

def _text_width(draw_obj: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> int:
    try:
        return int(draw_obj.textlength(text, font=font))
    except Exception:
        bbox = draw_obj.textbbox((0, 0), text, font=font)
        return bbox[2] - bbox[0]

def draw_status_circle(base_img, left_x, center_y, status="online"):
    circle_radius = 15
    circle_img = Image.new("RGBA", (2*circle_radius, 2*circle_radius), (0,0,0,0))
    draw = ImageDraw.Draw(circle_img)
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
    if status == "online":
        outline_color = (16, 100, 16, 255)
    else:
        outline_color = (180, 32, 32, 255)
    draw.ellipse([0, 0, 2*circle_radius-1, 2*circle_radius-1], outline=outline_color, width=2)
    base_img.alpha_composite(circle_img, (left_x, center_y - circle_radius))

def create_guild_image(guild_data: Dict[str, Any], banner_renderer, max_width: int = CANVAS_WIDTH) -> BytesIO:
    def sg(d, *keys, default="N/A"):
        v = d
        for k in keys:
            if not isinstance(v, dict):
                return default
            v = v.get(k)
            if v is None:
                return default
        return v

    # --- メンバー情報取得 ---
    members = guild_data.get("members", {}) or {}
    online_players: List[Dict[str, str]] = []
    rank_to_stars = {
        "OWNER": "★★★★★",
        "CHIEF": "★★★★",
        "STRATEGIST": "★★★",
        "CAPTAIN": "★★",
        "RECRUITER": "★",
        "RECRUIT": ""
    }
    # クラス情報も取得
    for rank_name, rank_group in members.items():
        if not isinstance(rank_group, dict):
            continue
        for player_name, payload in rank_group.items():
            if isinstance(payload, dict):
                player_data = payload
                if player_data.get("online"):
                    # --- クラス名取得（activeCharacter/type） ---
                    active_char_uuid = player_data.get("activeCharacter")
                    active_char_type = None
                    if active_char_uuid:
                        char_obj = player_data.get("characters", {}).get(active_char_uuid, {})
                        active_char_type = char_obj.get("type")
                        # 例: "ARCHER", "MAGE" など
                    online_players.append({
                        "name": player_name,
                        "server": player_data.get("server", "N/A"),
                        "rank_stars": rank_to_stars.get(rank_name.upper(), ""),
                        "rank": rank_name.upper(),
                        "class_type": active_char_type  # Noneなら非表示
                    })

    prefix = sg(guild_data, "prefix", default="")
    name = sg(guild_data, "name", default="Unknown Guild")
    owner_list = guild_data.get("members", {}).get("owner", {}) or {}
    owner = list(owner_list.keys())[0] if owner_list else "N/A"
    created = sg(guild_data, "created", default="N/A")
    if isinstance(created, str) and "T" in created:
        created = created.split("T")[0]
    level = sg(guild_data, "level", default=0)
    xpPercent = sg(guild_data, "xpPercent", default=0)
    wars = sg(guild_data, "wars", default=0)
    territories = sg(guild_data, "territories", default=0)
    total_members = sg(guild_data, "members", "total", default=0)

    season_ranks = guild_data.get("seasonRanks") or {}
    latest_season = "N/A"
    rating_display = "N/A"
    if isinstance(season_ranks, dict) and season_ranks:
        try:
            latest_season = str(max(int(k) for k in season_ranks.keys()))
            rating = season_ranks.get(latest_season, {}).get("rating", "N/A")
            rating_display = f"{rating:,}" if isinstance(rating, int) else rating
        except Exception:
            latest_season = "N/A"

    banner_img = None
    try:
        banner_bytes = banner_renderer.create_banner_image(guild_data.get("banner")) if banner_renderer is not None else None
        if banner_bytes:
            if isinstance(banner_bytes, (bytes, bytearray)):
                banner_img = Image.open(BytesIO(banner_bytes)).convert("RGBA")
            elif hasattr(banner_bytes, "read"):
                banner_img = Image.open(banner_bytes).convert("RGBA")
    except Exception as e:
        logger.warning(f"バナー生成に失敗: {e}")

    # 固定パラメータ
    img_w = max_width
    margin = 36
    banner_x = img_w - margin - 117   # 右上
    banner_y = margin + 13
    banner_w = 120
    banner_h = 120

    # ギルド名・横線位置
    name_x = margin + 20
    name_y = margin + 10
    line_x1 = name_x - 10
    line_x2 = banner_x - 18
    line_y = name_y + 48 + 16  # ギルド名の下

    # ステータス
    stat_y = line_y + 16
    icon_size = 32
    icon_gap = 8
    left_icon_x = margin

    # 2本目横線
    line_y2 = stat_y + 135

    # Created/Season
    info_y = line_y2 + 12

    # 3本目横線
    line_y3 = line_y2 + 100

    # オンラインメンバー部の高さ動的計算
    role_order = ["CHIEF", "STRATEGIST", "CAPTAIN", "RECRUITER", "RECRUIT"]
    online_by_role = {role: [] for role in role_order}
    for p in online_players:
        rank = p.get("rank", "")
        if rank in online_by_role:
            online_by_role[rank].append(p)
    member_rows = 0
    for role in role_order:
        n = len(online_by_role[role])
        member_rows += max(1, math.ceil(n / 2)) if n else 1
    role_header_height = 32 * len(role_order)
    member_height = 30 * member_rows
    footer_height = 36
    extra_height = 30
    img_h = line_y3 + 18 + role_header_height + member_height + footer_height + extra_height

    img = create_card_background(img_w, img_h)
    draw = ImageDraw.Draw(img)

    try:
        font_title_base = ImageFont.truetype(FONT_PATH, 48)
        font_sub = ImageFont.truetype(FONT_PATH, 24)
        font_stats = ImageFont.truetype(FONT_PATH, 22)
        font_small = ImageFont.truetype(FONT_PATH, 16)
        font_section = ImageFont.truetype(FONT_PATH, 26)
        font_rank = ImageFont.truetype(FONT_PATH, 22)
    except Exception as e:
        logger.error(f"FONT_PATH 読み込み失敗: {e}")
        font_title_base = font_sub = font_stats = font_small = font_section = font_rank = ImageFont.load_default()

    # アイコン読込
    member_icon = _load_icon(ICON_PATHS["member"], icon_size)
    war_icon = _load_icon(ICON_PATHS["war"], icon_size)
    territory_icon = _load_icon(ICON_PATHS["territory"], icon_size)
    owner_icon = _load_icon(ICON_PATHS["owner"], icon_size)
    created_icon = _load_icon(ICON_PATHS["created"], icon_size)
    season_icon = _load_icon(ICON_PATHS["season"], icon_size)
    # クラスアイコン
    class_icons = {}
    for class_name, path in CLASS_ICON_MAP.items():
        class_icons[class_name] = _load_icon(path, 28)

    # バナー画像（右上固定座標）
    if banner_img:
        img.paste(banner_img, (banner_x, banner_y), mask=banner_img)

    # ギルド名（左揃え、横線の上。横線を飛び出す場合はフォント自動縮小）
    guild_name = name
    font_title = font_title_base
    max_name_width = line_x2 - name_x
    name_w = _text_width(draw, guild_name, font_title)
    font_size = 48
    while name_w > max_name_width and font_size > 16:
        font_size -= 2
        font_title = ImageFont.truetype(FONT_PATH, font_size)
        name_w = _text_width(draw, guild_name, font_title)
    draw.text((name_x, name_y), guild_name, font=font_title, fill=TITLE_COLOR)

    # 横線
    draw.line([(line_x1, line_y), (line_x2, line_y)], fill=LINE_COLOR, width=2)

    # ステータスアイコン・XPバー（固定座標）
    stat_icon_x = margin + 20
    stat_icon_y = stat_y
    draw.rectangle([stat_icon_x, stat_icon_y, stat_icon_x + icon_size, stat_icon_y + icon_size], fill=(220,180,80,255), outline=LINE_COLOR)
    draw.text((stat_icon_x + icon_size // 2, stat_icon_y + icon_size // 2), str(level), font=font_stats, fill=TITLE_COLOR, anchor="mm")
    xpbar_x = stat_icon_x + icon_size + icon_gap
    xpbar_y = stat_icon_y + icon_size // 2 - 12
    xpbar_w = 220
    xpbar_h = 24
    draw.rectangle([xpbar_x, xpbar_y, xpbar_x + xpbar_w, xpbar_y + xpbar_h], fill=(120, 100, 80, 255))
    xp_fill = float(xpPercent) / 100.0 if xpPercent else 0
    fill_w = int(xpbar_w * xp_fill)
    bar_color = (60, 144, 255, 255) if xp_fill >= 0.8 else (44, 180, 90, 255) if xp_fill >= 0.5 else (220, 160, 52, 255)
    if fill_w > 0:
        draw.rectangle([xpbar_x, xpbar_y, xpbar_x + fill_w, xpbar_y + xpbar_h], fill=bar_color)
    draw.rectangle([xpbar_x, xpbar_y, xpbar_x + xpbar_w, xpbar_y + xpbar_h], outline=LINE_COLOR)
    draw.text((xpbar_x + xpbar_w + 10, xpbar_y + xpbar_h // 2), f"{xpPercent}%", font=font_stats, fill=TITLE_COLOR, anchor="lm")

    # 他ステータスアイコン群（横並び固定座標）
    stats_gap = 80
    stats_y2 = stat_icon_y + icon_size + 12
    stats_x = margin + 20
    stats_x2 = stats_x + stats_gap

    # メンバー数
    if member_icon:
        img.paste(member_icon, (stats_x, stats_y2), mask=member_icon)
    draw.text((stats_x + icon_size + 8, stats_y2 + 4), f"{len(online_players)}/{total_members}", font=font_stats, fill=TITLE_COLOR)

    # War数
    if war_icon:
        img.paste(war_icon, (stats_x2 + 140, stats_y2), mask=war_icon)
    draw.text((stats_x2 + icon_size + 8 + 140, stats_y2 + 4), f"{_fmt_num(wars)}", font=font_stats, fill=TITLE_COLOR)

    # 領地数
    if territory_icon:
        img.paste(territory_icon, (stats_x, stats_y2 + 42), mask=territory_icon)
    draw.text((stats_x + icon_size + 8, stats_y2 + 46), f"{_fmt_num(territories)}", font=font_stats, fill=TITLE_COLOR)

    # オーナー
    if owner_icon:
        img.paste(owner_icon, (stats_x2 + 140, stats_y2 + 42), mask=owner_icon)
    draw.text((stats_x2 + icon_size + 8 + 140, stats_y2 + 46), owner, font=font_stats, fill=TITLE_COLOR)

    # 2本目横線
    draw.line([(line_x1, line_y2), (img_w - margin - 8, line_y2)], fill=LINE_COLOR, width=2)

    # Created/Season（アイコン＋テキスト）
    created_x = margin + 20
    season_x = created_x
    if created_icon:
        img.paste(created_icon, (created_x, info_y), mask=created_icon)
        draw.text((created_x + icon_size + 8, info_y + 4), f"Since {created}", font=font_stats, fill=TITLE_COLOR)
    else:
        draw.text((created_x, info_y), f"Created on: {created}", font=font_stats, fill=TITLE_COLOR)
    if season_icon:
        img.paste(season_icon, (season_x, info_y + 42), mask=season_icon)
        draw.text((season_x + icon_size + 8, info_y + 46), f"{rating_display} SR (Season {latest_season})", font=font_stats, fill=TITLE_COLOR)
    else:
        draw.text((season_x, info_y), f"Latest SR: {rating_display} (Season {latest_season})", font=font_stats, fill=TITLE_COLOR)

    # 3本目横線
    draw.line([(line_x1, line_y3), (img_w - margin - 8, line_y3)], fill=LINE_COLOR, width=2)

    # === オンラインメンバー（役職ごと・2列表示＋クラスアイコン/ステータス丸/表示位置調整） ===
    role_header_y = line_y3 + 18
    col_gap = 240
    role_x1 = margin + 20
    role_x2 = img_w // 2 + 20
    row_h = 30
    member_y = role_header_y

    role_display_map = {
        "CHIEF": "****CHIEF",
        "STRATEGIST": "***STRATEGIST",
        "CAPTAIN": "**CAPTAIN",
        "RECRUITER": "*RECRUITER",
        "RECRUIT": "RECRUIT"
    }

    world_font = font_rank
    status_circle_size = 28
    for role in role_order:
        draw.text((role_x1, member_y), role_display_map[role], font=font_section, fill=TITLE_COLOR)
        member_y += 32

        group_members = online_by_role[role]
        for i in range(0, len(group_members), 2):
            # 一列目
            p1 = group_members[i]
            # 二列目
            p2 = group_members[i + 1] if i + 1 < len(group_members) else None

            # --- 一列目 ---
            x_base = role_x1
            y_base = member_y
            # クラスアイコン描画
            class_type1 = p1.get("class_type")
            icon_x = x_base
            if class_type1 and class_type1 in class_icons and class_icons[class_type1]:
                icon_img = class_icons[class_type1]
                img.paste(icon_img, (icon_x, y_base), mask=icon_img)
                name_x = icon_x + status_circle_size + 4
            else:
                name_x = icon_x
            # 名前描画
            name1 = p1.get("name", "Unknown")
            draw.text((name_x, y_base), name1, font=font_rank, fill=TITLE_COLOR)
            # ステータス丸＋ワールド名（画像の半分の位置からちょっと左を終端）
            server1 = p1.get("server", "")
            if server1:
                status_circle_x = img_w // 2 - status_circle_size - 16
                status_circle_y = y_base + 11
                draw_status_circle(img, status_circle_x, status_circle_y, status="online")
                world_x = status_circle_x + status_circle_size + 4
                world_text_w = _text_width(draw, server1, world_font)
                # ワールド名終端：画像の半分の位置からちょっと左
                max_world_x = img_w // 2 + 10
                # ワールド名がはみ出す場合は左詰め
                if world_x + world_text_w > max_world_x:
                    world_x = max_world_x - world_text_w
                draw.text((world_x, y_base), server1, font=world_font, fill=SUBTITLE_COLOR)

            # --- 二列目 ---
            if p2:
                x_base_2 = role_x2
                y_base_2 = member_y
                class_type2 = p2.get("class_type")
                icon_x2 = x_base_2
                if class_type2 and class_type2 in class_icons and class_icons[class_type2]:
                    icon_img2 = class_icons[class_type2]
                    img.paste(icon_img2, (icon_x2, y_base_2), mask=icon_img2)
                    name_x2 = icon_x2 + status_circle_size + 4
                else:
                    name_x2 = icon_x2
                name2 = p2.get("name", "Unknown")
                draw.text((name_x2, y_base_2), name2, font=font_rank, fill=TITLE_COLOR)
                server2 = p2.get("server", "")
                if server2:
                    # ステータス丸＋ワールド名（画像の半分より右端まで）
                    status_circle_x2 = img_w - margin - 8 - status_circle_size - 10
                    status_circle_y2 = y_base_2 + 11
                    draw_status_circle(img, status_circle_x2, status_circle_y2, status="online")
                    world_x2 = status_circle_x2 + status_circle_size + 4
                    world_text_w2 = _text_width(draw, server2, world_font)
                    max_world_x2 = img_w - margin - 8
                    if world_x2 + world_text_w2 > max_world_x2:
                        world_x2 = max_world_x2 - world_text_w2
                    draw.text((world_x2, y_base_2), server2, font=world_font, fill=SUBTITLE_COLOR)
            member_y += row_h
        member_y += 8

    # フッター
    footer_text = "Generated by Minister Chikuwa#5740"
    try:
        fw = _text_width(draw, footer_text, font=font_small)
    except Exception:
        bbox = draw.textbbox((0, 0), footer_text, font=font_small)
        fw = bbox[2] - bbox[0]
    draw.text((img_w - fw - 8, img_h - 4 - 17), footer_text, font=font_small, fill=(120, 110, 100, 255))

    out_bytes = BytesIO()
    img.save(out_bytes, format="PNG")
    out_bytes.seek(0)

    try:
        if isinstance(banner_img, Image.Image):
            banner_img.close()
    except Exception:
        pass

    return out_bytes
