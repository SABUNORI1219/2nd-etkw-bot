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
    """
    四辺の太線/細線直線長さと、四隅のアーチ位置を完全個別調整できるバージョン。
    余計な上限/下限なし。
    """
    w, h = img.size

    notch_radius = 12 if min(w, h) * 0.035 < 12 else int(min(w, h) * 0.035)
    arc_diameter = notch_radius * 2
    inner_notch_radius = 8 if notch_radius * 0.9 < 8 else int(notch_radius * 0.90)
    inner_arc_diameter = inner_notch_radius * 2

    arc_pad = int(notch_radius * 0.35)
    inner_pad = int(inner_notch_radius * 0.30)

    # 直線inset 個別値
    lo_top = line_inset_outer_top if line_inset_outer_top is not None else -40
    lo_bottom = line_inset_outer_bottom if line_inset_outer_bottom is not None else -40
    lo_left = line_inset_outer_left if line_inset_outer_left is not None else -40
    lo_right = line_inset_outer_right if line_inset_outer_right is not None else -40
    li_top = line_inset_inner_top if line_inset_inner_top is not None else -32
    li_bottom = line_inset_inner_bottom if line_inset_inner_bottom is not None else -32
    li_left = line_inset_inner_left if line_inset_inner_left is not None else -32
    li_right = line_inset_inner_right if line_inset_inner_right is not None else -32

    # corner_trim 個別値
    ct_top = corner_trim_top if corner_trim_top is not None else (corner_trim if corner_trim is not None else int(notch_radius * 0.25) - math.ceil(outer_width / 2))
    ct_bottom = corner_trim_bottom if corner_trim_bottom is not None else (corner_trim if corner_trim is not None else int(notch_radius * 0.25) - math.ceil(outer_width / 2))
    ct_left = corner_trim_left if corner_trim_left is not None else (corner_trim if corner_trim is not None else int(notch_radius * 0.25) - math.ceil(outer_width / 2))
    ct_right = corner_trim_right if corner_trim_right is not None else (corner_trim if corner_trim is not None else int(notch_radius * 0.25) - math.ceil(outer_width / 2))

    # offset
    if outer_offset is None:
        outer_offset = 12
    else:
        outer_offset = int(outer_offset)
    if inner_offset is None:
        inner_offset = outer_offset + outer_width + inner_width + 4
    else:
        inner_offset = int(inner_offset)

    ox = int(outer_offset)
    oy = int(outer_offset)
    ow = int(w - outer_offset * 2)
    oh = int(h - outer_offset * 2)

    ix = int(inner_offset)
    iy = int(inner_offset)
    iw = int(w - inner_offset * 2)
    ih = int(h - inner_offset * 2)

    out = img.convert("RGBA")

    def _clamp_center(pt, stroke_w):
        return pt  # clampなし

    def _inflate_bbox(bbox, pad):
        x0, y0, x1, y1 = bbox
        return [x0 - pad, y0 - pad, x1 + pad, y1 + pad]

    def _expand_and_clamp_bbox(bbox, pad):
        x0, y0, x1, y1 = bbox
        return [x0 - pad, y0 - pad, x1 + pad, y1 + pad]

    # 各辺anchor 個別指定
    top_y = oy + outer_width / 2 + lo_top
    bot_y = oy + oh - outer_width / 2 - lo_bottom
    left_x = ox + outer_width / 2 + lo_left
    right_x = ox + ow - outer_width / 2 - lo_right

    inner_top_y = iy + inner_width / 2 + li_top
    inner_bot_y = iy + ih - inner_width / 2 - li_bottom
    left_ix = ix + inner_width / 2 + li_left
    right_ix = ix + iw - inner_width / 2 - li_right

    # アーチbbox 個別指定
    r = arc_diameter / 2.0
    left_arc_box = [left_x - r + arc_nudge_outer_topleft_x, top_y + arc_nudge_outer_topleft_y, left_x + r + arc_nudge_outer_topleft_x, top_y + 2 * r + arc_nudge_outer_topleft_y]
    right_arc_box = [right_x - r + arc_nudge_outer_topright_x, top_y + arc_nudge_outer_topright_y, right_x + r + arc_nudge_outer_topright_x, top_y + 2 * r + arc_nudge_outer_topright_y]
    bottom_left_arc_box = [left_x - r + arc_nudge_outer_bottomleft_x, bot_y - 2 * r + arc_nudge_outer_bottomleft_y, left_x + r + arc_nudge_outer_bottomleft_x, bot_y + arc_nudge_outer_bottomleft_y]
    bottom_right_arc_box = [right_x - r + arc_nudge_outer_bottomright_x, bot_y - 2 * r + arc_nudge_outer_bottomright_y, right_x + r + arc_nudge_outer_bottomright_x, bot_y + arc_nudge_outer_bottomright_y]

    r_i = inner_arc_diameter / 2.0
    li_box = [left_ix - r_i + arc_nudge_inner_topleft_x, inner_top_y + arc_nudge_inner_topleft_y, left_ix + r_i + arc_nudge_inner_topleft_x, inner_top_y + 2 * r_i + arc_nudge_inner_topleft_y]
    ri_box = [right_ix - r_i + arc_nudge_inner_topright_x, inner_top_y + arc_nudge_inner_topright_y, right_ix + r_i + arc_nudge_inner_topright_x, inner_top_y + 2 * r_i + arc_nudge_inner_topright_y]
    bl_box = [left_ix - r_i + arc_nudge_inner_bottomleft_x, inner_bot_y - 2 * r_i + arc_nudge_inner_bottomleft_y, left_ix + r_i + arc_nudge_inner_bottomleft_x, inner_bot_y + arc_nudge_inner_bottomleft_y]
    br_box = [right_ix - r_i + arc_nudge_inner_bottomright_x, inner_bot_y - 2 * r_i + arc_nudge_inner_bottomright_y, right_ix + r_i + arc_nudge_inner_bottomright_x, inner_bot_y + arc_nudge_inner_bottomright_y]

    p_left_top = _arc_point(left_arc_box, 90)
    p_right_top = _arc_point(right_arc_box, 90)
    p_left_left = _arc_point(left_arc_box, 180)
    p_left_bot = _arc_point(bottom_left_arc_box, 270)
    p_right_right = _arc_point(right_arc_box, 0)
    p_right_bot = _arc_point(bottom_right_arc_box, 270)

    p_ili_top = _arc_point(li_box, 90)
    p_iri_top = _arc_point(ri_box, 90)
    p_ili_left = _arc_point(li_box, 180)
    p_ili_bot = _arc_point(bl_box, 270)
    p_iri_right = _arc_point(ri_box, 0)
    p_iri_bot = _arc_point(br_box, 270)

    frame_layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw_frame = ImageDraw.Draw(frame_layer)

    # 横線（top）太線
    start_x = max(ox + lo_left, p_left_top[0] + ct_top)
    end_x = min(ox + ow - lo_right, p_right_top[0] - ct_top)
    if start_x < end_x:
        draw_frame.line([_clamp_center((start_x, top_y), outer_width), _clamp_center((end_x, top_y), outer_width)], fill=frame_color, width=outer_width)

    # 横線（bottom）太線
    start_x_b = max(ox + lo_left, p_left_bot[0] + ct_bottom)
    end_x_b = min(ox + ow - lo_right, p_right_bot[0] - ct_bottom)
    if start_x_b < end_x_b:
        draw_frame.line([_clamp_center((start_x_b, bot_y), outer_width), _clamp_center((end_x_b, bot_y), outer_width)], fill=frame_color, width=outer_width)

    # 縦線（left）太線
    start_y = max(oy + lo_top, p_left_left[1] + ct_left)
    end_y = min(oy + oh - lo_bottom, p_left_bot[1] - ct_left)
    if start_y < end_y:
        draw_frame.line([_clamp_center((left_x, start_y), outer_width), _clamp_center((left_x, end_y), outer_width)], fill=frame_color, width=outer_width)

    # 縦線（right）太線
    start_y_r = max(oy + lo_top, p_right_right[1] + ct_right)
    end_y_r = min(oy + oh - lo_bottom, p_right_bot[1] - ct_right)
    if start_y_r < end_y_r:
        draw_frame.line([_clamp_center((right_x, start_y_r), outer_width), _clamp_center((right_x, end_y_r), outer_width)], fill=frame_color, width=outer_width)

    mask = Image.new("L", (w, h), 255)
    draw_mask = ImageDraw.Draw(mask)
    outer_half = outer_width / 2
    inflate_outer = outer_half + 1
    draw_mask.ellipse(_inflate_bbox(left_arc_box, inflate_outer), fill=0)
    draw_mask.ellipse(_inflate_bbox(right_arc_box, inflate_outer), fill=0)
    draw_mask.ellipse(_inflate_bbox(bottom_left_arc_box, inflate_outer), fill=0)
    draw_mask.ellipse(_inflate_bbox(bottom_right_arc_box, inflate_outer), fill=0)
    frame_layer = Image.composite(frame_layer, Image.new("RGBA", (w, h), (0, 0, 0, 0)), mask)

    out = Image.alpha_composite(out, frame_layer)

    draw_out = ImageDraw.Draw(out)
    stroke_pad = outer_width / 2 + 1
    left_bbox = _expand_and_clamp_bbox(left_arc_box, stroke_pad)
    right_bbox = _expand_and_clamp_bbox(right_arc_box, stroke_pad)
    bl_bbox = _expand_and_clamp_bbox(bottom_left_arc_box, stroke_pad)
    br_bbox = _expand_and_clamp_bbox(bottom_right_arc_box, stroke_pad)

    try:
        draw_out.arc(left_bbox, start=0, end=90, fill=frame_color, width=outer_width)
        draw_out.arc(right_bbox, start=90, end=180, fill=frame_color, width=outer_width)
        draw_out.arc(br_bbox, start=180, end=270, fill=frame_color, width=outer_width)
        draw_out.arc(bl_bbox, start=270, end=360, fill=frame_color, width=outer_width)
    except Exception:
        pass

    # 細線（inner）も同様に個別パラメータで描画
    inner_layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw_inner_layer = ImageDraw.Draw(inner_layer)

    # 横線（top）細線
    sxi = max(ix + li_left, p_ili_top[0] + ct_top)
    exi = min(ix + iw - li_right, p_iri_top[0] - ct_top)
    if sxi < exi:
        draw_inner_layer.line([_clamp_center((sxi, inner_top_y), inner_width), _clamp_center((exi, inner_top_y), inner_width)], fill=(95, 60, 35, 220), width=inner_width)

    # 横線（bottom）細線
    sxb = max(ix + li_left, p_ili_bot[0] + ct_bottom)
    exb = min(ix + iw - li_right, p_iri_bot[0] - ct_bottom)
    if sxb < exb:
        draw_inner_layer.line([_clamp_center((sxb, inner_bot_y), inner_width), _clamp_center((exb, inner_bot_y), inner_width)], fill=(95, 60, 35, 220), width=inner_width)

    # 縦線（left）細線
    syi = max(iy + li_top, p_ili_left[1] + ct_left)
    eyi = min(iy + ih - li_bottom, p_ili_bot[1] - ct_left)
    if syi < eyi:
        draw_inner_layer.line([_clamp_center((left_ix, syi), inner_width), _clamp_center((left_ix, eyi), inner_width)], fill=(95, 60, 35, 220), width=inner_width)

    # 縦線（right）細線
    syi_r = max(iy + li_top, p_iri_right[1] + ct_right)
    eyi_r = min(iy + ih - li_bottom, p_iri_bot[1] - ct_right)
    if syi_r < eyi_r:
        draw_inner_layer.line([_clamp_center((right_ix, syi_r), inner_width), _clamp_center((right_ix, eyi_r), inner_width)], fill=(95, 60, 35, 220), width=inner_width)

    mask_inner = Image.new("L", (w, h), 255)
    dm = ImageDraw.Draw(mask_inner)
    inner_half = inner_width / 2
    inflate_inner = inner_half + 1
    dm.ellipse(_inflate_bbox(li_box, inflate_inner), fill=0)
    dm.ellipse(_inflate_bbox(ri_box, inflate_inner), fill=0)
    dm.ellipse(_inflate_bbox(bl_box, inflate_inner), fill=0)
    dm.ellipse(_inflate_bbox(br_box, inflate_inner), fill=0)
    inner_layer = Image.composite(inner_layer, Image.new("RGBA", (w, h), (0, 0, 0, 0)), mask_inner)

    out = Image.alpha_composite(out, inner_layer)

    draw_out = ImageDraw.Draw(out)
    stroke_pad_i = inner_width / 2 + 1
    li_bbox = _expand_and_clamp_bbox(li_box, stroke_pad_i)
    ri_bbox = _expand_and_clamp_bbox(ri_box, stroke_pad_i)
    bli_bbox = _expand_and_clamp_bbox(bl_box, stroke_pad_i)
    bri_bbox = _expand_and_clamp_bbox(br_box, stroke_pad_i)

    try:
        draw_out.arc(li_bbox, start=0, end=90, fill=(95, 60, 35, 220), width=inner_width)
        draw_out.arc(ri_bbox, start=90, end=180, fill=(95, 60, 35, 220), width=inner_width)
        draw_out.arc(bri_bbox, start=180, end=270, fill=(95, 60, 35, 220), width=inner_width)
        draw_out.arc(bli_bbox, start=270, end=360, fill=(95, 60, 35, 220), width=inner_width)
    except Exception:
        pass

    return out

