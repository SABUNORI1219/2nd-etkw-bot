from PIL import Image, ImageDraw, ImageFont, ImageFilter
from io import BytesIO
import os
import logging
import random
import math
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)

# フォント・アセットパス
FONT_PATH = os.path.join(os.path.dirname(__file__), "../assets/fonts/Minecraftia-Regular.ttf")
BANNER_PLACEHOLDER = None

# レイアウト定数
CANVAS_WIDTH = 700
MARGIN = 28
LEFT_COLUMN_WIDTH = 460
RIGHT_COLUMN_WIDTH = CANVAS_WIDTH - LEFT_COLUMN_WIDTH - MARGIN * 2
LINE_COLOR = (40, 40, 40, 255)

# 色定義
BASE_BG_COLOR = (218, 179, 99)
TITLE_COLOR = (40, 30, 20, 255)
SUBTITLE_COLOR = (80, 60, 40, 255)
TABLE_HEADER_BG = (230, 230, 230, 255)

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


def draw_decorative_frame(img: Image.Image,
                          outer_offset: Optional[int] = None,
                          outer_width: int = 8,
                          inner_offset: Optional[int] = None,
                          inner_width: int = 2,
                          frame_color=(85, 50, 30, 255)) -> Image.Image:
    """
    外枠（太）＋内枠（細）を描画します。
    アーチと直線は「見た目上独立」かつ「四隅はアーチで欠ける」ように描画します。
    調整パラメータ（arc_pad, inner_pad, line_inset_*, corner_trim）をいじって下さい。
    """
    w, h = img.size

    # アーチ半径
    notch_radius = max(12, int(min(w, h) * 0.035))
    arc_diameter = notch_radius * 2

    # 内アーチの半径（外アーチに近づけることで形を揃える）
    inner_notch_radius = max(8, int(notch_radius * 0.90))
    inner_arc_diameter = inner_notch_radius * 2

    # --- 調整可能なパラメータ ---
    arc_pad = max(8, int(notch_radius * 0.8))         # アーチ全体を外側に寄せる量（px）
    inner_pad = max(6, int(inner_notch_radius * 0.7)) # 内アーチの外寄せ（px）

    # 直線の内寄せ量（増やすほど直線は内側に寄る）
    line_inset_outer = -40   # 調整ポイント：外枠直線の内寄せ（px）
    line_inset_inner = -32    # 調整ポイント：内枠直線の内寄せ（px）

    # 角を切るためのトリム量（アーチの端点からさらに内側へ退く量）
    corner_trim = max(2, int(notch_radius * 0.25))  # 調整ポイント：大きいほど角の欠けが深くなる

    # --- offset の安全化 ---
    min_outer_offset = int(arc_diameter + arc_pad + (outer_width / 2) + 1)
    if outer_offset is None:
        outer_offset = max(12, min_outer_offset)
    else:
        outer_offset = int(max(0, outer_offset))

    if inner_offset is None:
        inner_offset = outer_offset + max(6, outer_width + inner_width + 4)
    else:
        inner_offset = int(max(inner_offset, (inner_width // 2) + 1))

    ox = int(outer_offset)
    oy = int(outer_offset)
    ow = int(w - outer_offset * 2)
    oh = int(h - outer_offset * 2)

    ix = int(inner_offset)
    iy = int(inner_offset)
    iw = int(w - inner_offset * 2)
    ih = int(h - inner_offset * 2)

    out = img.convert("RGBA")
    draw = ImageDraw.Draw(out)

    # clamp helper
    def _clamp_center(pt, stroke_w):
        half = stroke_w / 2.0
        x = max(half, min(w - half, pt[0]))
        y = max(half, min(h - half, pt[1]))
        return (x, y)

    # --- arc bboxes (計算は先に行う) ---
    left_arc_box = [ox - arc_diameter - arc_pad, oy - arc_diameter - arc_pad, ox - arc_pad, oy - arc_pad]
    right_arc_box = [ox + ow + arc_pad, oy - arc_diameter - arc_pad, ox + ow + arc_diameter + arc_pad, oy - arc_pad]
    bottom_left_arc_box = [ox - arc_diameter - arc_pad, oy + oh + arc_pad, ox - arc_pad, oy + oh + arc_diameter + arc_pad]
    bottom_right_arc_box = [ox + ow + arc_pad, oy + oh + arc_pad, ox + ow + arc_diameter + arc_pad, oy + oh + arc_diameter + arc_pad]

    # --- compute arc edge points used to trim lines so corners are arc-shaped ---
    p_left_top = _arc_point(left_arc_box, 90)
    p_right_top = _arc_point(right_arc_box, 90)
    p_left_left = _arc_point(left_arc_box, 180)
    p_left_bot = _arc_point(bottom_left_arc_box, 270)
    p_right_right = _arc_point(right_arc_box, 0)
    p_right_bot = _arc_point(bottom_right_arc_box, 270)

    # ----------------------------
    # 1) 外枠直線：直線は固定位置（line_inset_outer）だが四隅は arc の外周に被らないようトリムする
    # ----------------------------
    # horizontals
    top_y = oy + int(outer_width / 2) + line_inset_outer
    bot_y = oy + oh - int(outer_width / 2) - line_inset_outer

    # compute trimmed start/end X based on arc endpoints and corner_trim
    start_x = max(ox + line_inset_outer, p_left_top[0] + corner_trim)
    end_x = min(ox + ow - line_inset_outer, p_right_top[0] - corner_trim)
    if start_x < end_x:
        draw.line([_clamp_center((start_x, top_y), outer_width), _clamp_center((end_x, top_y), outer_width)],
                  fill=frame_color, width=outer_width)

    start_x_b = max(ox + line_inset_outer, p_left_bot[0] + corner_trim)
    end_x_b = min(ox + ow - line_inset_outer, p_right_bot[0] - corner_trim)
    if start_x_b < end_x_b:
        draw.line([_clamp_center((start_x_b, bot_y), outer_width), _clamp_center((end_x_b, bot_y), outer_width)],
                  fill=frame_color, width=outer_width)

    # verticals: compute trimmed start/end Y using arc points
    left_x = ox + int(outer_width / 2) + line_inset_outer
    right_x = ox + ow - int(outer_width / 2) - line_inset_outer

    start_y = max(oy + line_inset_outer, p_left_left[1] + corner_trim)
    end_y = min(oy + oh - line_inset_outer, p_left_bot[1] - corner_trim)
    if start_y < end_y:
        draw.line([_clamp_center((left_x, start_y), outer_width), _clamp_center((left_x, end_y), outer_width)],
                  fill=frame_color, width=outer_width)

    start_y_r = max(oy + line_inset_outer, p_right_right[1] + corner_trim)
    end_y_r = min(oy + oh - line_inset_outer, p_right_bot[1] - corner_trim)
    if start_y_r < end_y_r:
        draw.line([_clamp_center((right_x, start_y_r), outer_width), _clamp_center((right_x, end_y_r), outer_width)],
                  fill=frame_color, width=outer_width)

    # ----------------------------
    # 2) 外アーチ（outer arcs）を描画（直線の上に描く）
    # ----------------------------
    try:
        draw.arc(left_arc_box, start=0, end=90, fill=frame_color, width=outer_width)
        draw.arc(right_arc_box, start=90, end=180, fill=frame_color, width=outer_width)
        draw.arc(bottom_right_arc_box, start=180, end=270, fill=frame_color, width=outer_width)
        draw.arc(bottom_left_arc_box, start=270, end=360, fill=frame_color, width=outer_width)
    except Exception:
        draw.arc(left_arc_box, start=0, end=90, fill=frame_color)
        draw.arc(right_arc_box, start=90, end=180, fill=frame_color)
        draw.arc(bottom_right_arc_box, start=180, end=270, fill=frame_color)
        draw.arc(bottom_left_arc_box, start=270, end=360, fill=frame_color)

    # ----------------------------
    # 3) 内枠直線：同様に四隅を内アーチで欠けさせる
    # ----------------------------
    # compute inner arc bboxes (already available via inner_pad usage below)
    li_box = [ix - inner_arc_diameter - inner_pad, iy - inner_arc_diameter - inner_pad, ix - inner_pad, iy - inner_pad]
    ri_box = [ix + iw + inner_pad, iy - inner_arc_diameter - inner_pad, ix + iw + inner_arc_diameter + inner_pad, iy - inner_pad]
    br_box = [ix + iw + inner_pad, iy + ih + inner_pad, ix + iw + inner_arc_diameter + inner_pad, iy + ih + inner_arc_diameter + inner_pad]
    bl_box = [ix - inner_arc_diameter - inner_pad, iy + ih + inner_pad, ix - inner_pad, iy + ih + inner_arc_diameter + inner_pad]

    # inner arc points
    p_ili_top = _arc_point(li_box, 90)
    p_iri_top = _arc_point(ri_box, 90)
    p_ili_left = _arc_point(li_box, 180)
    p_ili_bot = _arc_point(bl_box, 270)
    p_iri_right = _arc_point(ri_box, 0)
    p_iri_bot = _arc_point(br_box, 270)

    inner_top_y = iy + int(inner_width / 2) + line_inset_inner
    inner_bot_y = iy + ih - int(inner_width / 2) - line_inset_inner

    sxi = max(ix + line_inset_inner, p_ili_top[0] + corner_trim)
    exi = min(ix + iw - line_inset_inner, p_iri_top[0] - corner_trim)
    if sxi < exi:
        draw.line([_clamp_center((sxi, inner_top_y), inner_width), _clamp_center((exi, inner_top_y), inner_width)],
                  fill=(95, 60, 35, 220), width=inner_width)

    sxb = max(ix + line_inset_inner, p_ili_bot[0] + corner_trim)
    exb = min(ix + iw - line_inset_inner, p_iri_bot[0] - corner_trim)
    if sxb < exb:
        draw.line([_clamp_center((sxb, inner_bot_y), inner_width), _clamp_center((exb, inner_bot_y), inner_width)],
                  fill=(95, 60, 35, 220), width=inner_width)

    left_ix = ix + int(inner_width / 2) + line_inset_inner
    right_ix = ix + iw - int(inner_width / 2) - line_inset_inner
    syi = max(iy + line_inset_inner, p_ili_left[1] + corner_trim)
    eyi = min(iy + ih - line_inset_inner, p_ili_bot[1] - corner_trim)
    if syi < eyi:
        draw.line([_clamp_center((left_ix, syi), inner_width), _clamp_center((left_ix, eyi), inner_width)],
                  fill=(95, 60, 35, 220), width=inner_width)
    syi_r = max(iy + line_inset_inner, p_iri_right[1] + corner_trim)
    eyi_r = min(iy + ih - line_inset_inner, p_iri_bot[1] - corner_trim)
    if syi_r < eyi_r:
        draw.line([_clamp_center((right_ix, syi_r), inner_width), _clamp_center((right_ix, eyi_r), inner_width)],
                  fill=(95, 60, 35, 220), width=inner_width)

    # ----------------------------
    # 4) 内アーチを描画（直線の上に描く）
    # ----------------------------
    try:
        draw.arc(li_box, start=0, end=90, fill=(95, 60, 35, 220), width=inner_width)
        draw.arc(ri_box, start=90, end=180, fill=(95, 60, 35, 220), width=inner_width)
        draw.arc(br_box, start=180, end=270, fill=(95, 60, 35, 220), width=inner_width)
        draw.arc(bl_box, start=270, end=360, fill=(95, 60, 35, 220), width=inner_width)
    except Exception:
        draw.arc(li_box, start=0, end=90, fill=(95, 60, 35, 220))
        draw.arc(ri_box, start=90, end=180, fill=(95, 60, 35, 220))
        draw.arc(br_box, start=180, end=270, fill=(95, 60, 35, 220))
        draw.arc(bl_box, start=270, end=360, fill=(95, 60, 35, 220))

    # 装飾的なルール線・ボックス
    rule_color = (110, 75, 45, 180)
    try:
        y_rule = iy + int(ih * 0.12)
        draw.line([(ix + int(iw * 0.03), y_rule), (ix + iw - int(iw * 0.03), y_rule)], fill=rule_color, width=max(2, inner_width + 2))
        y_rule2 = iy + int(ih * 0.48)
        draw.line([(ix + int(iw * 0.03), y_rule2), (ix + int(iw * 0.60), y_rule2)], fill=rule_color, width=max(2, inner_width + 2))
        box_x = ix + int(iw * 0.04)
        box_y = iy + int(ih * 0.06)
        box_w = int(iw * 0.18)
        box_h = int(ih * 0.18)
        draw.rectangle([box_x, box_y, box_x + box_w, box_y + box_h], outline=rule_color, width=max(2, inner_width))
    except Exception:
        logger.debug("rule/box draw failed, skipping")

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

    # 装飾枠を描画（outer_offset/inner_offset を明示指定）
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
