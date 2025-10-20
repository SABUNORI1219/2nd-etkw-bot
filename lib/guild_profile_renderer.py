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


def draw_decorative_frame(img: Image.Image,
                          outer_offset: Optional[int] = None,
                          outer_width: int = 8,
                          inner_offset: Optional[int] = None,
                          inner_width: int = 2,
                          frame_color=(85, 50, 30, 255)) -> Image.Image:
    """
    安定的なマスク方式で外枠（太）＋内枠（細）を描画する。
    - 外側矩形を塗りつぶして中心をくり抜き、四隅を円でくり抜く（内向きの凹み）。
    - くり抜きは透明にしたまま、アーチの線は上から arc を描いて表示する。
    戻り値は RGBA イメージ。
    """
    w, h = img.size

    # デフォルトオフセット自動計算
    if outer_offset is None:
        outer_offset = max(12, int(min(w, h) * 0.025))
    if inner_offset is None:
        inner_offset = outer_offset + max(8, int(min(w, h) * 0.02))

    ox = int(outer_offset)
    oy = int(outer_offset)
    ow = int(w - outer_offset * 2)
    oh = int(h - outer_offset * 2)

    ix = int(inner_offset)
    iy = int(inner_offset)
    iw = int(w - inner_offset * 2)
    ih = int(h - inner_offset * 2)

    # 凹み（notch）サイズ（px）
    notch_radius = max(12, int(min(w, h) * 0.035))
    inner_notch = max(6, int(min(w, h) * 0.02))

    out = img.convert("RGBA")

    # ---- 外枠マスク作成 ----
    mask_outer = Image.new("L", (w, h), 0)
    md = ImageDraw.Draw(mask_outer)

    # 外側長方形を塗りつぶしてから内側をくり抜く（リング状にする）
    md.rectangle([ox, oy, ox + ow, oy + oh], fill=255)
    inner_cut = [ox + outer_width, oy + outer_width, ox + ow - outer_width, oy + oh - outer_width]
    if inner_cut[2] > inner_cut[0] and inner_cut[3] > inner_cut[1]:
        md.rectangle(inner_cut, fill=0)

    # 四隅の notch（円）を角に置いてくり抜く（透明にする）
    md.ellipse([ox - notch_radius, oy - notch_radius, ox + notch_radius, oy + notch_radius], fill=0)  # 左上
    md.ellipse([ox + ow - notch_radius, oy - notch_radius, ox + ow + notch_radius, oy + notch_radius], fill=0)  # 右上
    md.ellipse([ox - notch_radius, oy + oh - notch_radius, ox + notch_radius, oy + oh + notch_radius], fill=0)  # 左下
    md.ellipse([ox + ow - notch_radius, oy + oh - notch_radius, ox + ow + notch_radius, oy + oh + notch_radius], fill=0)  # 右下

    # カラー層に alpha としてマスクを設定して合成（外枠のリングを作る）
    layer_outer = Image.new("RGBA", (w, h), frame_color)
    layer_outer.putalpha(mask_outer)
    out = Image.alpha_composite(out, layer_outer)

    # ---- 外枠のアーチ線を上から描画（マスクで空いた部分に線を引く） ----
    draw_outer = ImageDraw.Draw(out)
    # アーチ用の bbox を角の外側に置く（bbox の一辺が角に一致する形）
    arc_extent = notch_radius * 2
    left_arc_box = [ox - arc_extent, oy - arc_extent, ox, oy]  # bottom-right == (ox,oy)
    right_arc_box = [ox + ow, oy - arc_extent, ox + ow + arc_extent, oy]  # bottom-left == (ox+ow,oy)
    bottom_left_arc_box = [ox - arc_extent, oy + oh, ox, oy + oh + arc_extent]
    bottom_right_arc_box = [ox + ow, oy + oh, ox + ow + arc_extent, oy + oh + arc_extent]

    try:
        draw_outer.arc(left_arc_box, start=0, end=90, fill=frame_color, width=outer_width)       # top-left concave
        draw_outer.arc(right_arc_box, start=90, end=180, fill=frame_color, width=outer_width)    # top-right
        draw_outer.arc(bottom_right_arc_box, start=180, end=270, fill=frame_color, width=outer_width)  # bottom-right
        draw_outer.arc(bottom_left_arc_box, start=270, end=360, fill=frame_color, width=outer_width)   # bottom-left
    except Exception:
        # Pillow の環境で幅を無視する場合のフォールバック（細線でも描く）
        draw_outer.arc(left_arc_box, start=0, end=90, fill=frame_color)
        draw_outer.arc(right_arc_box, start=90, end=180, fill=frame_color)
        draw_outer.arc(bottom_right_arc_box, start=180, end=270, fill=frame_color)
        draw_outer.arc(bottom_left_arc_box, start=270, end=360, fill=frame_color)

    # ---- 内枠マスク作成（外枠より内側） ----
    mask_inner = Image.new("L", (w, h), 0)
    md2 = ImageDraw.Draw(mask_inner)

    md2.rectangle([ix, iy, ix + iw, iy + ih], fill=255)
    inner2_cut = [ix + inner_width, iy + inner_width, ix + iw - inner_width, iy + ih - inner_width]
    if inner2_cut[2] > inner2_cut[0] and inner2_cut[3] > inner2_cut[1]:
        md2.rectangle(inner2_cut, fill=0)

    md2.ellipse([ix - inner_notch, iy - inner_notch, ix + inner_notch, iy + inner_notch], fill=0)  # 内左上
    md2.ellipse([ix + iw - inner_notch, iy - inner_notch, ix + iw + inner_notch, iy + inner_notch], fill=0)  # 内右上
    md2.ellipse([ix - inner_notch, iy + ih - inner_notch, ix + inner_notch, iy + ih + inner_notch], fill=0)  # 内左下
    md2.ellipse([ix + iw - inner_notch, iy + ih - inner_notch, ix + iw + inner_notch, iy + ih + inner_notch], fill=0)  # 内右下

    inner_color = (95, 60, 35, 220)
    layer_inner = Image.new("RGBA", (w, h), inner_color)
    layer_inner.putalpha(mask_inner)
    out = Image.alpha_composite(out, layer_inner)

    # ---- 内枠のアーチ線を上から描画 ----
    draw_inner = ImageDraw.Draw(out)
    inner_arc_extent = int(inner_notch * 2)
    li_box = [ix - inner_arc_extent, iy - inner_arc_extent, ix, iy]
    ri_box = [ix + iw, iy - inner_arc_extent, ix + iw + inner_arc_extent, iy]
    bli_box = [ix - inner_arc_extent, iy + ih, ix, iy + ih + inner_arc_extent]
    bri_box = [ix + iw, iy + ih, ix + iw + inner_arc_extent, iy + ih + inner_arc_extent]

    try:
        draw_inner.arc(li_box, start=0, end=90, fill=inner_color, width=inner_width)
        draw_inner.arc(ri_box, start=90, end=180, fill=inner_color, width=inner_width)
        draw_inner.arc(bri_box, start=180, end=270, fill=inner_color, width=inner_width)
        draw_inner.arc(bli_box, start=270, end=360, fill=inner_color, width=inner_width)
    except Exception:
        draw_inner.arc(li_box, start=0, end=90, fill=inner_color)
        draw_inner.arc(ri_box, start=90, end=180, fill=inner_color)
        draw_inner.arc(bri_box, start=180, end=270, fill=inner_color)
        draw_inner.arc(bli_box, start=270, end=360, fill=inner_color)

    # ---- 装飾ルール線・ボックスは最後に上書きで描画 ----
    draw = ImageDraw.Draw(out)
    rule_color = (110, 75, 45, 180)
    y_rule = iy + int(ih * 0.12)
    draw.line([(ix + int(iw * 0.03), y_rule), (ix + iw - int(iw * 0.03), y_rule)],
              fill=rule_color, width=max(2, inner_width + 2))
    y_rule2 = iy + int(ih * 0.48)
    draw.line([(ix + int(iw * 0.03), y_rule2), (ix + int(iw * 0.60), y_rule2)],
              fill=rule_color, width=max(2, inner_width + 2))
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
