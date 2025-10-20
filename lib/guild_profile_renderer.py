from PIL import Image, ImageDraw, ImageFont, ImageFilter
from io import BytesIO
import os
import logging
import random
import math
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)

# フォント・アセットパス（profile_renderer と合わせておく）
FONT_PATH = os.path.join(os.path.dirname(__file__), "../assets/fonts/Minecraftia-Regular.ttf")
BANNER_PLACEHOLDER = None  # もしアセットのバナー用画像があれば設定

# レイアウト定数 — 縦長に変更（横長から縦長へ）
CANVAS_WIDTH = 700   # 縦長の幅に固定（高さはオンライン人数に応じて伸縮）
MARGIN = 28
LEFT_COLUMN_WIDTH = 460
RIGHT_COLUMN_WIDTH = CANVAS_WIDTH - LEFT_COLUMN_WIDTH - MARGIN * 2
LINE_COLOR = (40, 40, 40, 255)

# 色定義
BASE_BG_COLOR = (218, 179, 99)
TITLE_COLOR = (40, 30, 20, 255)
SUBTITLE_COLOR = (80, 60, 40, 255)
TABLE_HEADER_BG = (230, 230, 230, 255)
ONLINE_BADGE = (60, 200, 60, 255)
OFFLINE_BADGE = (200, 60, 60, 255)

# NumPy availability (optional for noise)
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
    """
    draw オブジェクトと font を使ってテキスト幅を安全に取得するユーティリティ。
    """
    try:
        return int(draw_obj.textlength(text, font=font))
    except Exception:
        bbox = draw_obj.textbbox((0, 0), text, font=font)
        return bbox[2] - bbox[0]


def _arc_point(bbox, angle_deg):
    """
    bbox = [x0,y0,x1,y1] の楕円上の angle_deg (度) に対応する座標を返す。
    """
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
    """
    p -> q の方向に沿って q 側に amount ピクセルだけ伸ばした点を返す。
    """
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


