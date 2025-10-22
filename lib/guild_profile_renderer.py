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
    変更はこの関数内に閉じ、他の処理には影響しない実装です。
    """
    w, h = img.size

    # アーチ半径
    notch_radius = max(12, int(min(w, h) * 0.035))
    arc_diameter = notch_radius * 2

    # 内アーチの半径（外アーチに近づけることで形を揃える）
    inner_notch_radius = max(8, int(notch_radius * 0.90))
    inner_arc_diameter = inner_notch_radius * 2

    # --- 調整可能なパラメータ ---
    arc_pad = max(8, int(notch_radius * 0.35))         # アーチ全体を外側に寄せる量（px）
    inner_pad = max(6, int(inner_notch_radius * 0.30)) # 内アーチの外寄せ（px）

    # 直線の内寄せ量（増やすほど直線は内側に寄る）
    # NOTE: we do NOT change these values here; keep them as-is to avoid moving lines.
    line_inset_outer = -40   # 調整ポイント：外枠直線の内寄せ（px）
    line_inset_inner = -32   # 調整ポイント：内枠直線の内寄せ（px）

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

    # compute straight-line anchors first (these exist later too; compute here to build arc bboxes)
    top_y = oy + int(outer_width / 2) + line_inset_outer
    bot_y = oy + oh - int(outer_width / 2) - line_inset_outer
    left_x = ox + int(outer_width / 2) + line_inset_outer
    right_x = ox + ow - int(outer_width / 2) - line_inset_outer
    
    # Use arc_diameter as width/height of each corner ellipse (rx = ry = arc_diameter/2)
    r = arc_diameter / 2.0
    
    # Left-top arc: we want its top point (angle 90°) to be at y = top_y and its center x to be left_x
    # bbox y0 = top_y  (because p_left_top.y == bbox.y0), bbox x center = left_x
    left_arc_box = [
        int(math.floor(left_x - r)),   # x0
        int(math.floor(top_y)),        # y0
        int(math.ceil(left_x + r)),    # x1
        int(math.ceil(top_y + 2 * r))  # y1
    ]
    
    # Right-top arc: center x = right_x, top aligned to top_y
    right_arc_box = [
        int(math.floor(right_x - r)),
        int(math.floor(top_y)),
        int(math.ceil(right_x + r)),
        int(math.ceil(top_y + 2 * r))
    ]
    
    # Left-bottom arc: bottom point (angle 270°) should be at y = bot_y => bbox y1 = bot_y
    bottom_left_arc_box = [
        int(math.floor(left_x - r)),
        int(math.floor(bot_y - 2 * r)),
        int(math.ceil(left_x + r)),
        int(math.ceil(bot_y))
    ]
    
    # Right-bottom arc: center x = right_x, bottom aligned to bot_y
    bottom_right_arc_box = [
        int(math.floor(right_x - r)),
        int(math.floor(bot_y - 2 * r)),
        int(math.ceil(right_x + r)),
        int(math.ceil(bot_y))
    ]

    # --- DEBUG: log arc bbox values (insert immediately after left_arc_box/right_arc_box/... definitions)
    logger.info(f"[FRAME DEBUG] w={w} h={h} ox={ox} oy={oy} ow={ow} oh={oh}")
    logger.info(f"[FRAME DEBUG] notch_radius={notch_radius} arc_diameter={arc_diameter} arc_pad={arc_pad}")
    logger.info(f"[FRAME DEBUG] left_arc_box={left_arc_box}")
    logger.info(f"[FRAME DEBUG] right_arc_box={right_arc_box}")
    logger.info(f"[FRAME DEBUG] bottom_left_arc_box={bottom_left_arc_box}")
    logger.info(f"[FRAME DEBUG] bottom_right_arc_box={bottom_right_arc_box}")

    # inner anchors (reuse inner_top_y/inner_bot_y, left_ix/right_ix which used later)
    inner_top_y = iy + int(inner_width / 2) + line_inset_inner
    inner_bot_y = iy + ih - int(inner_width / 2) - line_inset_inner
    left_ix = ix + int(inner_width / 2) + line_inset_inner
    right_ix = ix + iw - int(inner_width / 2) - line_inset_inner
    
    r_i = inner_arc_diameter / 2.0
    
    li_box = [int(math.floor(left_ix - r_i)), int(math.floor(inner_top_y)), int(math.ceil(left_ix + r_i)), int(math.ceil(inner_top_y + 2 * r_i))]
    ri_box = [int(math.floor(right_ix - r_i)), int(math.floor(inner_top_y)), int(math.ceil(right_ix + r_i)), int(math.ceil(inner_top_y + 2 * r_i))]
    bl_box = [int(math.floor(left_ix - r_i)), int(math.floor(inner_bot_y - 2 * r_i)), int(math.ceil(left_ix + r_i)), int(math.ceil(inner_bot_y))]
    br_box = [int(math.floor(right_ix - r_i)), int(math.floor(inner_bot_y - 2 * r_i)), int(math.ceil(right_ix + r_i)), int(math.ceil(inner_bot_y))]

    # --- DEBUG: log inner arc bbox / inner pad values ---
    logger.info(f"[FRAME DEBUG] inner_notch_radius={inner_notch_radius} inner_arc_diameter={inner_arc_diameter} inner_pad={inner_pad}")
    logger.info(f"[FRAME DEBUG] li_box={li_box}")
    logger.info(f"[FRAME DEBUG] ri_box={ri_box}")
    logger.info(f"[FRAME DEBUG] bl_box={bl_box}")
    logger.info(f"[FRAME DEBUG] br_box={br_box}")

    # --- compute arc edge points used to trim lines so corners are arc-shaped ---
    p_left_top = _arc_point(left_arc_box, 90)
    p_right_top = _arc_point(right_arc_box, 90)
    p_left_left = _arc_point(left_arc_box, 180)
    p_left_bot = _arc_point(bottom_left_arc_box, 270)
    p_right_right = _arc_point(right_arc_box, 0)
    p_right_bot = _arc_point(bottom_right_arc_box, 270)

    # inner arc points for inner masking/drawing
    p_ili_top = _arc_point(li_box, 90)
    p_iri_top = _arc_point(ri_box, 90)
    p_ili_left = _arc_point(li_box, 180)
    p_ili_bot = _arc_point(bl_box, 270)
    p_iri_right = _arc_point(ri_box, 0)
    p_iri_bot = _arc_point(br_box, 270)

    # --- DEBUG: log arc edge points used for trimming (after computing inner pts) ---
    logger.info(f"[FRAME DEBUG] p_left_top={p_left_top} p_right_top={p_right_top}")
    logger.info(f"[FRAME DEBUG] p_left_left={p_left_left} p_left_bot={p_left_bot}")
    logger.info(f"[FRAME DEBUG] p_right_right={p_right_right} p_right_bot={p_right_bot}")
    logger.info(f"[FRAME DEBUG] p_ili_top={p_ili_top} p_iri_top={p_iri_top} p_ili_bot={p_ili_bot} p_iri_bot={p_iri_bot}")

    # =====================================================================
    # Replace drawing with a frame-layer + mask approach:
    # - draw straight lines onto frame_layer using EXACT same geometry as before
    # - erase (mask-out) ellipse areas under arcs so straight lines are removed there
    # - draw arcs on frame_layer
    # - composite frame_layer onto base image
    # This guarantees line positions are not altered; only pixels under arcs are removed.
    # =====================================================================

    frame_layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw_frame = ImageDraw.Draw(frame_layer)

    # --- DEBUG (visual): draw bbox outlines on frame_layer so we can see where arcs will be ---
    try:
        dbg_col = (255, 0, 0, 180)
        draw_frame.rectangle([int(left_arc_box[0]), int(left_arc_box[1]), int(left_arc_box[2]), int(left_arc_box[3])],
                             outline=dbg_col, width=1)
        draw_frame.rectangle([int(right_arc_box[0]), int(right_arc_box[1]), int(right_arc_box[2]), int(right_arc_box[3])],
                             outline=dbg_col, width=1)
        draw_frame.rectangle([int(bottom_left_arc_box[0]), int(bottom_left_arc_box[1]), int(bottom_left_arc_box[2]), int(bottom_left_arc_box[3])],
                             outline=dbg_col, width=1)
        draw_frame.rectangle([int(bottom_right_arc_box[0]), int(bottom_right_arc_box[1]), int(bottom_right_arc_box[2]), int(bottom_right_arc_box[3])],
                             outline=dbg_col, width=1)
        # inner boxes too
        draw_frame.rectangle([int(li_box[0]), int(li_box[1]), int(li_box[2]), int(li_box[3])], outline=dbg_col, width=1)
        draw_frame.rectangle([int(ri_box[0]), int(ri_box[1]), int(ri_box[2]), int(ri_box[3])], outline=dbg_col, width=1)
        draw_frame.rectangle([int(bl_box[0]), int(bl_box[1]), int(bl_box[2]), int(bl_box[3])], outline=dbg_col, width=1)
        draw_frame.rectangle([int(br_box[0]), int(br_box[1]), int(br_box[2]), int(br_box[3])], outline=dbg_col, width=1)
    except Exception:
        logger.info("FRAME DEBUG: visual bbox draw failed, continuing")

    # --- 1) draw outer straight lines on frame_layer using the same coordinate logic as before ---
    # horizontals (use same start/end logic so positions remain unchanged)
    top_y = oy + int(outer_width / 2) + line_inset_outer
    bot_y = oy + oh - int(outer_width / 2) - line_inset_outer

    start_x = max(ox + line_inset_outer, p_left_top[0] + corner_trim)
    end_x = min(ox + ow - line_inset_outer, p_right_top[0] - corner_trim)
    if start_x < end_x:
        draw_frame.line([_clamp_center((start_x, top_y), outer_width), _clamp_center((end_x, top_y), outer_width)],
                        fill=frame_color, width=outer_width)

    start_x_b = max(ox + line_inset_outer, p_left_bot[0] + corner_trim)
    end_x_b = min(ox + ow - line_inset_outer, p_right_bot[0] - corner_trim)
    if start_x_b < end_x_b:
        draw_frame.line([_clamp_center((start_x_b, bot_y), outer_width), _clamp_center((end_x_b, bot_y), outer_width)],
                        fill=frame_color, width=outer_width)

    # verticals
    left_x = ox + int(outer_width / 2) + line_inset_outer
    right_x = ox + ow - int(outer_width / 2) - line_inset_outer

    start_y = max(oy + line_inset_outer, p_left_left[1] + corner_trim)
    end_y = min(oy + oh - line_inset_outer, p_left_bot[1] - corner_trim)
    if start_y < end_y:
        draw_frame.line([_clamp_center((left_x, start_y), outer_width), _clamp_center((left_x, end_y), outer_width)],
                        fill=frame_color, width=outer_width)

    start_y_r = max(oy + line_inset_outer, p_right_right[1] + corner_trim)
    end_y_r = min(oy + oh - line_inset_outer, p_right_bot[1] - corner_trim)
    if start_y_r < end_y_r:
        draw_frame.line([_clamp_center((right_x, start_y_r), outer_width), _clamp_center((right_x, end_y_r), outer_width)],
                        fill=frame_color, width=outer_width)

    # --- 2) erase regions under outer arcs from frame_layer via mask (so straight lines are removed there) ---
    mask = Image.new("L", (w, h), 255)  # 255 = keep, 0 = erase
    draw_mask = ImageDraw.Draw(mask)

    outer_half = math.ceil(outer_width / 2)
    inflate_outer = outer_half + corner_trim + 1  # safety pad; tweak only for visual pixel remnant, not line position

    # log outer inflate (inner inflate logged later when defined)
    logger.info(f"[FRAME DEBUG] outer_half={outer_half} inflate_outer={inflate_outer}")

    def _inflate_bbox(bbox, pad):
        x0, y0, x1, y1 = bbox
        return [int(x0 - pad), int(y0 - pad), int(x1 + pad), int(y1 + pad)]

    draw_mask.ellipse(_inflate_bbox(left_arc_box, inflate_outer), fill=0)
    draw_mask.ellipse(_inflate_bbox(right_arc_box, inflate_outer), fill=0)
    draw_mask.ellipse(_inflate_bbox(bottom_left_arc_box, inflate_outer), fill=0)
    draw_mask.ellipse(_inflate_bbox(bottom_right_arc_box, inflate_outer), fill=0)

    transparent = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    frame_layer = Image.composite(frame_layer, transparent, mask)

    # --- DEBUG: quick check — sample pixel inside left arc bbox center after mask applied ---
    try:
        cx = int((left_arc_box[0] + left_arc_box[2]) / 2)
        cy = int((left_arc_box[1] + left_arc_box[3]) / 2)
        pix = frame_layer.getpixel((max(0, min(w-1, cx)), max(0, min(h-1, cy))))
        logger.info(f"[FRAME DEBUG] sample_pixel_after_mask_left_arc at ({cx},{cy}) = {pix}")
    except Exception as e:
        logger.info(f"[FRAME DEBUG] sample pixel check failed: {e}")

    # --- 3) draw outer arcs onto frame_layer ---
    draw_frame = ImageDraw.Draw(frame_layer)
    try:
        draw_frame.arc(left_arc_box, start=0, end=90, fill=frame_color, width=outer_width)
        draw_frame.arc(right_arc_box, start=90, end=180, fill=frame_color, width=outer_width)
        draw_frame.arc(bottom_right_arc_box, start=180, end=270, fill=frame_color, width=outer_width)
        draw_frame.arc(bottom_left_arc_box, start=270, end=360, fill=frame_color, width=outer_width)
    except Exception:
        draw_frame.arc(left_arc_box, start=0, end=90, fill=frame_color)
        draw_frame.arc(right_arc_box, start=90, end=180, fill=frame_color)
        draw_frame.arc(bottom_right_arc_box, start=180, end=270, fill=frame_color)
        draw_frame.arc(bottom_left_arc_box, start=270, end=360, fill=frame_color)

    # --- DEBUG: test draw arcs directly (red thick) for visibility check; remove after testing ---
    try:
        test_layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        td = ImageDraw.Draw(test_layer)
        td.arc(left_arc_box, start=0, end=90, fill=(255, 0, 0, 255), width=max(12, outer_width + 6))
        td.arc(right_arc_box, start=90, end=180, fill=(255, 0, 0, 255), width=max(12, outer_width + 6))
        td.arc(bottom_right_arc_box, start=180, end=270, fill=(255, 0, 0, 255), width=max(12, outer_width + 6))
        td.arc(bottom_left_arc_box, start=270, end=360, fill=(255, 0, 0, 255), width=max(12, outer_width + 6))
        try:
            test_img = Image.alpha_composite(img.convert("RGBA"), test_layer)
            test_img.save("/tmp/guild_frame_debug_arcs.png")
            logger.debug("[FRAME DEBUG] saved test arc overlay to /tmp/guild_frame_debug_arcs.png")
        except Exception as e:
            logger.info(f"[FRAME DEBUG] failed to save test image: {e}")
    except Exception:
        logger.info("FRAME DEBUG: test arc overlay failed, continuing")

    # --- 4) inner straight lines drawn onto frame_layer (positions unchanged) ---
    in_overlap = 0

    inner_top_y = iy + int(inner_width / 2) + line_inset_inner
    inner_bot_y = iy + ih - int(inner_width / 2) - line_inset_inner

    start_in_top = (int(p_ili_top[0]), inner_top_y)
    end_in_top = (int(p_iri_top[0]), inner_top_y)
    if start_in_top[0] < end_in_top[0]:
        draw_frame.line([_clamp_center(start_in_top, inner_width), _clamp_center(end_in_top, inner_width)],
                        fill=(95, 60, 35, 220), width=inner_width)

    start_in_bot = (int(p_ili_bot[0]), inner_bot_y)
    end_in_bot = (int(p_iri_bot[0]), inner_bot_y)
    if start_in_bot[0] < end_in_bot[0]:
        draw_frame.line([_clamp_center(start_in_bot, inner_width), _clamp_center(end_in_bot, inner_width)],
                        fill=(95, 60, 35, 220), width=inner_width)

    # inner verticals: use fixed x positions (as before) and inner_top_y/inner_bot_y for y endpoints
    left_ix = ix + int(inner_width / 2) + line_inset_inner
    right_ix = ix + iw - int(inner_width / 2) - line_inset_inner
    if inner_top_y < inner_bot_y:
        draw_frame.line([_clamp_center((left_ix, inner_top_y), inner_width), _clamp_center((left_ix, inner_bot_y), inner_width)],
                        fill=(95, 60, 35, 220), width=inner_width)
        draw_frame.line([_clamp_center((right_ix, inner_top_y), inner_width), _clamp_center((right_ix, inner_bot_y), inner_width)],
                        fill=(95, 60, 35, 220), width=inner_width)

    # erase inner arc coverage areas from frame_layer as well
    mask_inner = Image.new("L", (w, h), 255)
    dm = ImageDraw.Draw(mask_inner)
    inner_half = math.ceil(inner_width / 2)
    inflate_inner = inner_half + corner_trim + 1

    # log inner inflate now that it's defined
    logger.info(f"[FRAME DEBUG] inner_half={inner_half} inflate_inner={inflate_inner}")

    dm.ellipse(_inflate_bbox(li_box, inflate_inner), fill=0)
    dm.ellipse(_inflate_bbox(ri_box, inflate_inner), fill=0)
    dm.ellipse(_inflate_bbox(bl_box, inflate_inner), fill=0)
    dm.ellipse(_inflate_bbox(br_box, inflate_inner), fill=0)
    frame_layer = Image.composite(frame_layer, transparent, mask_inner)

    # draw inner arcs onto frame_layer
    draw_frame = ImageDraw.Draw(frame_layer)
    try:
        draw_frame.arc(li_box, start=0, end=90, fill=(95, 60, 35, 220), width=inner_width)
        draw_frame.arc(ri_box, start=90, end=180, fill=(95, 60, 35, 220), width=inner_width)
        draw_frame.arc(br_box, start=180, end=270, fill=(95, 60, 35, 220), width=inner_width)
        draw_frame.arc(bl_box, start=270, end=360, fill=(95, 60, 35, 220), width=inner_width)
    except Exception:
        draw_frame.arc(li_box, start=0, end=90, fill=(95, 60, 35, 220))
        draw_frame.arc(ri_box, start=90, end=180, fill=(95, 60, 35, 220))
        draw_frame.arc(br_box, start=180, end=270, fill=(95, 60, 35, 220))
        draw_frame.arc(bl_box, start=270, end=360, fill=(95, 60, 35, 220))

    # --- 5) composite frame_layer onto the original 'out' image and continue (rest unchanged) ---
    out = img.convert("RGBA")
    out = Image.alpha_composite(out, frame_layer)

    # 装飾的なルール線・ボックス（元実装に近い位置で描画）
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
        logger.info("rule/box draw failed, skipping")

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