def create_card_background(w: int, h: int,
                           noise_std: float = 30.0,
                           noise_blend: float = 0.30,
                           vignette_blur: int = 80) -> Image.Image:
    base = Image.new('RGB', (w, h), BASE_BG_COLOR)

    if _HAS_NUMPY:
        try:
            noise = np.random.normal(128, noise_std, (h, w))
            noise = np.clip(noise, 0, 255).astype(np.uint8)
            noise_img = Image.fromarray(noise, mode='L').convert('RGB')
        except Exception:
            noise_img = Image.effect_noise((w, h), int(noise_std)).convert('L').convert('RGB')
    else:
        try:
            noise_img = Image.effect_noise((w, h), int(noise_std)).convert('L').convert('RGB')
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
        composed = composed.convert('RGBA')

    return composed

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
                        "rank_stars": rank_to_stars.get(rank_name.upper(), ""),
                        "rank": rank_name.upper()
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
    banner_x = img_w - margin - 170   # 右上
    banner_y = margin + 30
    banner_w = 140
    banner_h = 140

    # ギルド名・横線位置
    name_x = margin
    name_y = margin + 10
    line_x1 = margin
    line_x2 = banner_x - 18
    line_y = name_y + 48 + 8  # ギルド名の下

    # ステータス
    stat_y = line_y + 16
    icon_size = 32
    icon_gap = 8
    left_icon_x = margin

    # Created/Season
    info_y = stat_y + icon_size + 32 + 16

    # 2本目横線
    line_y2 = info_y + 28

    # 3本目横線
    line_y3 = line_y2 + 30

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
    created_icon = _load_icon(ICON_PATHS["created"], 24)
    season_icon = _load_icon(ICON_PATHS["season"], 24)

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
    stat_icon_x = margin
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
    stats_y2 = stat_icon_y + icon_size + 12
    stats_x = margin
    stats_gap = 80

    # メンバー数
    if member_icon:
        img.paste(member_icon, (stats_x, stats_y2), mask=member_icon)
    draw.text((stats_x + icon_size + 8, stats_y2 + 8), f"{len(online_players)}/{total_members}", font=font_stats, fill=TITLE_COLOR)

    # War数
    stats_x2 = stats_x + stats_gap
    if war_icon:
        img.paste(war_icon, (stats_x2, stats_y2), mask=war_icon)
    draw.text((stats_x2 + icon_size + 8, stats_y2 + 8), f"{_fmt_num(wars)}", font=font_stats, fill=TITLE_COLOR)

    # 領地数
    stats_x3 = stats_x2 + stats_gap
    if territory_icon:
        img.paste(territory_icon, (stats_x3, stats_y2), mask=territory_icon)
    draw.text((stats_x3 + icon_size + 8, stats_y2 + 8), f"{_fmt_num(territories)}", font=font_stats, fill=TITLE_COLOR)

    # オーナー
    stats_x4 = stats_x3 + stats_gap
    if owner_icon:
        img.paste(owner_icon, (stats_x4, stats_y2), mask=owner_icon)
    draw.text((stats_x4 + icon_size + 8, stats_y2 + 8), owner, font=font_stats, fill=TITLE_COLOR)

    # 2本目横線
    draw.line([(line_x1, line_y2), (line_x2, line_y2)], fill=LINE_COLOR, width=2)

    # Created/Season（アイコン＋テキスト）
    created_x = margin
    season_x = img_w - margin - 240
    if created_icon:
        img.paste(created_icon, (created_x, info_y), mask=created_icon)
        draw.text((created_x + 28, info_y), f"Created on: {created}", font=font_small, fill=(20, 140, 80, 255))
    else:
        draw.text((created_x, info_y), f"Created on: {created}", font=font_small, fill=(20, 140, 80, 255))
    if season_icon:
        img.paste(season_icon, (season_x, info_y), mask=season_icon)
        draw.text((season_x + 28, info_y), f"Latest SR: {rating_display} (Season {latest_season})", font=font_small, fill=(44, 180, 90, 255))
    else:
        draw.text((season_x, info_y), f"Latest SR: {rating_display} (Season {latest_season})", font=font_small, fill=(44, 180, 90, 255))

    # 3本目横線
    draw.line([(line_x1, line_y3), (line_x2, line_y3)], fill=LINE_COLOR, width=2)

    # オンラインメンバー（役職ごと・2列表示）
    role_header_y = line_y3 + 18
    col_gap = 240
    role_x1 = margin
    role_x2 = margin + col_gap
    row_h = 30
    member_y = role_header_y

    role_display_map = {
        "CHIEF": "**CHIEFS**",
        "STRATEGIST": "**STRATEGISTS**",
        "CAPTAIN": "*CAPTAINS*",
        "RECRUITER": "RECRUITERS",
        "RECRUIT": "RECRUITS"
    }
    for role in role_order:
        draw.text((role_x1, member_y), role_display_map[role], font=font_section, fill=TITLE_COLOR)
        member_y += 32

        group_members = online_by_role[role]
        for i in range(0, len(group_members), 2):
            p1 = group_members[i]
            p2 = group_members[i + 1] if i + 1 < len(group_members) else None

            # 左列
            name1 = p1.get("name", "Unknown")
            server1 = p1.get("server", "")
            draw.text((role_x1, member_y), name1, font=font_rank, fill=TITLE_COLOR)
            if server1:
                draw.text((role_x1 + 140, member_y), server1, font=font_small, fill=SUBTITLE_COLOR)

            # 右列
            if p2:
                name2 = p2.get("name", "Unknown")
                server2 = p2.get("server", "")
                draw.text((role_x2, member_y), name2, font=font_rank, fill=TITLE_COLOR)
                if server2:
                    draw.text((role_x2 + 140, member_y), server2, font=font_small, fill=SUBTITLE_COLOR)
            member_y += row_h
        member_y += 8

    # フッター
    footer_text = "Generated by Minister Chikuwa"
    try:
        fw = _text_width(draw, footer_text, font=font_small)
    except Exception:
        bbox = draw.textbbox((0, 0), footer_text, font=font_small)
        fw = bbox[2] - bbox[0]
    draw.text((img_w - fw - margin, img_h - margin - 4), footer_text, font=font_small, fill=(120, 110, 100, 255))

    out_bytes = BytesIO()
    img.save(out_bytes, format="PNG")
    out_bytes.seek(0)

    try:
        if isinstance(banner_img, Image.Image):
            banner_img.close()
    except Exception:
        pass

    return out_bytes
