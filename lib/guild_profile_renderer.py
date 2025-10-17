from PIL import Image, ImageDraw, ImageFont, ImageFilter
from io import BytesIO
import os
import logging
import random
import numpy as np
from typing import Dict, List, Any

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
# 単一背景に統一
BASE_BG_COLOR = (218, 179, 99)  # ベース色 変えるな
TITLE_COLOR = (40, 30, 20, 255)
SUBTITLE_COLOR = (80, 60, 40, 255)
TABLE_HEADER_BG = (230, 230, 230, 255)
ONLINE_BADGE = (60, 200, 60, 255)
OFFLINE_BADGE = (200, 60, 60, 255)

# NumPy availability (we import at top; assume present in environment)
_HAS_NUMPY = True

def _fmt_num(v):
    try:
        if isinstance(v, int):
            return f"{v:,}"
        if isinstance(v, float):
            return f"{v:,.0f}"
        return str(v)
    except Exception:
        return str(v)

def _add_burn_speckles(base: Image.Image, density_factor: float = 1.0, edge_bias: float = 0.5,
                       radius_range=(1, 3), alpha_range=(10, 70), seed: int | None = None) -> Image.Image:
    """
    ベース画像の周縁に「焦げの微粒子（小さな粒子が多数）」を散らす。
    - density_factor: 粒子の総数スケーリング（1.0がデフォルト）
    - edge_bias: 0..1.0 (0中央均一 / 1 完全に端寄せ)。値が大きいほど端に偏る。
    - radius_range: 各粒子の半径(px)の範囲（小さい値を指定）
    - alpha_range: 粒子の不透明度範囲
    - seed: 再現シード
    """
    if seed is not None:
        rnd = random.Random(seed)
    else:
        rnd = random.Random()

    w, h = base.size
    cx, cy = w / 2.0, h / 2.0
    max_r = (cx ** 2 + cy ** 2) ** 0.5

    # 粒子数目安（画像サイズに依存）：増やしすぎ注意
    base_count = int((w * h) / 900.0)  # 例えば 1000x600 -> ~666
    total_count = max(200, int(base_count * density_factor))

    speckle_layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    sd = ImageDraw.Draw(speckle_layer)

    for i in range(total_count):
        # candidate position
        x = rnd.random() * w
        y = rnd.random() * h
        # compute normalized distance from center (0 center - 1 corner)
        d = ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5 / max_r
        # probability to accept this speckle based on edge_bias
        # transform d by bias: higher edge_bias -> prefer values near 1
        p = max(0.0, min(1.0, (d - (1.0 - edge_bias)) / edge_bias)) if edge_bias > 0 else d
        # random threshold to reduce count and emphasize edges
        if rnd.random() > p:
            continue

        r = rnd.randint(radius_range[0], radius_range[1])
        a = rnd.randint(alpha_range[0], alpha_range[1])
        # small irregularity: sometimes make elongated ellipse
        if rnd.random() < 0.12:
            rx = r + rnd.randint(0, r)
            ry = r
        else:
            rx = ry = r

        bbox = [int(x - rx), int(y - ry), int(x + rx), int(y + ry)]
        # color: dark burnt brown
        color = (45, 28, 16, a)
        sd.ellipse(bbox, fill=color)

    # 微小ブラーで馴染ませ（ほんの少しだけ）
    speckle_layer = speckle_layer.filter(ImageFilter.GaussianBlur(1))

    # 軽く全体の暗さを変えるため multiply 合成の代わりに alpha_compositeで重ねる
    out = base.convert("RGBA")
    out = Image.alpha_composite(out, speckle_layer)
    return out

