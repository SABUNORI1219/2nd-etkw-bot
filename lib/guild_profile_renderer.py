from PIL import Image, ImageDraw, ImageFont, ImageFilter
from io import BytesIO
import os
import logging
import random
import math
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)

FONT_PATH = os.path.join(os.path.dirname(__file__), "../assets/fonts/Minecraftia-Regular.ttf")
ICON_DIR = os.path.join(os.path.dirname(__file__), "../assets/guild_profile")
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


def _arc_point(bbox, angle_deg):
    x0, y0, x1, y1 = bbox
    cx = (x0 + x1) / 2.0
    cy = (y0 + y1) / 2.0
    rx = (x1 - x0) / 2.0
    ry = (y1 - y0) / 2.0
    rad = math.radians(angle_deg)
    x = cx + rx * math.cos(rad)
    y = cy - ry * math.sin(rad)
    return (x, y)


def _extend_point(p, q, amount):
    px, py = p
    qx, qy = q
    dx = qx - px
    dy = qy - py
    dist = math.hypot(dx, dy)
    if dist == 0:
        return qx, qy
    ux = dx / dist
    uy = dy / dist
    return (px + ux * amount, py + uy * amount)

def _load_icon(name, size):
    """assets/guild_profile/{name}.png を読み込み、RGBAで正方形にリサイズして返す。"""
    pth = os.path.join(ICON_DIR, f"{name}.png")
    try:
        im = Image.open(pth).convert("RGBA")
        if size is not None:
            im = im.resize((size, size), Image.LANCZOS)
        return im
    except Exception:
        return None

def draw_decorative_frame(
    img: Image.Image,
    outer_offset: Optional[int] = None,
    outer_width: int = 8,
    inner_offset: Optional[int] = None,
    inner_width: int = 2,
    frame_color=(85, 50, 30, 255),
    # 個別調整用（直線）
    line_inset_outer_top: Optional[int] = None,
    line_inset_outer_bottom: Optional[int] = None,
    line_inset_outer_left: Optional[int] = None,
    line_inset_outer_right: Optional[int] = None,
    line_inset_inner_top: Optional[int] = None,
    line_inset_inner_bottom: Optional[int] = None,
    line_inset_inner_left: Optional[int] = None,
    line_inset_inner_right: Optional[int] = None,
    # 個別調整用（アーチ位置）
    arc_nudge_outer_topleft_x: int = -4,
    arc_nudge_outer_topleft_y: int = -27.5,
    arc_nudge_outer_topright_x: int = 3.75,
    arc_nudge_outer_topright_y: int = -27.5,
    arc_nudge_outer_bottomleft_x: int = -4,
    arc_nudge_outer_bottomleft_y: int = 27.5,
    arc_nudge_outer_bottomright_x: int = 3.75,
    arc_nudge_outer_bottomright_y: int = 27.5,
    arc_nudge_inner_topleft_x: int = -2,
    arc_nudge_inner_topleft_y: int = -25,
    arc_nudge_inner_topright_x: int = 2,
    arc_nudge_inner_topright_y: int = -25,
    arc_nudge_inner_bottomleft_x: int = -2,
    arc_nudge_inner_bottomleft_y: int = 25,
    arc_nudge_inner_bottomright_x: int = 2,
    arc_nudge_inner_bottomright_y: int = 25,
    # 個別corner_trim
    corner_trim_top: Optional[int] = -10,
    corner_trim_bottom: Optional[int] = -10,
    corner_trim_left: Optional[int] = -45,
    corner_trim_right: Optional[int] = -45,
    # 共通corner_trim（個別指定なければ使う）
    corner_trim: Optional[int] = None,
) -> Image.Image:
    ### ... unchanged, see previous code ...

    # (省略: 前回までと同じフレーム描画部分)

    # ...省略...
    return out

