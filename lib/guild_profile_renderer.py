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


# Replace the existing draw_decorative_frame(...) implementation in lib/guild_profile_renderer.py with the function below.

def draw_decorative_frame(img: Image.Image,
                          outer_offset: Optional[int] = None,
                          outer_width: int = 8,
                          inner_offset: Optional[int] = None,
                          inner_width: int = 2,
                          frame_color=(85, 50, 30, 255),
                          # --- 新オプション（可搬・省略可） ---
                          # これらを与えなければ既存のデフォルト振る舞い（かつ柔軟）になります。
                          corner_trim_override: Optional[int] = None,
                          line_inset_outer_override: Optional[int] = None,
                          line_inset_inner_override: Optional[int] = None,
                          arc_nudge_outer_x: int = 0,
                          arc_nudge_outer_y: int = 0,
                          arc_nudge_inner_x: int = 0,
                          arc_nudge_inner_y: int = 0) -> Image.Image:
    """
    外枠（太）＋内枠（細）を描画します。

    変更点（目的：ハードな上限・下限をなくして柔軟に調整できるように）
    - corner_trim 等の「固定下限・上限」を取り除き、override パラメータで明示的に指定できるようにしました。
    - デフォルトは過去の挙動を踏襲しつつ、outer_width に応じて合理的に負の値を許容する自動計算を行います（過剰な -64 などは不要）。
    - アーチ位置を個別に微調整する arc_nudge_* 引数を追加（直線の位置は変更しないでアーチだけ移動できます）。
    - 変数名は既存のまま維持しています（left_arc_box, p_left_top, outer_width 等）。
    """
    w, h = img.size

    # アーチ半径（既存）
    notch_radius = max(12, int(min(w, h) * 0.035))
    arc_diameter = notch_radius * 2

    # 内アーチ半径（既存）
    inner_notch_radius = max(8, int(notch_radius * 0.90))
    inner_arc_diameter = inner_notch_radius * 2

    # 既存の「パラメータ群」
    arc_pad = max(8, int(notch_radius * 0.35))
    inner_pad = max(6, int(inner_notch_radius * 0.30))

    # line_inset は override があればそれを使う（柔軟化）
    if line_inset_outer_override is not None:
        line_inset_outer = int(line_inset_outer_override)
    else:
        line_inset_outer = -40

    if line_inset_inner_override is not None:
        line_inset_inner = int(line_inset_inner_override)
    else:
        line_inset_inner = -32

    # corner_trim: override があればそのまま使う
    if corner_trim_override is not None:
        corner_trim = int(corner_trim_override)
    else:
        # 自動値 = アーチサイズに基づくベース値 － 太線幅/2（これにより太線と直線が自然に接合する）
        # ここで負値も許容する（直線を伸ばすために必要な最小値と整合）
        corner_trim = int(notch_radius * 0.25) - math.ceil(outer_width / 2)

    # --- offset の安全化（既存のロジックを維持。ただし override による柔軟性を残す） ---
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

    def _clamp_center(pt, stroke_w):
        # safety: ここは画像のピクセル境界外描画を防ぐ最低限のクランプです（削除しないこと推奨）
        half = stroke_w / 2.0
        x = max(half, min(w - half, pt[0]))
        y = max(half, min(h - half, pt[1]))
        return (x, y)

    def _inflate_bbox(bbox, pad):
        x0, y0, x1, y1 = bbox
        return [int(x0 - pad), int(y0 - pad), int(x1 + pad), int(y1 + pad)]

    def _expand_and_clamp_bbox(bbox, pad):
        x0, y0, x1, y1 = bbox
        x0e = max(0, int(math.floor(x0 - pad)))
        y0e = max(0, int(math.floor(y0 - pad)))
        x1e = min(w, int(math.ceil(x1 + pad)))
        y1e = min(h, int(math.ceil(y1 + pad)))
        if x1e <= x0e:
            x1e = min(w, x0e + 1)
        if y1e <= y0e:
            y1e = min(h, y0e + 1)
        return [x0e, y0e, x1e, y1e]

    # -------------------------
    # straight-line anchors（既存）
    # -------------------------
    top_y = oy + int(outer_width / 2) + line_inset_outer
    bot_y = oy + oh - int(outer_width / 2) - line_inset_outer
    left_x = ox + int(outer_width / 2) + line_inset_outer
    right_x = ox + ow - int(outer_width / 2) - line_inset_outer

    # アーチ bbox（arc_nudge_* を反映してアーチだけ個別に動かせる）
    r = arc_diameter / 2.0
    left_arc_box = [left_x - r + arc_nudge_outer_x, top_y + arc_nudge_outer_y, left_x + r + arc_nudge_outer_x, top_y + 2 * r + arc_nudge_outer_y]
    right_arc_box = [right_x - r + arc_nudge_outer_x, top_y + arc_nudge_outer_y, right_x + r + arc_nudge_outer_x, top_y + 2 * r + arc_nudge_outer_y]
    bottom_left_arc_box = [left_x - r + arc_nudge_outer_x, bot_y - 2 * r + arc_nudge_outer_y, left_x + r + arc_nudge_outer_x, bot_y + arc_nudge_outer_y]
    bottom_right_arc_box = [right_x - r + arc_nudge_outer_x, bot_y - 2 * r + arc_nudge_outer_y, right_x + r + arc_nudge_outer_x, bot_y + arc_nudge_outer_y]

    # inner arc bboxes（inner 用の nudge）
    inner_top_y = iy + int(inner_width / 2) + line_inset_inner
    inner_bot_y = iy + ih - int(inner_width / 2) - line_inset_inner
    left_ix = ix + int(inner_width / 2) + line_inset_inner
    right_ix = ix + iw - int(inner_width / 2) - line_inset_inner
    r_i = inner_arc_diameter / 2.0
    li_box = [left_ix - r_i + arc_nudge_inner_x, inner_top_y + arc_nudge_inner_y, left_ix + r_i + arc_nudge_inner_x, inner_top_y + 2 * r_i + arc_nudge_inner_y]
    ri_box = [right_ix - r_i + arc_nudge_inner_x, inner_top_y + arc_nudge_inner_y, right_ix + r_i + arc_nudge_inner_x, inner_top_y + 2 * r_i + arc_nudge_inner_y]
    bl_box = [left_ix - r_i + arc_nudge_inner_x, inner_bot_y - 2 * r_i + arc_nudge_inner_y, left_ix + r_i + arc_nudge_inner_x, inner_bot_y + arc_nudge_inner_y]
    br_box = [right_ix - r_i + arc_nudge_inner_x, inner_bot_y - 2 * r_i + arc_nudge_inner_y, right_ix + r_i + arc_nudge_inner_x, inner_bot_y + arc_nudge_inner_y]

    # arc edge points
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

    # -------------------------------------------------------------------
    # frame_layer に直線を描画 → mask で穴あけ → 合成 → out に直接アーチを描画
    # -------------------------------------------------------------------
    frame_layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw_frame = ImageDraw.Draw(frame_layer)

    # 外枠 horizontals
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

    # 外枠 verticals
    left_xc = left_x
    right_xc = right_x
    start_y = max(oy + line_inset_outer, p_left_left[1] + corner_trim)
    end_y = min(oy + oh - line_inset_outer, p_left_bot[1] - corner_trim)
    if start_y < end_y:
        draw_frame.line([_clamp_center((left_xc, start_y), outer_width), _clamp_center((left_xc, end_y), outer_width)],
                        fill=frame_color, width=outer_width)

    start_y_r = max(oy + line_inset_outer, p_right_right[1] + corner_trim)
    end_y_r = min(oy + oh - line_inset_outer, p_right_bot[1] - corner_trim)
    if start_y_r < end_y_r:
        draw_frame.line([_clamp_center((right_xc, start_y_r), outer_width), _clamp_center((right_xc, end_y_r), outer_width)],
                        fill=frame_color, width=outer_width)

    # mask で外アーチ領域を消す（inflate は corner_trim に応じて自動調整）
    mask = Image.new("L", (w, h), 255)
    draw_mask = ImageDraw.Draw(mask)
    outer_half = math.ceil(outer_width / 2)
    inflate_outer = outer_half + abs(corner_trim) + 1
    draw_mask.ellipse(_inflate_bbox(left_arc_box, inflate_outer), fill=0)
    draw_mask.ellipse(_inflate_bbox(right_arc_box, inflate_outer), fill=0)
    draw_mask.ellipse(_inflate_bbox(bottom_left_arc_box, inflate_outer), fill=0)
    draw_mask.ellipse(_inflate_bbox(bottom_right_arc_box, inflate_outer), fill=0)
    frame_layer = Image.composite(frame_layer, Image.new("RGBA", (w, h), (0, 0, 0, 0)), mask)

    out = Image.alpha_composite(out, frame_layer)

    # out にアーチを直接描画（stroke が bbox 辺で切れないよう pad を少し余裕を持たせる）
    draw_out = ImageDraw.Draw(out)
    stroke_pad = math.ceil(outer_width / 2) + 1
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
        try:
            draw_out.pieslice(left_bbox, start=0, end=90, fill=frame_color)
            inner_left = [left_bbox[0] + outer_width, left_bbox[1] + outer_width, left_bbox[2] - outer_width, left_bbox[3] - outer_width]
            if inner_left[2] > inner_left[0] and inner_left[3] > inner_left[1]:
                draw_out.pieslice(inner_left, start=0, end=90, fill=(0, 0, 0, 0))
            draw_out.pieslice(right_bbox, start=90, end=180, fill=frame_color)
            inner_right = [right_bbox[0] + outer_width, right_bbox[1] + outer_width, right_bbox[2] - outer_width, right_bbox[3] - outer_width]
            if inner_right[2] > inner_right[0] and inner_right[3] > inner_right[1]:
                draw_out.pieslice(inner_right, start=90, end=180, fill=(0, 0, 0, 0))
            draw_out.pieslice(br_bbox, start=180, end=270, fill=frame_color)
            inner_br = [br_bbox[0] + outer_width, br_bbox[1] + outer_width, br_bbox[2] - outer_width, br_bbox[3] - outer_width]
            if inner_br[2] > inner_br[0] and inner_br[3] > inner_br[1]:
                draw_out.pieslice(inner_br, start=180, end=270, fill=(0, 0, 0, 0))
            draw_out.pieslice(bl_bbox, start=270, end=360, fill=frame_color)
            inner_bl = [bl_bbox[0] + outer_width, bl_bbox[1] + outer_width, bl_bbox[2] - outer_width, bl_bbox[3] - outer_width]
            if inner_bl[2] > inner_bl[0] and inner_bl[3] > inner_bl[1]:
                draw_out.pieslice(inner_bl, start=270, end=360, fill=(0, 0, 0, 0))
        except Exception:
            logger.debug("Outer arc fallback failed; skipping outer arcs")

    # --- inner lines/arcs (同様に) ---
    inner_layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw_inner_layer = ImageDraw.Draw(inner_layer)

    sxi = max(ix + line_inset_inner, p_ili_top[0] + corner_trim)
    exi = min(ix + iw - line_inset_inner, p_iri_top[0] - corner_trim)
    if sxi < exi:
        draw_inner_layer.line([_clamp_center((sxi, inner_top_y), inner_width), _clamp_center((exi, inner_top_y), inner_width)],
                              fill=(95, 60, 35, 220), width=inner_width)

    sxb = max(ix + line_inset_inner, p_ili_bot[0] + corner_trim)
    exb = min(ix + iw - line_inset_inner, p_iri_bot[0] - corner_trim)
    if sxb < exb:
        draw_inner_layer.line([_clamp_center((sxb, inner_bot_y), inner_width), _clamp_center((exb, inner_bot_y), inner_width)],
                              fill=(95, 60, 35, 220), width=inner_width)

    left_ix_center = left_ix
    right_ix_center = right_ix
    syi = max(iy + line_inset_inner, p_ili_left[1] + corner_trim)
    eyi = min(iy + ih - line_inset_inner, p_ili_bot[1] - corner_trim)
    if syi < eyi:
        draw_inner_layer.line([_clamp_center((left_ix_center, syi), inner_width), _clamp_center((left_ix_center, eyi), inner_width)],
                              fill=(95, 60, 35, 220), width=inner_width)

    syi_r = max(iy + line_inset_inner, p_iri_right[1] + corner_trim)
    eyi_r = min(iy + ih - line_inset_inner, p_iri_bot[1] - corner_trim)
    if syi_r < eyi_r:
        draw_inner_layer.line([_clamp_center((right_ix_center, syi_r), inner_width), _clamp_center((right_ix_center, eyi_r), inner_width)],
                              fill=(95, 60, 35, 220), width=inner_width)

    mask_inner = Image.new("L", (w, h), 255)
    dm = ImageDraw.Draw(mask_inner)
    inner_half = math.ceil(inner_width / 2)
    inflate_inner = inner_half + abs(corner_trim) + 1
    dm.ellipse(_inflate_bbox(li_box, inflate_inner), fill=0)
    dm.ellipse(_inflate_bbox(ri_box, inflate_inner), fill=0)
    dm.ellipse(_inflate_bbox(bl_box, inflate_inner), fill=0)
    dm.ellipse(_inflate_bbox(br_box, inflate_inner), fill=0)
    inner_layer = Image.composite(inner_layer, Image.new("RGBA", (w, h), (0, 0, 0, 0)), mask_inner)

    out = Image.alpha_composite(out, inner_layer)

    # draw inner arcs on up-to-date out
    draw_out = ImageDraw.Draw(out)
    stroke_pad_i = math.ceil(inner_width / 2) + 1
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
        try:
            draw_out.pieslice(li_bbox, start=0, end=90, fill=(95, 60, 35, 220))
            inner_li = [li_bbox[0] + inner_width, li_bbox[1] + inner_width, li_bbox[2] - inner_width, li_bbox[3] - inner_width]
            if inner_li[2] > inner_li[0] and inner_li[3] > inner_li[1]:
                draw_out.pieslice(inner_li, start=0, end=90, fill=(0, 0, 0, 0))
            draw_out.pieslice(ri_bbox, start=90, end=180, fill=(95, 60, 35, 220))
            inner_ri = [ri_bbox[0] + inner_width, ri_bbox[1] + inner_width, ri_bbox[2] - inner_width, ri_bbox[3] - inner_width]
            if inner_ri[2] > inner_ri[0] and inner_ri[3] > inner_ri[1]:
                draw_out.pieslice(inner_ri, start=90, end=180, fill=(0, 0, 0, 0))
            draw_out.pieslice(bri_bbox, start=180, end=270, fill=(95, 60, 35, 220))
            inner_br = [bri_bbox[0] + inner_width, bri_bbox[1] + inner_width, bri_bbox[2] - inner_width, bri_bbox[3] - inner_width]
            if inner_br[2] > inner_br[0] and inner_br[3] > inner_br[1]:
                draw_out.pieslice(inner_br, start=180, end=270, fill=(0, 0, 0, 0))
            draw_out.pieslice(bli_bbox, start=270, end=360, fill=(95, 60, 35, 220))
            inner_bl = [bli_bbox[0] + inner_width, bli_bbox[1] + inner_width, bli_bbox[2] - inner_width, bli_bbox[3] - inner_width]
            if inner_bl[2] > inner_bl[0] and inner_bl[3] > inner_bl[1]:
                draw_out.pieslice(inner_bl, start=270, end=360, fill=(0, 0, 0, 0))
        except Exception:
            logger.debug("Inner arc fallback failed; skipping inner arcs")

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

    out_bytes = BytesIO()
    # 修正: 正しい変数 img を保存する（以前のバグは out を参照していたため NameError が発生）
    img.save(out_bytes, format="PNG")
    out_bytes.seek(0)

    try:
        if isinstance(banner_img, Image.Image):
            banner_img.close()
    except Exception:
        pass

    return out_bytes