def create_card_background(w: int, h: int,
                           noise_std: float = 30.0,
                           noise_blend: float = 0.30,
                           vignette_blur: int = 80,
                           vignette_strength: float = 1.0) -> Image.Image:
    """
    ノイズ + 軽いブラー + ビネット + 微粒子焦げ を作る。
    """
    base_color = BASE_BG_COLOR
    base = Image.new("RGB", (w, h), base_color)

    # ==== ノイズ生成（NumPy を使用）====
    try:
        noise = np.random.normal(128, noise_std, (h, w))
        noise = np.clip(noise, 0, 255).astype(np.uint8)
        noise_img = Image.fromarray(noise, mode="L").convert("RGB")
    except Exception:
        # fallback
        try:
            noise = Image.effect_noise((w, h), max(10, int(noise_std))).convert("L")
            noise = noise.point(lambda p: int((p - 128) * (noise_std / 30.0) + 128))
            noise_img = noise.convert("RGB")
        except Exception:
            noise_img = Image.new("RGB", (w, h), (128, 128, 128))

    img = Image.blend(base, noise_img, noise_blend)

    # 軽くぼかして紙感
    img = img.filter(ImageFilter.GaussianBlur(1))

    # ==== ビネットマスク（端の暗化）====
    vignette = Image.new("L", (w, h), 0)
    dv = ImageDraw.Draw(vignette)
    max_r = int(max(w, h) * 0.75)
    # ループ回数を減らして高速化（6 -> 8 step）
    for i in range(0, max_r, 8):
        val = int(255 * (i / max_r))
        bbox = (-i, -i, w + i, h + i)
        dv.ellipse(bbox, fill=val)
    vignette = vignette.filter(ImageFilter.GaussianBlur(vignette_blur))

    dark_color = (50, 30, 10)
    dark_img = Image.new("RGB", (w, h), dark_color)
    composed = Image.composite(img, dark_img, vignette)

    # ==== 微粒子焦げ（粒子レベル）====
    # パラメータ: density_factor を増やすと粒子数が増える（1.0がデフォルト）
    # edge_bias: 1.0なら完全に端寄せ、0.0なら中央まで混ざる
    composed = _add_burn_speckles(composed, density_factor=1.8, edge_bias=0.6,
                                  radius_range=(1, 3), alpha_range=(12, 70))

    # 軽い斑点オーバーレイ（小さめのスポットを少量）
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    spot_count = max(6, int((w * h) / (900 * 600))) * 6
    for _ in range(spot_count):
        side = random.choice(["top", "bottom", "left", "right"])
        r = random.randint(6, 26)  # 小さいスポットに変更
        if side == "top":
            x = random.randint(0, w)
            y = random.randint(0, int(h * 0.12))
        elif side == "bottom":
            x = random.randint(0, w)
            y = random.randint(int(h * 0.88), h - 1)
        elif side == "left":
            x = random.randint(0, int(w * 0.08))
            y = random.randint(0, h)
        else:
            x = random.randint(int(w * 0.92), w - 1)
            y = random.randint(0, h)
        bbox = [x - r, y - r, x + r, y + r]
        od.ellipse(bbox, fill=(45, 26, 14, random.randint(18, 70)))
    overlay = overlay.filter(ImageFilter.GaussianBlur(3))
    composed = Image.alpha_composite(composed.convert("RGBA"), overlay)

    return composed

def create_guild_image(guild_data: Dict[str, Any], banner_renderer, max_width: int = CANVAS_WIDTH) -> BytesIO:
    """
    guild_data は API からのそのままの辞書を想定。
    banner_renderer は既存の BannerRenderer インスタンスで、
      banner_renderer.create_banner_image(guild_banner_obj) -> BytesIO-or-bytes を返す想定。
    戻り値: BytesIO (PNG)
    """
    # 安全取得ヘルパ
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
            if isinstance(payload, dict) and player_data := payload:
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
    created = sg(guild_data, "created", default="N/A").split("T")[0] if isinstance(sg(guild_data, "created", default="N/A"), str) else sg(guild_data, "created", default="N/A")
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
    base_height = 480  # ヘッダ等の固定領域
    row_height = 48     # オンラインプレイヤー1行の高さ
    online_count = len(online_players)
    content_height = base_height + max(0, online_count) * row_height + 140
    canvas_w = max_width
    canvas_h = content_height

    # キャンバス作成（指定のノイズ + ビネット背景）
    img = create_card_background(canvas_w, canvas_h)
    draw = ImageDraw.Draw(img)

    card_x = MARGIN
    card_y = MARGIN
    card_w = canvas_w - MARGIN * 2
    card_h = canvas_h - MARGIN * 2

    # フォント設定（profile_renderer.py と同様の読み込み方法）
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

    # テキスト色は暗めで描画（背景に馴染むように）
    draw.text((inner_left, inner_top), f"[{prefix}] {name}", font=font_title, fill=TITLE_COLOR)
    draw.text((inner_left, inner_top + 64), f"Owner: {owner}  |  Created: {created}", font=font_sub, fill=SUBTITLE_COLOR)

    # バナー表示（左カラム上部に）
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

    # 主要統計（バナー右）
    stats_x = banner_x + banner_w + 24
    stats_y = banner_y
    draw.text((stats_x, stats_y), f"Level: {level}   ({xpPercent}%)", font=font_stats, fill=SUBTITLE_COLOR)
    draw.text((stats_x, stats_y + 36), f"Wars: {_fmt_num(wars)}   Territories: {_fmt_num(territories)}", font=font_stats, fill=SUBTITLE_COLOR)
    draw.text((stats_x, stats_y + 72), f"Members: {_fmt_num(total_members)}   Online: {_fmt_num(online_count)}", font=font_stats, fill=SUBTITLE_COLOR)
    draw.text((stats_x, stats_y + 108), f"Latest SR: {rating_display} (Season {latest_season})", font=font_stats, fill=SUBTITLE_COLOR)

    # 区切り線（左部と右部）
    sep_x = card_x + LEFT_COLUMN_WIDTH
    sep_y1 = inner_top + 20
    sep_y2 = card_y + card_h - 40
    draw.line([(sep_x, sep_y1), (sep_x, sep_y2)], fill=LINE_COLOR, width=2)

    # 右側：オンラインプレイヤーテーブル
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
                while display_name and ( (draw.textlength(display_name + "...", font=font_table) if hasattr(draw, "textlength") else (draw.textbbox((0,0), display_name + "...", font=font_table)[2] - draw.textbbox((0,0), display_name + "...", font=font_table)[0]) ) > max_name_w):
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