def create_card_background(w: int, h: int,
                           noise_std: float = 30.0,
                           noise_blend: float = 0.30,
                           vignette_blur: int = 80) -> Image.Image:
    base = Image.new('RGB', (w, h), BASE_BG_COLOR)

    # ノイズ生成（省略可能）
    if _HAS_NUMPY:
        try:
            noise = np.random.normal(128, noise_std, (h, w))
            noise = np.clip(noise, 0, 255).astype(np.uint8)
            noise_img = Image.fromarray(noise, mode='L').convert('RGB')
        except Exception:
            noise_img = Image.effect_noise((w, h), max(10, int(noise_std))).convert('L').convert('RGB')
    else:
        try:
            noise_img = Image.effect_noise((w, h), max(10, int(noise_std))).convert('L').convert('RGB')
        except Exception:
            noise_img = Image.new('RGB', (w, h), (128, 128, 128))
            nd = ImageDraw.Draw(noise_img)
            for _ in range(max(100, w * h // 1200)):
                x = random.randrange(0, w)
                y = random.randrange(0, h)
                tone = random.randint(90, 180)
                nd.point((x, y), fill=(tone, tone, tone))

    img = Image.blend(base, noise_img, noise_blend)
    img = img.filter(ImageFilter.GaussianBlur(1))

    # ビネット
    vignette = Image.new('L', (w, h), 0)
    dv = ImageDraw.Draw(vignette)
    max_r = int(max(w, h) * 0.75)
    for i in range(0, max_r, max(6, max_r // 60)):
        val = int(255 * (i / max_r))
        bbox = (-i, -i, w + i, h + i)
        dv.ellipse(bbox, fill=val)
    vignette = vignette.filter(ImageFilter.GaussianBlur(vignette_blur))
    vignette = vignette.point(lambda p: max(0, min(255, p)))

    dark_color = (50, 30, 10)
    dark_img = Image.new('RGB', (w, h), dark_color)
    composed = Image.composite(img, dark_img, vignette)

    try:
        composed = draw_decorative_frame(composed.convert('RGBA'),
                                         outer_offset=60,
                                         outer_width=max(6, int(w * 0.01)),
                                         inner_offset=64,
                                         inner_width=max(1, int(w * 0.005)),
                                         frame_color=(85, 50, 30, 255))
    except Exception as e:
        logger.exception(f"draw_decorative_frame failed: {e}")
        # img, composed両方必ず定義されているのでここでどちらでもOK
        return img.convert('RGBA')
    return composed

def create_guild_image(guild_data: Dict[str, Any], banner_renderer, max_width: int = CANVAS_WIDTH) -> BytesIO:
    # アイコン名マッピング
    icon_map = {
        "level": "level",
        "member": "member",
        "war": "war",
        "territory": "territory",
        "owner": "owner",
        "chief": "chief",
        "strategist": "strategist",
        "captain": "captain",
        "recruiter": "recruiter",
        "recruit": "recruit",
        "server": "server",
        "xpbar_bg": "xpbar_bg",
        "xpbar_fg": "xpbar_fg",
        "banner": "banner",
    }

    def sg(d, *keys, default="N/A"):
        v = d
        for k in keys:
            if not isinstance(v, dict):
                return default
            v = v.get(k)
            if v is None:
                return default
        return v

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
    for rank_name, rank_group in members.items():
        if not isinstance(rank_group, dict):
            continue
        for player_name, payload in rank_group.items():
            if isinstance(payload, dict):
                player_data = payload
                if player_data.get("online"):
                    online_players.append({
                        "name": player_name,
                        "server": player_data.get("server", "N/A"),
                        "rank_stars": rank_to_stars.get(rank_name.upper(), "")
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

    # === レイアウト定義 ===
    img_w = max_width
    img_h = 700 + 220  # +α
    img = create_card_background(img_w, img_h)
    draw = ImageDraw.Draw(img)

    # --- フォント準備 ---
    try:
        font_title = ImageFont.truetype(FONT_PATH, 48)
        font_sub = ImageFont.truetype(FONT_PATH, 24)
        font_stats = ImageFont.truetype(FONT_PATH, 22)
        font_small = ImageFont.truetype(FONT_PATH, 16)
        font_section = ImageFont.truetype(FONT_PATH, 26)
        font_rank = ImageFont.truetype(FONT_PATH, 22)
    except Exception as e:
        logger.error(f"FONT_PATH 読み込み失敗: {e}")
        font_title = font_sub = font_stats = font_small = font_section = font_rank = ImageFont.load_default()

    # --- ギルド名行 ---
    margin = 36
    top_y = margin
    # ギルド名（中央揃え）
    guild_name = name
    draw.text((img_w // 2, top_y), guild_name, font=font_title, fill=TITLE_COLOR, anchor="ma")

    # バナー
    banner_size = 80
    banner_x = img_w - margin - banner_size
    banner_y = top_y
    if banner_img:
        try:
            banner_resized = banner_img.resize((banner_size, banner_size), Image.LANCZOS)
            img.paste(banner_resized, (banner_x, banner_y), mask=banner_resized)
        except Exception as e:
            logger.warning(f"バナー貼付失敗: {e}")

    # アンダーバー
    line_y = top_y + 60
    draw.line([(margin, line_y), (img_w - margin, line_y)], fill=LINE_COLOR, width=3)

    # --- レベル・XPバー・ステータスアイコン群 ---
    icon_size = 32
    stats_y = line_y + 18

    level_icon = _load_icon(icon_map["level"], icon_size)
    member_icon = _load_icon(icon_map["member"], icon_size)
    war_icon = _load_icon(icon_map["war"], icon_size)
    territory_icon = _load_icon(icon_map["territory"], icon_size)
    owner_icon = _load_icon(icon_map["owner"], icon_size)
    xpbar_bg_icon = _load_icon(icon_map["xpbar_bg"], 180)
    xpbar_fg_icon = _load_icon(icon_map["xpbar_fg"], 180)

    # アイコン位置
    stats_x = margin
    x = stats_x
    y = stats_y
    # レベルアイコン
    if level_icon:
        img.paste(level_icon, (x, y), mask=level_icon)
    draw.text((x + icon_size + 4, y + 6), f"{level}", font=font_stats, fill=TITLE_COLOR)
    x += icon_size + 60

    # XPバー
    bar_x = x
    bar_y = y
    bar_w = 180
    bar_h = 24
    # バー背景
    if xpbar_bg_icon:
        img.paste(xpbar_bg_icon, (bar_x, bar_y), mask=xpbar_bg_icon)
    else:
        draw.rectangle([bar_x, bar_y, bar_x + bar_w, bar_y + bar_h], fill=(100, 80, 70, 255))
    # バー進捗
    xp_fill = float(xpPercent) / 100.0 if xpPercent else 0
    fill_w = int(bar_w * xp_fill)
    bar_color = (60, 144, 255, 255) if xp_fill >= 0.8 else (44, 180, 90, 255) if xp_fill >= 0.5 else (220, 160, 52, 255)
    if fill_w > 0:
        draw.rectangle([bar_x, bar_y, bar_x + fill_w, bar_y + bar_h], fill=bar_color)
    # バー前景アイコン
    if xpbar_fg_icon:
        img.paste(xpbar_fg_icon, (bar_x, bar_y), mask=xpbar_fg_icon)
    # XP%
    draw.text((bar_x + bar_w + 12, bar_y + 2), f"{xpPercent}%", font=font_stats, fill=TITLE_COLOR)

    x = bar_x + bar_w + 70

    # --- メンバー数/Wars/Territory（アイコン＋数値 横並び）---
    row_stats_y = y + bar_h + 10
    mx = stats_x
    stat_gap = 100
    # メンバー
    if member_icon:
        img.paste(member_icon, (mx, row_stats_y), mask=member_icon)
    draw.text((mx + icon_size + 4, row_stats_y + 6), f"{online_players.__len__()}/{total_members}", font=font_stats, fill=TITLE_COLOR)
    mx += stat_gap
    # Wars
    if war_icon:
        img.paste(war_icon, (mx, row_stats_y), mask=war_icon)
    draw.text((mx + icon_size + 4, row_stats_y + 6), f"{_fmt_num(wars)}", font=font_stats, fill=TITLE_COLOR)
    mx += stat_gap
    # Territory
    if territory_icon:
        img.paste(territory_icon, (mx, row_stats_y), mask=territory_icon)
    draw.text((mx + icon_size + 4, row_stats_y + 6), f"{_fmt_num(territories)}", font=font_stats, fill=TITLE_COLOR)

    # --- オーナー名 ---
    owner_y = row_stats_y + icon_size + 8
    if owner_icon:
        img.paste(owner_icon, (stats_x, owner_y), mask=owner_icon)
    draw.text((stats_x + icon_size + 4, owner_y + 6), f"{owner}", font=font_stats, fill=TITLE_COLOR)

    # --- 横線 ---
    line2_y = owner_y + 38
    draw.line([(margin, line2_y), (img_w - margin, line2_y)], fill=LINE_COLOR, width=2)

    # --- Created/Season --- 
    info_y = line2_y + 14
    draw.text((margin, info_y), f"Created on: {created}", font=font_small, fill=(20, 140, 80, 255))
    draw.text((img_w // 2, info_y), f"Latest SR: {rating_display} (Season {latest_season})", font=font_small, fill=(44, 180, 90, 255), anchor="ma")

    # --- 横線 ---
    line3_y = info_y + 28
    draw.line([(margin, line3_y), (img_w - margin, line3_y)], fill=LINE_COLOR, width=2)

    # --- メンバー表（役職ごとに2列表示, アイコン付き） ---
    role_icon_map = {
        "CHIEF": "chief",
        "STRATEGIST": "strategist",
        "CAPTAIN": "captain",
        "RECRUITER": "recruiter",
        "RECRUIT": "recruit"
    }
    role_display_map = {
        "CHIEF": "**CHIEFS**",
        "STRATEGIST": "**STRATEGISTS**",
        "CAPTAIN": "*CAPTAINS*",
        "RECRUITER": "RECRUITERS",
        "RECRUIT": "RECRUITS"
    }
    member_list_y = line3_y + 14
    roles_order = ["CHIEF", "STRATEGIST", "CAPTAIN", "RECRUITER", "RECRUIT"]

    col_gap = 260
    icon_mini = 22
    role_x1 = margin
    role_x2 = margin + col_gap

    for role in roles_order:
        # section header
        draw.text((role_x1, member_list_y), role_display_map[role], font=font_section, fill=TITLE_COLOR)
        member_list_y += 32

        group_members = members.get(role.lower(), {}) or {}
        names = list(group_members.keys())
        # 2列表示
        for i in range(0, len(names), 2):
            n1 = names[i]
            n2 = names[i + 1] if i + 1 < len(names) else None

            # 左列
            y1 = member_list_y
            icon1 = _load_icon(role_icon_map[role], icon_mini)
            if icon1:
                img.paste(icon1, (role_x1, y1), mask=icon1)
            draw.text((role_x1 + icon_mini + 4, y1 + 2), n1, font=font_rank, fill=TITLE_COLOR)
            server1 = group_members[n1].get("server", "")
            if server1:
                draw.text((role_x1 + icon_mini + 150, y1 + 2), server1, font=font_small, fill=SUBTITLE_COLOR)

            # 右列
            if n2:
                icon2 = _load_icon(role_icon_map[role], icon_mini)
                if icon2:
                    img.paste(icon2, (role_x2, y1), mask=icon2)
                draw.text((role_x2 + icon_mini + 4, y1 + 2), n2, font=font_rank, fill=TITLE_COLOR)
                server2 = group_members[n2].get("server", "")
                if server2:
                    draw.text((role_x2 + icon_mini + 150, y1 + 2), server2, font=font_small, fill=SUBTITLE_COLOR)
            member_list_y += icon_mini + 8

        member_list_y += 12

    # --- フッター ---
    footer_text = "Generated by Minister Chikuwa"
    try:
        fw = _text_width(draw, footer_text, font=font_small)
    except Exception:
        bbox = draw.textbbox((0, 0), footer_text, font=font_small)
        fw = bbox[2] - bbox[0]
    draw.text((img_w - fw - margin, img_h - margin), footer_text, font=font_small, fill=(120, 110, 100, 255))

    out_bytes = BytesIO()
    img.save(out_bytes, format="PNG")
    out_bytes.seek(0)

    try:
        if isinstance(banner_img, Image.Image):
            banner_img.close()
    except Exception:
        pass

    return out_bytes
