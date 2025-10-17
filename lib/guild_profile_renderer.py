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

# レイアウト定数
CANVAS_WIDTH = 1000
MARGIN = 40
LEFT_COLUMN_WIDTH = 600
RIGHT_COLUMN_WIDTH = CANVAS_WIDTH - LEFT_COLUMN_WIDTH - MARGIN * 2
LINE_COLOR = (40, 40, 40, 255)
# 単一背景に統一（指定の黄土色）
BASE_BG_COLOR = (218, 179, 99)
TITLE_COLOR = (40, 30, 20, 255)
SUBTITLE_COLOR = (80, 60, 40, 255)
TABLE_HEADER_BG = (230, 230, 230, 255)
ONLINE_BADGE = (60, 200, 60, 255)
OFFLINE_BADGE = (200, 60, 60, 255)

# NumPy availability
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
    draw.textlength が使えればそれを優先し、なければ textbbox を使う。
    """
    try:
        # Pillow >= 8.0 has textlength
        return int(draw_obj.textlength(text, font=font))
    except Exception:
        bbox = draw_obj.textbbox((0, 0), text, font=font)
        return bbox[2] - bbox[0]

def add_burn_edges(base: Image.Image,
                   edge_width: float = 0.14,
                   noise_sd: float = 0.12,
                   threshold: float = 0.22,
                   blur_radius: int = 8,
                   scorch_color=(70, 40, 20),
                   scorch_alpha: int = 220,
                   speckle_density: float = 2.0,
                   seed: Optional[int] = None) -> Image.Image:
    """
    周縁に「ほどよく散る」微粒子レベルの焦げを付与する（返り値 RGBA）。
    - edge_width: 端寄せの幅 (0..0.5)。小さめにして中央侵入を抑える。
    - noise_sd: ノイズのばらつき（numpy 利用時）。
    - threshold: マスクしきい値（0..1）。小さいほど広がる。
    - blur_radius: マスクぼかし。
    - scorch_color: 焦げ色 (R,G,B) — 濃い目の焦げ茶をデフォルトに。
    - scorch_alpha: 焦げレイヤ最大アルファ。
    - speckle_density: 粒子の密度スケール（2.0 程度がほどよい）。
    """
    rnd = random.Random(seed) if seed is not None else random.Random()

    w, h = base.size
    cx, cy = w / 2.0, h / 2.0
    max_r = math.hypot(cx, cy)
    max_inner = min(cx, cy) if min(cx, cy) > 0 else 1.0

    # 1) マスク（高周波ノイズ × edge proximity）
    if _HAS_NUMPY:
        noise = np.random.normal(0.5, noise_sd, (h, w))
        noise = np.clip(noise, 0.0, 1.0)
        ys = np.arange(h) - cy
        xs = np.arange(w) - cx
        xv, yv = np.meshgrid(xs, ys)
        abs_x = np.abs(xv)
        abs_y = np.abs(yv)
        edge_dist_x = cx - abs_x
        edge_dist_y = cy - abs_y
        edge_dist = np.minimum(edge_dist_x, edge_dist_y)
        bp = 1.0 - (edge_dist / max_inner)
        bp = np.clip(bp, 0.0, 1.0)
        combined = noise * bp
        mask_arr = (combined > threshold).astype('uint8') * 255
        mask_img = Image.fromarray(mask_arr, mode='L')
    else:
        mask_img = Image.new('L', (w, h), 0)
        md = mask_img.load()
        for y in range(h):
            for x in range(w):
                dx = abs(x - cx)
                dy = abs(y - cy)
                edge_dist = min(cx - dx, cy - dy)
                bp = 1.0 - (edge_dist / max_inner) if max_inner > 0 else 0.0
                bp = max(0.0, min(1.0, bp))
                n = rnd.gauss(0.5, noise_sd)
                n = max(0.0, min(1.0, n))
                val = n * bp
                md[x, y] = 255 if val > threshold else 0

    # 2) mask を馴染ませる
    mask = mask_img.filter(ImageFilter.GaussianBlur(int(blur_radius)))
    mask = mask.point(lambda p: int(min(255, p * 0.95)))

    # 3) 焦げレイヤ合成（色は下地に馴染むよう alpha で）
    alpha_layer = mask.point(lambda p: int((p / 255.0) * scorch_alpha))
    scorch = Image.new('RGBA', (w, h), scorch_color + (0,))
    scorch.putalpha(alpha_layer)
    out = Image.alpha_composite(base.convert('RGBA'), scorch)

    # 4) 微粒子を周縁全体にまばらに撒く（粒子レベル感）
    speckle_layer = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    sd_draw = ImageDraw.Draw(speckle_layer)
    base_count = int((w * h) / 380.0)
    particle_count = int(base_count * speckle_density)
    particle_count = min(particle_count, 10000)  # 安全上の上限

    for _ in range(particle_count):
        attempts = 0
        while True:
            attempts += 1
            x = rnd.random() * w
            y = rnd.random() * h
            dx = abs(x - cx)
            dy = abs(y - cy)
            edge_dist = min(cx - dx, cy - dy)
            bp = 1.0 - (edge_dist / max_inner) if max_inner > 0 else 0.0
            bp = max(0.0, min(1.0, bp))
            # 周縁優先だが内部にも散る余地を残す（0.08..1.0）
            accept_p = 0.08 + 0.92 * bp
            if rnd.random() < accept_p or attempts > 6:
                break
        rad = rnd.randint(1, 2)
        alpha = rnd.randint(12, 120)  # 濃い粒子も出るよう幅を確保
        color = (scorch_color[0], scorch_color[1], scorch_color[2], alpha)
        bbox = [int(x - rad), int(y - rad), int(x + rad), int(y + rad)]
        sd_draw.ellipse(bbox, fill=color)

    speckle_layer = speckle_layer.filter(ImageFilter.GaussianBlur(0.6))
    out = Image.alpha_composite(out, speckle_layer)

    return out

def draw_decorative_frame(img: Image.Image,
                          outer_offset: int = 18,
                          outer_width: int = 8,
                          inner_offset: int = 28,
                          inner_width: int = 2,
                          frame_color=(85, 50, 30, 255)) -> Image.Image:
    """
    外枠（太）+ 内枠（細）+ 角飾りを描く。引数で太さやオフセットを調整可能。
    返り値は RGBA イメージ。
    """
    w, h = img.size
    out = img.convert("RGBA")
    draw = ImageDraw.Draw(out)

    # 外枠（太め）
    ox = outer_offset
    oy = outer_offset
    ow = w - outer_offset * 2
    oh = h - outer_offset * 2
    # 外枠の輪郭（太線風に矩形を複数重ねて濃淡を出す）
    draw.rectangle([ox, oy, ox + ow, oy + oh], outline=frame_color, width=outer_width)

    # 内枠（細め）
    ix = inner_offset
    iy = inner_offset
    iw = w - inner_offset * 2
    ih = h - inner_offset * 2
    inner_color = (95, 60, 35, 220)
    draw.rectangle([ix, iy, ix + iw, iy + ih], outline=inner_color, width=inner_width)

    # 角飾り（小さい切欠きっぽく）
    corner_len = 18
    corner_thick = max(2, outer_width // 3)
    # 左上
    draw.line([ (ox+corner_thick//2, oy+corner_len), (ox+corner_thick//2, oy+corner_thick//2), (ox+corner_len, oy+corner_thick//2) ],
              fill=frame_color, width=corner_thick)
    # 右上
    draw.line([ (ox+ow-corner_len, oy+corner_thick//2), (ox+ow-corner_thick//2, oy+corner_thick//2), (ox+ow-corner_thick//2, oy+corner_len) ],
              fill=frame_color, width=corner_thick)
    # 左下
    draw.line([ (ox+corner_thick//2, oy+oh-corner_len), (ox+corner_thick//2, oy+oh-corner_thick//2), (ox+corner_len, oy+oh-corner_thick//2) ],
              fill=frame_color, width=corner_thick)
    # 右下
    draw.line([ (ox+ow-corner_len, oy+oh-corner_thick//2), (ox+ow-corner_thick//2, oy+oh-corner_thick//2), (ox+ow-corner_thick//2, oy+oh-corner_len) ],
              fill=frame_color, width=corner_thick)

    # さらに内側のルール線（画像サンプル風に、上・中・左の簡易的なガイドを描画）
    rule_color = (110, 75, 45, 180)
    # 上の水平ルール
    y_rule = iy + int(ih * 0.12)
    draw.line([(ix + 20, y_rule), (ix + iw - 20, y_rule)], fill=rule_color, width=4)
    # 中央の長めの水平ルール（やや下）
    y_rule2 = iy + int(ih * 0.56)
    draw.line([(ix + 20, y_rule2), (ix + int(iw * 0.62), y_rule2)], fill=rule_color, width=4)
    # 左の小矩形（バナー代替）
    box_x = ix + 28
    box_y = iy + int(ih * 0.08)
    box_w = int(iw * 0.18)
    box_h = int(ih * 0.22)
    draw.rectangle([box_x, box_y, box_x + box_w, box_y + box_h], outline=rule_color, width=3)

    return out

def create_card_background(w: int, h: int,
                           noise_std: float = 30.0,
                           noise_blend: float = 0.30,
                           vignette_blur: int = 80) -> Image.Image:
    """
    ノイズ + 軽いブラー + ビネット + 焦げ + 装飾枠 を作る背景生成。
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
            for _ in range(w * h // 800):
                x = random.randrange(0, w)
                y = random.randrange(0, h)
                tone = random.randint(80, 180)
                nd.point((x, y), fill=(tone, tone, tone))

    img = Image.blend(base, noise_img, noise_blend)

    # 軽くぼかして紙感を出す
    img = img.filter(ImageFilter.GaussianBlur(1))

    # ==== ビネット作成（端の暗化）====
    vignette = Image.new('L', (w, h), 0)
    dv = ImageDraw.Draw(vignette)
    max_r = int(max(w, h) * 0.75)
    for i in range(0, max_r, 8):
        val = int(255 * (i / max_r))
        bbox = (-i, -i, w + i, h + i)
        dv.ellipse(bbox, fill=val)
    vignette = vignette.filter(ImageFilter.GaussianBlur(vignette_blur))
    vignette = vignette.point(lambda p: max(0, min(255, p)))

    dark_color = (50, 30, 10)
    dark_img = Image.new('RGB', (w, h), dark_color)
    composed = Image.composite(img, dark_img, vignette)

    # ==== 焦げエッジ（周縁にまばら）====
    try:
        composed = add_burn_edges(composed,
                                  edge_width=0.14,
                                  noise_sd=0.12,
                                  threshold=0.22,
                                  blur_radius=8,
                                  scorch_color=(70, 40, 20),
                                  scorch_alpha=220,
                                  speckle_density=2.0,
                                  seed=None)
    except Exception as e:
        logger.exception(f"add_burn_edges failed: {e}")
        composed = composed.convert('RGBA')

    # ==== 装飾枠を描画（外枠・内枠・角飾り・ルール線）====
    try:
        composed = draw_decorative_frame(composed.convert('RGBA'),
                                        outer_offset=18,
                                        outer_width=8,
                                        inner_offset=28,
                                        inner_width=2,
                                        frame_color=(85, 50, 30, 255))
    except Exception as e:
        logger.exception(f"draw_decorative_frame failed: {e}")

    return composed

def create_guild_image(guild_data: Dict[str, Any], banner_renderer, max_width: int = CANVAS_WIDTH) -> BytesIO:
    """
    guild_data は API からのそのままの辞書を想定。
    banner_renderer は既存の BannerRenderer インスタンスでバナー画像を作る。
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

    # オンラインプレイヤー構造を解析してリスト化
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
            # avoid walrus assignment for compatibility
            if isinstance(payload, dict):
                player_data = payload
                if player_data.get("online"):
                    online_players.append({
                        "name": player_name,
                        "server": player_data.get("server", "N/A"),
                        "rank_stars": rank_to_stars.get(rank_name.upper(), "")
                    })

    # 基本データ
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

    # シーズン最新レーティング（安全に）
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

    # バナー
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

    # 動的高さ計算
    base_height = 480
    row_height = 48
    online_count = len(online_players)
    content_height = base_height + max(0, online_count) * row_height + 140
    canvas_w = max_width
    canvas_h = content_height

    # 背景作成
    img = create_card_background(canvas_w, canvas_h)
    draw = ImageDraw.Draw(img)

    card_x = MARGIN
    card_y = MARGIN
    card_w = canvas_w - MARGIN * 2
    card_h = canvas_h - MARGIN * 2

    # フォント設定（profile_renderer.py と同様）
    try:
        font_title = ImageFont.truetype(FONT_PATH, 48)
        font_sub = ImageFont.truetype(FONT_PATH, 28)
        font_stats = ImageFont.truetype(FONT_PATH, 22)
        font_table_header = ImageFont.truetype(FONT_PATH, 20)
        font_table = ImageFont.truetype(FONT_PATH, 18)
        font_small = ImageFont.truetype(FONT_PATH, 16)
    except Exception as e:
        logger.error(f"FONT_PATH 読み込み失敗: {e}")
        font_title = font_sub = font_stats = font_table_header = font_table = font_small = ImageFont.load_default()

    inner_left = card_x + 30
    inner_top = card_y + 30

    # テキスト描画
    draw.text((inner_left, inner_top), f"[{prefix}] {name}", font=font_title, fill=TITLE_COLOR)
    draw.text((inner_left, inner_top + 64), f"Owner: {owner}  |  Created: {created}", font=font_sub, fill=SUBTITLE_COLOR)

    # バナー
    banner_w = 240
    banner_h = 360
    banner_x = inner_left
    banner_y = inner_top + 110
    if banner_img:
        try:
            banner_resized = banner_img.resize((banner_w, banner_h), Image.LANCZOS)
            img.paste(banner_resized, (banner_x, banner_y), mask=banner_resized)
        except Exception as e:
            logger.warning(f"バナー貼付失敗: {e}")

    # 主要統計
    stats_x = banner_x + banner_w + 24
    stats_y = banner_y
    draw.text((stats_x, stats_y), f"Level: {level}   ({xpPercent}%)", font=font_stats, fill=SUBTITLE_COLOR)
    draw.text((stats_x, stats_y + 36), f"Wars: {_fmt_num(wars)}   Territories: {_fmt_num(territories)}", font=font_stats, fill=SUBTITLE_COLOR)
    draw.text((stats_x, stats_y + 72), f"Members: {_fmt_num(total_members)}   Online: {_fmt_num(online_count)}", font=font_stats, fill=SUBTITLE_COLOR)
    draw.text((stats_x, stats_y + 108), f"Latest SR: {rating_display} (Season {latest_season})", font=font_stats, fill=SUBTITLE_COLOR)

    # 区切り線
    sep_x = card_x + LEFT_COLUMN_WIDTH
    sep_y1 = inner_top + 20
    sep_y2 = card_y + card_h - 40
    draw.line([(sep_x, sep_y1), (sep_x, sep_y2)], fill=LINE_COLOR, width=2)

    # オンラインテーブル（簡易）
    table_x = sep_x + 20
    table_y = inner_top + 10
    draw.rectangle([table_x, table_y, table_x + RIGHT_COLUMN_WIDTH - 20, table_y + 40], fill=TABLE_HEADER_BG)
    draw.text((table_x + 8, table_y + 8), "Online Players", font=font_table_header, fill=TITLE_COLOR)
    header_bottom = table_y + 40
    col_server_w = 58
    col_name_w = RIGHT_COLUMN_WIDTH - 20 - col_server_w - 70
    col_rank_w = 70

    row_h = 44
    y = header_bottom + 10
    if online_players:
        for p in online_players:
            server = p.get("server", "N/A")
            pname = p.get("name", "Unknown")
            rank = p.get("rank_stars", "")

            draw.rectangle([table_x, y, table_x + col_server_w, y + row_h - 6], outline=LINE_COLOR, width=1)
            draw.text((table_x + 6, y + 10), server, font=font_table, fill=SUBTITLE_COLOR)

            nx = table_x + col_server_w + 8
            draw.rectangle([nx - 2, y, nx + col_name_w, y + row_h - 6], outline=LINE_COLOR, width=1)

            try:
                name_w = _text_width(draw, pname, font=font_table)
            except Exception:
                bbox = draw.textbbox((0,0), pname, font=font_table)
                name_w = bbox[2] - bbox[0]
            display_name = pname
            max_name_w = col_name_w - 12
            if name_w > max_name_w:
                # 末尾を切る簡易処理（安全に）
                while display_name and (_text_width(draw, display_name + "...", font=font_table) > max_name_w):
                    display_name = display_name[:-1]
                display_name = display_name + "..."
            draw.text((nx + 6, y + 10), display_name, font=font_table, fill=TITLE_COLOR)

            rx = nx + col_name_w + 8
            draw.rectangle([rx - 2, y, rx + col_rank_w, y + row_h - 6], outline=LINE_COLOR, width=1)
            draw.text((rx + 6, y + 10), rank, font=font_table, fill=SUBTITLE_COLOR)

            y += row_h
    else:
        draw.text((table_x + 8, header_bottom + 18), "No members online right now.", font=font_table, fill=SUBTITLE_COLOR)

    # フッター
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