def draw_decorative_frame(img: Image.Image,
                          outer_offset: Optional[int] = None,
                          outer_width: int = 8,
                          inner_offset: Optional[int] = None,
                          inner_width: int = 2,
                          frame_color=(85, 50, 30, 255)) -> Image.Image:
    """
    外枠（太）＋内枠（細）を描画する（スーパーサンプリング方式）。
    - アークは角の外側に bounding box を置き、適切な角度で描画（内向きの凹みにする）。
    - 高解像度で描画してから縮小することでアンチエイリアスの隙間を防ぐ。
    """
    w, h = img.size

    # 自動オフセット
    if outer_offset is None:
        outer_offset = max(12, int(min(w, h) * 0.025))
    if inner_offset is None:
        inner_offset = outer_offset + max(8, int(min(w, h) * 0.02))

    ox = outer_offset
    oy = outer_offset
    ow = w - outer_offset * 2
    oh = h - outer_offset * 2

    ix = inner_offset
    iy = inner_offset
    iw = w - inner_offset * 2
    ih = h - inner_offset * 2

    # 凹みサイズ（調整可能）
    notch_radius = max(12, int(min(w, h) * 0.035))
    inner_notch = max(6, int(min(w, h) * 0.02))

    # スーパーサンプリング倍率（描画品質向上）
    SCALE = 4
    sw = w * SCALE
    sh = h * SCALE

    # スケールされたパラメータ
    sox = ox * SCALE
    soy = oy * SCALE
    sow = ow * SCALE
    soh = oh * SCALE
    six = ix * SCALE
    siy = iy * SCALE
    siw = iw * SCALE
    sih = ih * SCALE
    snotch = notch_radius * SCALE
    sinner_notch = inner_notch * SCALE
    s_outer_w = max(1, int(outer_width * SCALE))
    s_inner_w = max(1, int(inner_width * SCALE))

    # 作業レイヤ（透明）に描く
    tmp = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
    td = ImageDraw.Draw(tmp)

    # アークの bbox を「角の外側」に置くことで、arc を内向き（凹）に見せる
    # top-left: bbox bottom-right == corner (ox,oy) scaled
    lt_box = [int(sox - 2 * snotch), int(soy - 2 * snotch), int(sox), int(soy)]
    rt_box = [int(sox + sow), int(soy - 2 * snotch), int(sox + sow + 2 * snotch), int(soy)]
    bl_box = [int(sox - 2 * snotch), int(soy + soh), int(sox), int(soy + soh + 2 * snotch)]
    br_box = [int(sox + sow), int(soy + soh), int(sox + sow + 2 * snotch), int(soy + soh + 2 * snotch)]

    # 外枠：アーク（内向きに見える角）を描画（角度は bbox に合わせて指定）
    try:
        td.arc(lt_box, start=0, end=90, fill=frame_color, width=s_outer_w)      # top-left concave
        td.arc(rt_box, start=90, end=180, fill=frame_color, width=s_outer_w)    # top-right
        td.arc(br_box, start=180, end=270, fill=frame_color, width=s_outer_w)   # bottom-right
        td.arc(bl_box, start=270, end=360, fill=frame_color, width=s_outer_w)   # bottom-left
    except Exception:
        # Pillow 環境によっては width 無視される場合があるが、縮小で許容する
        td.arc(lt_box, start=0, end=90, fill=frame_color)
        td.arc(rt_box, start=90, end=180, fill=frame_color)
        td.arc(br_box, start=180, end=270, fill=frame_color)
        td.arc(bl_box, start=270, end=360, fill=frame_color)

    # アークの端点を計算して、直線で繋ぐ（少しオーバーラップして確実に繋ぐ）
    # top edge
    p_lt_top = _arc_point([coord / SCALE for coord in lt_box], 90)
    p_rt_top = _arc_point([coord / SCALE for coord in rt_box], 90)
    # スケールしてから延長量を掛ける
    p1 = (p_lt_top[0] * SCALE, p_lt_top[1] * SCALE)
    p2 = (p_rt_top[0] * SCALE, p_rt_top[1] * SCALE)
    overlap_px = max(2, int(s_outer_w * 0.25))
    sstart = _extend_point(p1, p2, -overlap_px)
    send = _extend_point(p2, p1, -overlap_px)
    td.line([sstart, send], fill=frame_color, width=s_outer_w)

    # bottom edge
    p_lb_bot = _arc_point([coord / SCALE for coord in bl_box], 270)
    p_rb_bot = _arc_point([coord / SCALE for coord in br_box], 270)
    p1b = (p_lb_bot[0] * SCALE, p_lb_bot[1] * SCALE)
    p2b = (p_rb_bot[0] * SCALE, p_rb_bot[1] * SCALE)
    sstartb = _extend_point(p1b, p2b, -overlap_px)
    sendb = _extend_point(p2b, p1b, -overlap_px)
    td.line([sstartb, sendb], fill=frame_color, width=s_outer_w)

    # left vertical
    p_lt_l = _arc_point([coord / SCALE for coord in lt_box], 180)
    p_lb_l = _arc_point([coord / SCALE for coord in bl_box], 180)
    p1l = (p_lt_l[0] * SCALE, p_lt_l[1] * SCALE)
    p2l = (p_lb_l[0] * SCALE, p_lb_l[1] * SCALE)
    sstartl = _extend_point(p1l, p2l, -overlap_px)
    sendl = _extend_point(p2l, p1l, -overlap_px)
    td.line([sstartl, sendl], fill=frame_color, width=s_outer_w)

    # right vertical
    p_rt_r = _arc_point([coord / SCALE for coord in rt_box], 0)
    p_rb_r = _arc_point([coord / SCALE for coord in br_box], 0)
    p1r = (p_rt_r[0] * SCALE, p_rt_r[1] * SCALE)
    p2r = (p_rb_r[0] * SCALE, p_rb_r[1] * SCALE)
    sstartr = _extend_point(p1r, p2r, -overlap_px)
    sendr = _extend_point(p2r, p1r, -overlap_px)
    td.line([sstartr, sendr], fill=frame_color, width=s_outer_w)

    # 内枠（同様に高解像度で描画）
    # 内枠アーク用ボックス（内側に控えめに置く）
    inner_arc = int(notch_radius * 0.65)
    s_inner = inner_arc * SCALE
    li_box = [int(six - s_inner), int(siy - s_inner), int(six + s_inner), int(siy + s_inner)]
    ri_box = [int(six + siw - s_inner), int(siy - s_inner), int(six + siw + s_inner), int(siy + s_inner)]
    bli_box = [int(six - s_inner), int(siy + sih - s_inner), int(six + s_inner), int(siy + sih + s_inner)]
    bri_box = [int(six + siw - s_inner), int(siy + sih - s_inner), int(six + siw + s_inner), int(siy + sih + s_inner)]

    try:
        td.arc(li_box, start=0, end=90, fill=(95, 60, 35, 220), width=s_inner_w)
        td.arc(ri_box, start=90, end=180, fill=(95, 60, 35, 220), width=s_inner_w)
        td.arc(bri_box, start=180, end=270, fill=(95, 60, 35, 220), width=s_inner_w)
        td.arc(bli_box, start=270, end=360, fill=(95, 60, 35, 220), width=s_inner_w)
    except Exception:
        td.arc(li_box, start=0, end=90, fill=(95, 60, 35, 220))
        td.arc(ri_box, start=90, end=180, fill=(95, 60, 35, 220))
        td.arc(bri_box, start=180, end=270, fill=(95, 60, 35, 220))
        td.arc(bli_box, start=270, end=360, fill=(95, 60, 35, 220))

    # 内枠の直線接続（同じくオーバーラップ）
    # top
    pli_top = _arc_point([coord / SCALE for coord in li_box], 90)
    pri_top = _arc_point([coord / SCALE for coord in ri_box], 90)
    p1i = (pli_top[0] * SCALE, pli_top[1] * SCALE)
    p2i = (pri_top[0] * SCALE, pri_top[1] * SCALE)
    oi = max(2, int(s_inner_w * 0.25))
    td.line([_extend_point(p1i, p2i, -oi), _extend_point(p2i, p1i, -oi)], fill=(95, 60, 35, 220), width=s_inner_w)
    # bottom
    pli_bot = _arc_point([coord / SCALE for coord in bli_box], 270)
    pri_bot = _arc_point([coord / SCALE for coord in bri_box], 270)
    p1ib = (pli_bot[0] * SCALE, pli_bot[1] * SCALE)
    p2ib = (pri_bot[0] * SCALE, pri_bot[1] * SCALE)
    td.line([_extend_point(p1ib, p2ib, -oi), _extend_point(p2ib, p1ib, -oi)], fill=(95, 60, 35, 220), width=s_inner_w)
    # left vertical
    pli_l = _arc_point([coord / SCALE for coord in li_box], 180)
    pli_ll = _arc_point([coord / SCALE for coord in bli_box], 180)
    td.line([_extend_point((pli_l[0]*SCALE, pli_l[1]*SCALE), (pli_ll[0]*SCALE, pli_ll[1]*SCALE), -oi),
             _extend_point((pli_ll[0]*SCALE, pli_ll[1]*SCALE), (pli_l[0]*SCALE, pli_l[1]*SCALE), -oi)],
            fill=(95, 60, 35, 220), width=s_inner_w)
    # right vertical
    pri_r = _arc_point([coord / SCALE for coord in ri_box], 0)
    pri_rr = _arc_point([coord / SCALE for coord in bri_box], 0)
    td.line([_extend_point((pri_r[0]*SCALE, pri_r[1]*SCALE), (pri_rr[0]*SCALE, pri_rr[1]*SCALE), -oi),
             _extend_point((pri_rr[0]*SCALE, pri_rr[1]*SCALE), (pri_r[0]*SCALE, pri_r[1]*SCALE), -oi)],
            fill=(95, 60, 35, 220), width=s_inner_w)

    # 縮小して元画像に合成（高品質リサンプル）
    down = tmp.resize((w, h), resample=Image.LANCZOS)
    base = img.convert("RGBA")
    out = Image.alpha_composite(base, down)

    # ルール線等は上に描画
    draw = ImageDraw.Draw(out)
    rule_color = (110, 75, 45, 180)
    y_rule = iy + int(ih * 0.12)
    draw.line([(ix + int(iw * 0.03), y_rule), (ix + iw - int(iw * 0.03), y_rule)], fill=rule_color,
              width=max(2, inner_width + 2))
    y_rule2 = iy + int(ih * 0.48)
    draw.line([(ix + int(iw * 0.03), y_rule2), (ix + int(iw * 0.60), y_rule2)], fill=rule_color,
              width=max(2, inner_width + 2))
    box_x = ix + int(iw * 0.04)
    box_y = iy + int(ih * 0.06)
    box_w = int(iw * 0.18)
    box_h = int(ih * 0.18)
    draw.rectangle([box_x, box_y, box_x + box_w, box_y + box_h], outline=rule_color, width=max(2, inner_width))

    return out


