from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
import os
import logging
import json
import discord
from datetime import datetime, timezone, timedelta
from math import sqrt

logger = logging.getLogger(__name__)

# アセットとフォントのパスを定義
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS_PATH = os.path.join(project_root, "assets", "map")
FONT_PATH = os.path.join(project_root, "assets", "fonts", "NotoSansJP-Bold.ttf")

class MapRenderer:
    def __init__(self):
        try:
            self.map_img = Image.open(os.path.join(ASSETS_PATH, "main-map.png")).convert("RGBA")
            with open(os.path.join(ASSETS_PATH, "territories.json"), "r", encoding='utf-8') as f:
                self.local_territories = json.load(f)
            self.font = ImageFont.truetype(FONT_PATH, 40)

            TARGET_WIDTH = 1600
            original_w, original_h = self.map_img.size
            scale_factor = TARGET_WIDTH / original_w
            new_h = int(original_h * scale_factor)
            self.resized_map = self.map_img.resize((TARGET_WIDTH, new_h), Image.Resampling.LANCZOS)
            self.scale_factor = scale_factor # 初期リサイズ時のスケールファクターを保存
            logger.info(f"--- [MapRenderer] ベースマップを初期リサイズしました: {TARGET_WIDTH}x{new_h}")
        
        except FileNotFoundError as e:
            logger.error(f"マップ生成に必要なアセットが見つかりません: {e}")
            raise

    def _coord_to_pixel(self, x, z):
        return x + 2383, z + 6572

    def _hex_to_rgb(self, hex_color: str) -> tuple:
        hex_color = hex_color.lstrip('#')
        try:
            return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        except (ValueError, IndexError):
            return (255, 255, 255)

    def _draw_trading_and_territories(self, map_to_draw_on, box, is_zoomed, territory_data, guild_color_map):
        overlay = Image.new("RGBA", map_to_draw_on.size, (0,0,0,0))
        overlay_draw = ImageDraw.Draw(overlay)
        draw = ImageDraw.Draw(map_to_draw_on)
        
        # 1. 全ての交易路を地図の裏側に薄く描画する
        for name, data in self.local_territories.items():
            if "Trading Routes" not in data or "Location" not in data:
                continue
            try:
                x1 = (data["Location"]["start"][0] + data["Location"]["end"][0]) // 2
                z1 = (data["Location"]["start"][1] + data["Location"]["end"][1]) // 2
                l_px1, l_py1 = self._coord_to_pixel(x1, z1)
                l_scaled_px1, l_scaled_py1 = l_px1 * self.scale_factor, l_py1 * self.scale_factor
                for destination_name in data["Trading Routes"]:
                    dest_data = self.local_territories.get(destination_name)
                    if not dest_data or "Location" not in dest_data:
                        continue
                    x2 = (dest_data["Location"]["start"][0] + dest_data["Location"]["end"][0]) // 2
                    z2 = (dest_data["Location"]["start"][1] + dest_data["Location"]["end"][1]) // 2
                    l_px2, l_py2 = self._coord_to_pixel(x2, z2)
                    l_scaled_px2, l_scaled_py2 = l_px2 * self.scale_factor, l_py2 * self.scale_factor
                    if is_zoomed and box:
                        l_px1_rel, l_px2_rel = l_scaled_px1 - box[0], l_scaled_px2 - box[0]
                        l_py1_rel, l_py2_rel = l_scaled_py1 - box[1], l_scaled_py2 - box[1]
                        draw.line([(l_px1_rel, l_py1_rel), (l_px2_rel, l_py2_rel)], fill=(10, 10, 10, 128), width=1)
                    else:
                        draw.line([(l_scaled_px1, l_scaled_py1), (l_scaled_px2, l_scaled_py2)], fill=(10, 10, 10, 128), width=1)
            except KeyError:
                continue

        # Font Scaling dayo!
        scaled_font_size = max(12, int(self.font.size * self.scale_factor))
        try:
            scaled_font = ImageFont.truetype(FONT_PATH, scaled_font_size)
        except IOError:
            scaled_font = ImageFont.load_default()

        # --- 2. 全てのテリトリーを描画 ---
        for name, info in territory_data.items():
            if 'location' not in info or 'guild' not in info:
                continue
            t_px1, t_py1 = self._coord_to_pixel(*info["location"]["start"])
            t_px2, t_py2 = self._coord_to_pixel(*info["location"]["end"])
            t_scaled_px1, t_scaled_py1 = t_px1 * self.scale_factor, t_py1 * self.scale_factor
            t_scaled_px2, t_scaled_py2 = t_px2 * self.scale_factor, t_py2 * self.scale_factor
            if is_zoomed and box:
                t_px1_rel, t_px2_rel = t_scaled_px1 - box[0], t_scaled_px2 - box[0]
                t_py1_rel, t_py2_rel = t_scaled_py1 - box[1], t_scaled_py2 - box[1]
            else:
                t_px1_rel, t_py1_rel, t_px2_rel, t_py2_rel = t_scaled_px1, t_scaled_py1, t_scaled_px2, t_scaled_py2
            x_min, x_max = sorted([t_px1_rel, t_px2_rel])
            y_min, y_max = sorted([t_py1_rel, t_py2_rel])
            if x_max > 0 and y_max > 0 and x_min < map_to_draw_on.width and y_min < map_to_draw_on.height:
                prefix = info["guild"]["prefix"]
                color_hex = guild_color_map.get(prefix, "#FFFFFF")
                color_rgb = self._hex_to_rgb(color_hex)
                overlay_draw.rectangle([x_min, y_min, x_max, y_max], fill=(*color_rgb, 64))
                draw.rectangle([x_min, y_min, x_max, y_max], outline=color_rgb, width=2)
                draw.text(((x_min + x_max)/2, (y_min + y_max)/2), prefix, font=scaled_font, fill=color_rgb, anchor="mm", stroke_width=2, stroke_fill="black")

        return map_to_draw_on

    def create_territory_map(self, territory_data: dict, territories_to_render: dict, guild_color_map: dict) -> tuple[discord.File | None, discord.Embed | None]:
        if not territories_to_render:
            return None, None

        try:
            # 地図のコピーと初期化
            map_to_draw_on = self.resized_map.copy()
            box = None
            all_x, all_y = [], []
            is_zoomed = len(territories_to_render) < len(self.local_territories)

            # --- クロップ領域を計算 ---
            if is_zoomed:
                for terri_data in territories_to_render.values():
                    loc = terri_data.get("location", {})
                    start_x, start_z = loc.get("start", [0,0])
                    end_x, end_z = loc.get("end", [0,0])
                    px1, py1 = self._coord_to_pixel(start_x, start_z)
                    px2, py2 = self._coord_to_pixel(end_x, end_z)
                    all_x.extend([px1 * self.scale_factor, px2 * self.scale_factor])
                    all_y.extend([py1 * self.scale_factor, py2 * self.scale_factor])

            if all_x and all_y:
                padding = 30
                box = (
                    max(0, min(all_x) - padding),
                    max(0, min(all_y) - padding),
                    min(self.resized_map.width, max(all_x) + padding),
                    min(self.resized_map.height, max(all_y) + padding)
                )
                map_to_draw_on = map_to_draw_on.crop(box)

            # --- 描画処理をヘルパー関数に委譲 ---
            final_map = self._draw_trading_and_territories(
                map_to_draw_on,
                box,
                is_zoomed,
                territory_data,
                guild_color_map
            )

            # --- 最終出力 ---
            map_bytes = BytesIO()
            final_map.save(map_bytes, format='PNG')
            map_bytes.seek(0)

            jst_now = datetime.now(timezone(timedelta(hours=9)))
            formatted_time = jst_now.strftime("%Y/%m/%d %H:%M:%S")

            file = discord.File(map_bytes, filename="wynn_map.png")
            embed = discord.Embed(
                title="",
                color=discord.Color.green()
            )
            embed.set_image(url="attachment://wynn_map.png")
            embed.set_footer(text=f"Territory Map ({formatted_time}) | Minister Chikuwa")

            return file, embed

        except Exception as e:
            logger.error(f"マップ生成中にエラー: {e}", exc_info=True)
            return None, None

    def create_single_territory_image(self, territory: str, territory_data: dict, guild_color_map: dict) -> BytesIO | None:
        """指定された単一のテリトリー画像を切り出して返す"""
        logger.info(f"--- [MapRenderer] 単一テリトリー画像生成開始: {territory}")
        try:
            terri_data = self.local_territories.get(territory)
            if not terri_data or 'Location' not in terri_data:
                logger.error(f"'{territory}'にLocationデータがありません。")
                return None
            
            map_to_draw_on = self.resized_map.copy()
            box = None
            all_x, all_y = [], []
            is_zoomed = None

            self.map_on_process = self._draw_trading_and_territories(
                map_to_draw_on,
                box,
                is_zoomed,
                territory_data,
                guild_color_map
            )
            
            loc = terri_data.get("Location", {})
            
            px1, py1 = self._coord_to_pixel(*loc.get("start", [0, 0]))
            px2, py2 = self._coord_to_pixel(*loc.get("end", [0, 0]))

            px1, py1 = px1 * self.scale_factor, py1 * self.scale_factor
            px2, py2 = px2 * self.scale_factor, py2 * self.scale_factor

            # 必ず正しい順に整列
            left = min(px1, px2)
            right = max(px1, px2)
            top = min(py1, py2)
            bottom = max(py1, py2)

            padding = 50

            box = (
                max(0, left - padding),
                max(0, top - padding),
                min(self.map_on_process.width, right + padding),
                min(self.map_on_process.height, bottom + padding)
            )

            # ここでチェック
            if not (box[0] < box[2] and box[1] < box[3]):
                logger.error(f"'{territory}'の計算後の切り抜き範囲が無効です。Box: {box}")
                return None

            # ✨ 特別な装飾を描画（中心点を使って金色の円を描く）
            center_x = (px1 + px2) / 2
            center_y = (py1 + py2) / 2

            # 幅・高さをもとに円の半径を動的に設定
            territory_width = abs(px2 - px1)
            territory_height = abs(py2 - py1)

            highlight_radius = int(sqrt(territory_width ** 2 + territory_height ** 2) / 2)

            draw = ImageDraw.Draw(self.map_on_process)
            draw.ellipse(
                [(center_x - highlight_radius, center_y - highlight_radius),
                 (center_x + highlight_radius, center_y + highlight_radius)],
                outline="gold",
                width=3
            )
                
            cropped_image = self.map_on_process.crop(box)
            
            # 画像をバイトデータに変換
            map_bytes = BytesIO()
            cropped_image.save(map_bytes, format='PNG')
            map_bytes.seek(0)
            logger.info(f"--- [MapRenderer] ✅ 画像生成成功。")
            
            return map_bytes
        except Exception as e:
            logger.error(f"単一テリトリー画像の生成中にエラー: {e}")
            return None
