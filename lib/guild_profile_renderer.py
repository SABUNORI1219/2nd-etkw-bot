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
CANVAS_WIDTH = 700   # 縦長の幅に縮小（縦方向に伸ばします）
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

# NumPy availability (not required, but optional for noise)
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
    外枠（太）＋内枠（細）＋角飾りを描画する。
    outer_offset/inner_offset を None にすると画像サイズに応じた値を自動計算します。
    四隅を少し丸く（凹み風）に見せるため、ラウンド＆小さな「くぼみ」を掛け合わせています。
    返り値は RGBA イメージ。
    """
    w, h = img.size
    # 自動オフセット: 画像サイズに応じた余白を計算（縦長を想定）
    if outer_offset is None:
        outer_offset = max(12, int(min(w, h) * 0.025))
    if inner_offset is None:
        inner_offset = outer_offset + max(8, int(min(w, h) * 0.02))

    out = img.convert("RGBA")
    draw = ImageDraw.Draw(out)

    # 外枠（丸角の矩形）
    ox = outer_offset
    oy = outer_offset
    ow = w - outer_offset * 2
    oh = h - outer_offset * 2
    # 外枠の角丸半径（ほどよく丸める）
    outer_radius = max(8, int(min(w, h) * 0.02))
    try:
        # Pillow の rounded_rectangle が使える場合は利用
        draw.rounded_rectangle([ox, oy, ox + ow, oy + oh], radius=outer_radius, outline=frame_color, width=outer_width)
    except Exception:
        # フォールバック：普通の矩形
        draw.rectangle([ox, oy, ox + ow, oy + oh], outline=frame_color, width=outer_width)

    # 内枠（丸角の細い矩形）
    ix = inner_offset
    iy = inner_offset
    iw = w - inner_offset * 2
    ih = h - inner_offset * 2
    inner_color = (95, 60, 35, 220)
    inner_radius = max(6, int(min(w, h) * 0.015))
    try:
        draw.rounded_rectangle([ix, iy, ix + iw, iy + ih], radius=inner_radius, outline=inner_color, width=inner_width)
    except Exception:
        draw.rectangle([ix, iy, ix + iw, iy + ih], outline=inner_color, width=inner_width)

        # 角の「凹み（concave notch）」を描く（改良版）
    # 小さな円弧（BASE_BG_COLOR で塗りつぶし）で凹ませつつ、
    # その上から枠線を短い線分で再描画して繋がりを維持する。
    notch_size = max(10, int(min(w, h) * 0.03))
    inner_notch = max(6, int(min(w, h) * 0.02))
    # 作業レイヤ（凹みを描く）
    notch_layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    nd = ImageDraw.Draw(notch_layer)
    # 外枠の四隅を背景色でくり抜くように描画（やや内側に寄せる）
    nd.ellipse([ox - notch_size // 2, oy - notch_size // 2, ox + notch_size, oy + notch_size], fill=BASE_BG_COLOR + (255,))  # 左上
    nd.ellipse([ox + ow - notch_size, oy - notch_size // 2, ox + ow + notch_size // 2, oy + notch_size], fill=BASE_BG_COLOR + (255,))  # 右上
    nd.ellipse([ox - notch_size // 2, oy + oh - notch_size, ox + notch_size, oy + oh + notch_size // 2], fill=BASE_BG_COLOR + (255,))  # 左下
    nd.ellipse([ox + ow - notch_size, oy + oh - notch_size, ox + ow + notch_size // 2, oy + oh + notch_size // 2], fill=BASE_BG_COLOR + (255,))  # 右下
    # 内枠の四隅も同様に軽くくぼませる
    nd.ellipse([ix - inner_notch // 2, iy - inner_notch // 2, ix + inner_notch, iy + inner_notch], fill=BASE_BG_COLOR + (255,))  # 内左上
    nd.ellipse([ix + iw - inner_notch, iy - inner_notch // 2, ix + iw + inner_notch // 2, iy + inner_notch], fill=BASE_BG_COLOR + (255,))  # 内右上
    nd.ellipse([ix - inner_notch // 2, iy + ih - inner_notch, ix + inner_notch, iy + ih + inner_notch // 2], fill=BASE_BG_COLOR + (255,))  # 内左下
    nd.ellipse([ix + iw - inner_notch, iy + ih - inner_notch, ix + iw + inner_notch // 2, iy + ih + inner_notch // 2], fill=BASE_BG_COLOR + (255,))  # 内右下

    # ぼかして馴染ませて合成
    notch_layer = notch_layer.filter(ImageFilter.GaussianBlur(1.0))
    out = Image.alpha_composite(out, notch_layer)

    # 凹みで切れた枠線を短いキャップで再接続する（外枠・内枠それぞれ）
    reconnect = ImageDraw.Draw(out)
    # キャップ長は notch に合わせて調整
    cap_len = max(8, int(notch_size * 0.6))
    cap_offset = max(4, int(outer_width / 2))

    # 外枠キャップ（frame_color, outer_width）
    # 左上：水平と垂直を少し延ばす
    reconnect.line([(ox + corner_len, oy + cap_offset), (ox + corner_len + cap_len, oy + cap_offset)],
                   fill=frame_color, width=outer_width)
    reconnect.line([(ox + cap_offset, oy + corner_len), (ox + cap_offset, oy + corner_len + cap_len)],
                   fill=frame_color, width=outer_width)
    # 右上
    reconnect.line([(ox + ow - corner_len - cap_len, oy + cap_offset), (ox + ow - corner_len, oy + cap_offset)],
                   fill=frame_color, width=outer_width)
    reconnect.line([(ox + ow - cap_offset, oy + corner_len), (ox + ow - cap_offset, oy + corner_len + cap_len)],
                   fill=frame_color, width=outer_width)
    # 左下
    reconnect.line([(ox + corner_len, oy + oh - cap_offset), (ox + corner_len + cap_len, oy + oh - cap_offset)],
                   fill=frame_color, width=outer_width)
    reconnect.line([(ox + cap_offset, oy + oh - corner_len - cap_len), (ox + cap_offset, oy + oh - corner_len)],
                   fill=frame_color, width=outer_width)
    # 右下
    reconnect.line([(ox + ow - corner_len - cap_len, oy + oh - cap_offset), (ox + ow - corner_len, oy + oh - cap_offset)],
                   fill=frame_color, width=outer_width)
    reconnect.line([(ox + ow - cap_offset, oy + oh - corner_len - cap_len), (ox + ow - cap_offset, oy + oh - corner_len)],
                   fill=frame_color, width=outer_width)

    # 内枠キャップ（inner_color, inner_width） — 短めで控えめに
    inner_cap_len = max(6, int(inner_notch * 0.6))
    inner_cap_offset = max(2, int(inner_width / 2))
    # 内左上
    reconnect.line([(ix + int(inner_notch * 0.8), iy + inner_cap_offset), (ix + int(inner_notch * 0.8) + inner_cap_len, iy + inner_cap_offset)],
                   fill=inner_color, width=inner_width)
    reconnect.line([(ix + inner_cap_offset, iy + int(inner_notch * 0.8)), (ix + inner_cap_offset, iy + int(inner_notch * 0.8) + inner_cap_len)],
                   fill=inner_color, width=inner_width)
    # 内右上
    reconnect.line([(ix + iw - int(inner_notch * 0.8) - inner_cap_len, iy + inner_cap_offset), (ix + iw - int(inner_notch * 0.8), iy + inner_cap_offset)],
                   fill=inner_color, width=inner_width)
    reconnect.line([(ix + iw - inner_cap_offset, iy + int(inner_notch * 0.8)), (ix + iw - inner_cap_offset, iy + int(inner_notch * 0.8) + inner_cap_len)],
                   fill=inner_color, width=inner_width)
    # 内左下
    reconnect.line([(ix + int(inner_notch * 0.8), iy + ih - inner_cap_offset), (ix + int(inner_notch * 0.8) + inner_cap_len, iy + ih - inner_cap_offset)],
                   fill=inner_color, width=inner_width)
    reconnect.line([(ix + inner_cap_offset, iy + ih - int(inner_notch * 0.8) - inner_cap_len), (ix + inner_cap_offset, iy + ih - int(inner_notch * 0.8))],
                   fill=inner_color, width=inner_width)
    # 内右下
    reconnect.line([(ix + iw - int(inner_notch * 0.8) - inner_cap_len, iy + ih - inner_cap_offset), (ix + iw - int(inner_notch * 0.8), iy + ih - inner_cap_offset)],
                   fill=inner_color, width=inner_width)
    reconnect.line([(ix + iw - inner_cap_offset, iy + ih - int(inner_notch * 0.8) - inner_cap_len), (ix + iw - inner_cap_offset, iy + ih - int(inner_notch * 0.8))],
                   fill=inner_color, width=inner_width)

    # ルール線（装飾的な横線・バナー矩形）はそのまま上に描画して馴染ませる
    draw = ImageDraw.Draw(out)
    rule_color = (110, 75, 45, 180)
    y_rule = iy + int(ih * 0.12)
    draw.line([(ix + int(iw * 0.03), y_rule), (ix + iw - int(iw * 0.03), y_rule)], fill=rule_color, width=max(2, inner_width + 2))
    y_rule2 = iy + int(ih * 0.48)
    draw.line([(ix + int(iw * 0.03), y_rule2), (ix + int(iw * 0.60), y_rule2)], fill=rule_color, width=max(2, inner_width + 2))
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
    シンプルな紙風背景（ノイズ＋ブラー＋ビネット）に装飾枠を描画して返す。
    焦げ（burn/scorch）処理はすべて削除しました（ユーザ指示）。
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

    # 軽くぼかして紙感
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
    guild_data は API からのそのままの辞書を想定。
    banner_renderer は既存の BannerRenderer インスタンスでバナー画像を作る。
    戻り値: BytesIO (PNG)
    （重要）画像は縦長になるよう幅を CANVAS_WIDTH に固定し、高さはオンライン人数に合わせて伸縮します。
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

    # オンラインプレイヤー解析
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

    # シーズンレーティング
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

    # 動的高さ計算（オンライン数に応じて縦に伸ばす）
    base_height = 700  # ヘッダ等の固定領域（縦長の基準を上げた）
    row_height = 48
    online_count = len(online_players)
    # online プレイヤーリスト領域を伸ばすための余白
    extra_for_online = max(0, online_count) * row_height
    content_height = base_height + extra_for_online + 220  # フッタ余裕
    canvas_w = max_width
    canvas_h = content_height

    # 背景（縦長）作成
    img = create_card_background(canvas_w, canvas_h)
    draw = ImageDraw.Draw(img)

    card_x = MARGIN
    card_y = MARGIN
    card_w = canvas_w - MARGIN * 2
    card_h = canvas_h - MARGIN * 2

    # フォント設定
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

    # ヘッダテキスト
    draw.text((inner_left, inner_top), f"[{prefix}] {name}", font=font_title, fill=TITLE_COLOR)
    draw.text((inner_left, inner_top + 56), f"Owner: {owner}  |  Created: {created}", font=font_sub, fill=SUBTITLE_COLOR)

    # バナー（左上の矩形エリアに入れるレイアウトを維持）
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

    # 主要統計（バナーの右）
    stats_x = banner_x + banner_w + 18
    stats_y = banner_y
    draw.text((stats_x, stats_y), f"Level: {level}   ({xpPercent}%)", font=font_stats, fill=SUBTITLE_COLOR)
    draw.text((stats_x, stats_y + 30), f"Wars: {_fmt_num(wars)}   Territories: {_fmt_num(territories)}", font=font_stats, fill=SUBTITLE_COLOR)
    draw.text((stats_x, stats_y + 60), f"Members: {_fmt_num(total_members)}   Online: {_fmt_num(online_count)}", font=font_stats, fill=SUBTITLE_COLOR)
    draw.text((stats_x, stats_y + 90), f"Latest SR: {rating_display} (Season {latest_season})", font=font_stats, fill=SUBTITLE_COLOR)

    # 区切り線（左／右カラム）
    sep_x = card_x + LEFT_COLUMN_WIDTH
    sep_y1 = inner_top + 24
    sep_y2 = card_y + card_h - 40
    draw.line([(sep_x, sep_y1), (sep_x, sep_y2)], fill=LINE_COLOR, width=2)

    # 右側：オンラインテーブルヘッダ
    table_x = sep_x + 18
    table_y = inner_top + 10
    draw.rectangle([table_x, table_y, table_x + RIGHT_COLUMN_WIDTH - 18, table_y + 40], fill=TABLE_HEADER_BG)
    draw.text((table_x + 8, table_y + 8), "Online Players", font=font_table_header, fill=TITLE_COLOR)
    header_bottom = table_y + 40
    col_server_w = 56
    col_name_w = RIGHT_COLUMN_WIDTH - 18 - col_server_w - 60
    col_rank_w = 60

    # オンラインプレイヤー一覧
    row_h = 44
    y = header_bottom + 12
    if online_players:
        for p in online_players:
            server = p.get("server", "N/A")
            pname = p.get("name", "Unknown")
            rank = p.get("rank_stars", "")

            # server box
            draw.rectangle([table_x, y, table_x + col_server_w, y + row_h - 8], outline=LINE_COLOR, width=1)
            draw.text((table_x + 6, y + 10), server, font=font_table, fill=SUBTITLE_COLOR)

            # name box
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

            # rank box
            rx = nx + col_name_w + 8
            draw.rectangle([rx - 2, y, rx + col_rank_w, y + row_h - 8], outline=LINE_COLOR, width=1)
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
