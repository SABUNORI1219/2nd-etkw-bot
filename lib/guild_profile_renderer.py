from PIL import Image, ImageDraw, ImageFont, ImageFilter
from io import BytesIO
import os
import logging
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
BACKGROUND_COLOR = (245, 242, 238, 255)  # 新聞風・薄いベージュ
CARD_BG = (255, 255, 255, 255)
TITLE_COLOR = (40, 30, 20, 255)
SUBTITLE_COLOR = (80, 60, 40, 255)
TABLE_HEADER_BG = (230, 230, 230, 255)
ONLINE_BADGE = (60, 200, 60, 255)
OFFLINE_BADGE = (200, 60, 60, 255)

def _load_font(size):
    try:
        return ImageFont.truetype(FONT_PATH, size)
    except Exception:
        logger.warning("フォント読み込み失敗 - デフォルトフォントを使用します")
        from PIL import ImageFont
        return ImageFont.load_default()

def _fmt_num(v):
    try:
        if isinstance(v, int):
            return f"{v:,}"
        if isinstance(v, float):
            return f"{v:,.0f}"
        return str(v)
    except Exception:
        return str(v)

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
            if isinstance(payload, dict) and payload.get("online"):
                online_players.append({
                    "name": player_name,
                    "server": payload.get("server", "N/A"),
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
        banner_bytes = banner_renderer.create_banner_image(guild_data.get("banner"))
        if banner_bytes:
            from PIL import Image
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
    right_padding = MARGIN
    content_height = base_height + max(0, online_count) * row_height + 140
    canvas_w = max_width
    canvas_h = content_height

    # キャンバス作成
    img = Image.new("RGBA", (canvas_w, canvas_h), BACKGROUND_COLOR)
    draw = ImageDraw.Draw(img)

    # カード背景（ちょっと影付きでカード風に）
    card_x = MARGIN
    card_y = MARGIN
    card_w = canvas_w - MARGIN * 2
    card_h = canvas_h - MARGIN * 2
    # 影
    shadow = Image.new("RGBA", (card_w, card_h), (0,0,0,0))
    sd = ImageDraw.Draw(shadow)
    sd.rounded_rectangle([6,6,card_w-6,card_h-6], radius=16, fill=(0,0,0,30))
    shadow = shadow.filter(ImageFilter.GaussianBlur(4))
    img.alpha_composite(shadow, (card_x, card_y))
    # 背景矩形
    card = Image.new("RGBA", (card_w, card_h), CARD_BG)
    img.paste(card, (card_x, card_y), mask=card)

    # フォント
    font_title = _load_font(48)
    font_sub = _load_font(28)
    font_stats = _load_font(22)
    font_table_header = _load_font(20)
    font_table = _load_font(18)
    font_small = _load_font(16)

    inner_left = card_x + 30
    inner_top = card_y + 30

    # 左側：タイトル・バナー・主要統計
    # タイトル
    draw.text((inner_left, inner_top), f"[{prefix}] {name}", font=font_title, fill=TITLE_COLOR)
    # サブタイトル (owner, created)
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

    # 右側：オンラインプレイヤーテーブル（新聞風スタイル）
    table_x = sep_x + 20
    table_y = inner_top + 10
    # テーブルヘッダー
    draw.rectangle([table_x, table_y, table_x + RIGHT_COLUMN_WIDTH - 20, table_y + 40], fill=TABLE_HEADER_BG)
    draw.text((table_x + 8, table_y + 8), "Online Players", font=font_table_header, fill=TITLE_COLOR)
    # ヘッダの下に行を描く
    header_bottom = table_y + 40
    # 列幅
    col_server_w = 58
    col_name_w = RIGHT_COLUMN_WIDTH - 20 - col_server_w - 70  # rank列の予備幅
    col_rank_w = 70

    # 各行を書く
    row_h = 44
    y = header_bottom + 10
    if online_players:
        for p in online_players:
            # server
            server = p.get("server", "N/A")
            name = p.get("name", "Unknown")
            rank = p.get("rank_stars", "")

            # 行背景（交互）
            # if idx % 2 == 0: draw.rectangle([...], fill=(250,250,250,255))

            # サーバー矩形
            draw.rectangle([table_x, y, table_x + col_server_w, y + row_h - 6], outline=LINE_COLOR, width=1)
            draw.text((table_x + 6, y + 10), server, font=font_table, fill=SUBTITLE_COLOR)

            # プレイヤー名
            nx = table_x + col_server_w + 8
            draw.rectangle([nx - 2, y, nx + col_name_w, y + row_h - 6], outline=LINE_COLOR, width=1)
            draw.text((nx + 6, y + 10), name, font=font_table, fill=TITLE_COLOR)

            # ランク（星）
            rx = nx + col_name_w + 8
            draw.rectangle([rx - 2, y, rx + col_rank_w, y + row_h - 6], outline=LINE_COLOR, width=1)
            draw.text((rx + 6, y + 10), rank, font=font_table, fill=SUBTITLE_COLOR)

            y += row_h
    else:
        # オンラインが0人
        draw.text((table_x + 8, header_bottom + 18), "No members online right now.", font=font_table, fill=SUBTITLE_COLOR)

    # フッター（小さく生成者表記）
    footer_text = "Generated by Minister Chikuwa"
    fw, fh = draw.textlength(footer_text, font=font_small), font_small.getsize(footer_text)[1]
    draw.text((card_x + card_w - fw - 16, card_y + card_h - 36), footer_text, font=font_small, fill=(120, 110, 100, 255))

    # 結果を BytesIO で返す
    out = BytesIO()
    img.save(out, format="PNG")
    out.seek(0)

    # close images if any
    try:
        if banner_img:
            banner_img.close()
    except Exception:
        pass

    return out
