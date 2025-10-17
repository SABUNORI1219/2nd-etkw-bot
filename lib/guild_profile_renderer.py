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

def add_burn_edges(base: Image.Image,
                   edge_width: float = 0.16,
                   noise_sd: float = 0.15,
                   threshold: float = 0.36,
                   blur_radius: float = 10,
                   scorch_color=(45, 28, 16),
                   scorch_alpha: int = 190,
                   speckle_density: float = 1.6,
                   seed: Optional[int] = None) -> Image.Image:
    """
    base に“焼け（焦げ）”を自然に付与して RGBA を返す。
    - edge_width: 外縁領域の幅（0.0-0.5）
    - noise_sd: ノイズの標準偏差（numpy 用、0.15 程度が細かめ）
    - threshold: ノイズしきい値（0-1）で焼けの広がり調整
    - blur_radius: マスクをブラーして馴染ませる(px)
    - scorch_color: (R,G,B) 焦げ色
    - scorch_alpha: 焦げの最大アルファ（0-255）
    - speckle_density: 微粒子の量（1.0 基準）
    - seed: 再現用シード
    """
    if seed is not None:
        rnd = random.Random(seed)
    else:
        rnd = random.Random()

    w, h = base.size
    cx, cy = w / 2.0, h / 2.0
    max_r = math.hypot(cx, cy)

    # 1) 作業マスク（combined noise × radial）
    # Create noise and radial, combine to mask
    if _HAS_NUMPY:
        # noise: mean 0.5, sd noise_sd, clipped 0..1
        noise = np.random.normal(0.5, noise_sd, (h, w))
        noise = np.clip(noise, 0.0, 1.0)
        # radial distance normalized (0 center, 1 corner)
        ys = np.linspace(0, h - 1, h) - cy
        xs = np.linspace(0, w - 1, w) - cx
        xv, yv = np.meshgrid(xs, ys)
        d = np.sqrt(xv * xv + yv * yv) / max_r  # 0..1
        # scaled radial: only outer band passes (1 when near corner)
        start = 1.0 - edge_width
        scaled = (d - start) / (edge_width if edge_width > 0 else 1.0)
        scaled = np.clip(scaled, 0.0, 1.0)
        combined = noise * scaled  # fine-grained mask 0..1
        # threshold to emphasize shapes
        mask_arr = (combined > threshold).astype('uint8') * 255
        mask_img = Image.fromarray(mask_arr, mode='L')
    else:
        # PIL fallback - compute radial and noise in Python (slower)
        mask_img = Image.new("L", (w, h), 0)
        md = mask_img.load()
        for y in range(h):
            dy = y - cy
            for x in range(w):
                dx = x - cx
                d = math.hypot(dx, dy) / max_r
                # radial scaled
                start = 1.0 - edge_width
                if d <= start:
                    scaled = 0.0
                else:
                    scaled = min(1.0, (d - start) / (edge_width if edge_width > 0 else 1.0))
                # noise approx by random value
                n = rnd.gauss(0.5, noise_sd)
                n = max(0.0, min(1.0, n))
                val = n * scaled
                md[x, y] = 255 if val > threshold else 0

    # 2) soften mask
    mask = mask_img.filter(ImageFilter.GaussianBlur(int(blur_radius)))
    # optional reduce intensity slightly
    mask = mask.point(lambda p: int(min(255, p * 0.95)))

    # 3) create scorch layer with alpha from mask
    alpha_layer = mask.point(lambda p: int((p / 255.0) * scorch_alpha))
    scorch = Image.new("RGBA", (w, h), scorch_color + (0,))
    scorch.putalpha(alpha_layer)
    out = Image.alpha_composite(base.convert("RGBA"), scorch)

    # 4) add many micro-speckles biased to the edge area to get "粒子レベル"
    speckle_layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    sd_draw = ImageDraw.Draw(speckle_layer)
    # particle count scaled with image area and speckle_density
    base_count = int((w * h) / 350.0)
    particle_count = int(base_count * speckle_density)
    for _ in range(particle_count):
        # sample a radius biased to outer area
        # sample angle uniformly, radius biased toward max_r
        angle = rnd.random() * 2.0 * math.pi
        # rpos sample between inner_r and max_r
        inner_r = max_r * (1.0 - edge_width * 1.3)
        rpos = inner_r + (rnd.random() ** 1.8) * (max_r - inner_r)  # bias outward
        x = cx + rpos * math.cos(angle)
        y = cy + rpos * math.sin(angle)
        rad = rnd.randint(1, 2)  # very small particles
        a = rnd.randint(8, 60)
        bbox = [int(x - rad), int(y - rad), int(x + rad), int(y + rad)]
        sd_draw.ellipse(bbox, fill=(scorch_color[0], scorch_color[1], scorch_color[2], a))
    # slight blur to integrate
    speckle_layer = speckle_layer.filter(ImageFilter.GaussianBlur(0.9))
    out = Image.alpha_composite(out, speckle_layer)

    return out