def create_card_background(w: int, h: int,
                           noise_std: float = 30.0,
                           noise_blend: float = 0.30,
                           vignette_blur: int = 80) -> Image.Image:
    """
    紙風背景（ノイズ＋ブラー＋ビネット）に装飾枠を描画して返す。
    """
    base = Image.new('RGB', (w, h), BASE_BG_COLOR)

    # ==== ノイズ生成 ====
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

    # ==== ビネット（端の暗化）====
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

    # ==== 装飾枠を描画 ====
    try:
        composed = draw_decorative_frame(composed.convert('RGBA'),
                                         outer_offset=None,
                                         outer_width=max(6, int(w * 0.01)),
                                         inner_offset=None,
                                         inner_width=max(1, int(w * 0.005)),
                                         frame_color=(85, 50, 30, 255))
    except Exception as e:
        logger.exception(f"draw_decorative_frame failed: {e}")
        composed = composed.convert('RGBA')

    return composed


def create_guild_image(guild_data: Dict[str, Any], banner_renderer, max_width: int = CANVAS_WIDTH) -> BytesIO:
    """
    guild_data は辞書を想定。
    画像は縦長（幅は CANVAS_WIDTH に固定、高さはオンライン人数で伸縮）。
    戻り値: BytesIO (PNG)
    """
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

    base_height = 700
    row_height = 48
    online_count = len(online_players)
    extra_for_online = max(0, online_count) * row_height
    content_height = base_height + extra_for_online + 220
    canvas_w = max_width
    canvas_h = content_height

    img = create_card_background(canvas_w, canvas_h)
    draw = ImageDraw.Draw(img)

    card_x = MARGIN
    card_y = MARGIN
    card_w = canvas_w - MARGIN * 2
    card_h = canvas_h - MARGIN * 2

    try:
        font_title = ImageFont.truetype(FONT_PATH, 48)
        font_sub = ImageFont.truetype(FONT_PATH, 26)
        font_stats = ImageFont.truetype(FONT_PATH, 22)
        font_table_header = ImageFont.truetype(FONT_PATH, 20)
        font_table = ImageFont.truetype(FONT_PATH, 18)
        font_small = ImageFont.truetype(FONT_PATH, 16)
    except Exception as e:
        logger.error(f"FONT_PATH 読み込み失敗: {e}")
        font_title = font_sub = font_stats = font_table_header = font_table = font_small = ImageFont.load_default()

    inner_left = card_x + 36
    inner_top = card_y + 36

    draw.text((inner_left, inner_top), f"[{prefix}] {name}", font=font_title, fill=TITLE_COLOR)
    draw.text((inner_left, inner_top + 56), f"Owner: {owner}  |  Created: {created}", font=font_sub, fill=SUBTITLE_COLOR)

    banner_w = int(card_w * 0.18)
    banner_h = int(card_h * 0.20)
    banner_x = inner_left
    banner_y = inner_top + 110
    if banner_img:
        try:
            banner_resized = banner_img.resize((banner_w, banner_h), Image.LANCZOS)
            img.paste(banner_resized, (banner_x, banner_y), mask=banner_resized)
        except Exception as e:
            logger.warning(f"バナー貼付失敗: {e}")

    stats_x = banner_x + banner_w + 18
    stats_y = banner_y
    draw.text((stats_x, stats_y), f"Level: {level}   ({xpPercent}%)", font=font_stats, fill=SUBTITLE_COLOR)
    draw.text((stats_x, stats_y + 30), f"Wars: {_fmt_num(wars)}   Territories: {_fmt_num(territories)}", font=font_stats, fill=SUBTITLE_COLOR)
    draw.text((stats_x, stats_y + 60), f"Members: {_fmt_num(total_members)}   Online: {_fmt_num(online_count)}", font=font_stats, fill=SUBTITLE_COLOR)
    draw.text((stats_x, stats_y + 90), f"Latest SR: {rating_display} (Season {latest_season})", font=font_stats, fill=SUBTITLE_COLOR)

    sep_x = card_x + LEFT_COLUMN_WIDTH
    sep_y1 = inner_top + 24
    sep_y2 = card_y + card_h - 40
    draw.line([(sep_x, sep_y1), (sep_x, sep_y2)], fill=LINE_COLOR, width=2)

    table_x = sep_x + 18
    table_y = inner_top + 10
    draw.rectangle([table_x, table_y, table_x + RIGHT_COLUMN_WIDTH - 18, table_y + 40], fill=TABLE_HEADER_BG)
    draw.text((table_x + 8, table_y + 8), "Online Players", font=font_table_header, fill=TITLE_COLOR)
    header_bottom = table_y + 40
    col_server_w = 56
    col_name_w = RIGHT_COLUMN_WIDTH - 18 - col_server_w - 60
    col_rank_w = 60

    row_h = 44
    y = header_bottom + 12
    if online_players:
        for p in online_players:
            server = p.get("server", "N/A")
            pname = p.get("name", "Unknown")
            rank = p.get("rank_stars", "")

            draw.rectangle([table_x, y, table_x + col_server_w, y + row_h - 8], outline=LINE_COLOR, width=1)
            draw.text((table_x + 6, y + 10), server, font=font_table, fill=SUBTITLE_COLOR)

            nx = table_x + col_server_w + 8
            draw.rectangle([nx - 2, y, nx + col_name_w, y + row_h - 8], outline=LINE_COLOR, width=1)
            try:
                name_w = _text_width(draw, pname, font=font_table)
            except Exception:
                bbox = draw.textbbox((0, 0), pname, font=font_table)
                name_w = bbox[2] - bbox[0]
            display_name = pname
            max_name_w = col_name_w - 12
            if name_w > max_name_w:
                while display_name and (_text_width(draw, display_name + "...", font=font_table) > max_name_w):
                    display_name = display_name[:-1]
                display_name = display_name + "..."
            draw.text((nx + 6, y + 10), display_name, font=font_table, fill=TITLE_COLOR)

            rx = nx + col_name_w + 8
            draw.rectangle([rx - 2, y, rx + col_rank_w, y + row_h - 8], outline=LINE_COLOR, width=1)
            draw.text((rx + 6, y + 10), rank, font=font_table, fill=SUBTITLE_COLOR)

            y += row_h
    else:
        draw.text((table_x + 8, header_bottom + 18), "No members online right now.", font=font_table, fill=SUBTITLE_COLOR)

    footer_text = "Generated by Minister Chikuwa"
    try:
        fw = _text_width(draw, footer_text, font=font_small)
    except Exception:
        bbox = draw.textbbox((0, 0), footer_text, font=font_small)
        fw = bbox[2] - bbox[0]
    draw.text((card_x + card_w - fw - 16, card_y + card_h - 36), footer_text, font=font_small, fill=(120, 110, 100, 255))

    out = BytesIO()
    img.save(out, format="PNG")
    out.seek(0)

    try:
        if banner_img:
            banner_img.close()
    except Exception:
        pass

    return out