def create_card_background(w: int, h: int,
                           noise_std: float = 30.0,
                           noise_blend: float = 0.30,
                           vignette_blur: int = 80) -> Image.Image:
    """
    ノイズ + 軽いブラー + ビネット + 改良焦げ（add_burn_edges）を作る背景生成。
    """
    base = Image.new("RGB", (w, h), BASE_BG_COLOR)

    # ==== ノイズ生成 ====
    if _HAS_NUMPY:
        try:
            noise = np.random.normal(128, noise_std, (h, w))
            noise = np.clip(noise, 0, 255).astype(np.uint8)
            noise_img = Image.fromarray(noise, mode="L").convert("RGB")
        except Exception:
            noise_img = Image.effect_noise((w, h), max(10, int(noise_std))).convert("L").convert("RGB")
    else:
        try:
            noise_img = Image.effect_noise((w, h), max(10, int(noise_std))).convert("L").convert("RGB")
        except Exception:
            # fallback sparse dots
            noise_img = Image.new("RGB", (w, h), (128, 128, 128))
            nd = ImageDraw.Draw(noise_img)
            for _ in range(w * h // 800):
                x = random.randrange(0, w)
                y = random.randrange(0, h)
                tone = random.randint(80, 180)
                nd.point((x, y), fill=(tone, tone, tone))

    img = Image.blend(base, noise_img, noise_blend)
    img = img.filter(ImageFilter.GaussianBlur(1))

    # ==== ビネット（端の暗化）====
    vignette = Image.new("L", (w, h), 0)
    dv = ImageDraw.Draw(vignette)
    max_r = int(max(w, h) * 0.75)
    for i in range(0, max_r, 8):
        val = int(255 * (i / max_r))
        bbox = (-i, -i, w + i, h + i)
        dv.ellipse(bbox, fill=val)
    vignette = vignette.filter(ImageFilter.GaussianBlur(vignette_blur))
    vignette = vignette.point(lambda p: max(0, min(255, p)))

    dark_color = (50, 30, 10)
    dark_img = Image.new("RGB", (w, h), dark_color)
    composed = Image.composite(img, dark_img, vignette)

    # ==== 改良焦げエッジ: add_burn_edges を呼び出す（これが中心の改良点） ====
    try:
        composed_rgba = add_burn_edges(composed,
                                       edge_width=0.16,
                                       noise_sd=0.15,
                                       threshold=0.36,
                                       blur_radius=10,
                                       scorch_color=(45, 28, 16),
                                       scorch_alpha=180,
                                       speckle_density=1.8,
                                       seed=None)
    except Exception as e:
        logger.exception(f"add_burn_edges failed: {e}")
        composed_rgba = composed.convert("RGBA")

    return composed_rgba

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
                name_w = draw.textlength(pname, font=font_table)
            except Exception:
                bbox = draw.textbbox((0,0), pname, font=font_table)
                name_w = bbox[2] - bbox[0]
            display_name = pname
            max_name_w = col_name_w - 12
            if name_w > max_name_w:
                # 簡易省略処理
                while display_name and ((draw.textlength(display_name + "...", font=font_table) if hasattr(draw, "textlength") else (draw.textbbox((0,0), display_name + "...", font=font_table)[2] - draw.textbbox((0,0), display_name + "...", font=font_table)[0])) > max_name_w):
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
        fw = draw.textlength(footer_text, font=font_small)
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
