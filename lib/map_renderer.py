from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
import os
import logging
import json
import discord
from datetime import datetime, timezone, timedelta

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

    def _draw_overlays(self, map_to_draw_on: Image.Image, territory_data: dict, guild_color_map: dict, scale_factor: float, crop_box: tuple | None) -> Image.Image:
        """与えられた画像の上に、コネクション線とテリトリーを描画する共通の専門家"""
        overlay = Image.new("RGBA", map_to_draw_on.size, (0,0,0,0))
        overlay_draw = ImageDraw.Draw(overlay)
        draw = ImageDraw.Draw(map_to_draw_on)
        offset_x, offset_y = (crop_box[0], crop_box[1]) if crop_box else (0, 0)

        # --- コネクション線の描画 ---
        for data in self.local_territories.values():
            if "Trading Routes" not in data or "Location" not in data: continue
            try:
                x1 = (data["Location"]["start"][0] + data["Location"]["end"][0]) // 2
                z1 = (data["Location"]["start"][1] + data["Location"]["end"][1]) // 2
                px1_orig, py1_orig = self._coord_to_pixel(x1, z1)
                spx1, spy1 = px1_orig * self.scale_factor, py1_orig * self.scale_factor
                for destination_name in data["Trading Routes"]:
                    dest_data = self.local_territories.get(destination_name)
                    if not dest_data or "Location" not in dest_data: continue
                    x2 = (dest_data["Location"]["start"][0] + dest_data["Location"]["end"][0]) // 2
                    z2 = (dest_data["Location"]["start"][1] + dest_data["Location"]["end"][1]) // 2
                    px2_orig, py2_orig = self._coord_to_pixel(x2, z2)
                    spx2, spy2 = px2_orig * self.scale_factor, py2_orig * self.scale_factor
                    
                    final_px1, final_py1 = spx1 - offset_x, spy1 - offset_y
                    final_px2, final_py2 = spx2 - offset_x, spy2 - offset_y
                    
                    if (final_px1 > 0 or final_px2 > 0) and (final_py1 > 0 or final_py2 > 0) and \
                       (final_px1 < map_to_draw_on.width or final_px2 < map_to_draw_on.width) and \
                       (final_py1 < map_to_draw_on.height or final_py2 < map_to_draw_on.height):
                        draw.line([(final_px1, final_py1), (final_px2, final_py2)], fill=(10, 10, 10, 128), width=1)
            except KeyError:
                continue
        
        # --- テリトリーの描画 ---
        scaled_font_size = max(12, int(self.font.size * self.scale_factor))
        try:
            scaled_font = ImageFont.truetype(FONT_PATH, scaled_font_size)
        except IOError:
            scaled_font = ImageFont.load_default()
                
        for info in territory_data.items():
            if 'location' not in info or 'guild' not in info: continue
            
            px1_orig, py1_orig = self._coord_to_pixel(*info["location"]["start"])
            px2_orig, py2_orig = self._coord_to_pixel(*info["location"]["end"])
            spx1, spy1 = px1_orig * self.scale_factor, py1_orig * self.scale_factor
            spx2, spy2 = px2_orig * self.scale_factor, py2_orig * self.scale_factor

            final_px1, final_py1 = spx1 - offset_x, spy1 - offset_y
            final_px2, final_py2 = spx2 - offset_x, spy2 - offset_y
            
            x_min, x_max = sorted([final_px1, final_px2])
            y_min, y_max = sorted([final_py1, final_py2])

            if x_max > 0 and y_max > 0 and x_min < map_to_draw_on.width and y_min < map_to_draw_on.height:
                prefix = info["guild"]["prefix"]
                color_hex = guild_color_map.get(prefix, "#FFFFFF")
                color_rgb = self._hex_to_rgb(color_hex)
                
                overlay_draw.rectangle([x_min, y_min, x_max, y_max], fill=(*color_rgb, 64))
                draw.rectangle([x_min, y_min, x_max, y_max], outline=color_rgb, width=2)
                draw.text(((x_min + x_max)/2, (y_min + y_max)/2), prefix, font=scaled_font, fill=color_rgb, anchor="mm", stroke_width=2, stroke_fill="black")
                
        return Image.alpha_composite(map_to_draw_on, overlay)

    def create_territory_map(self, territory_data: dict, guild: str, guild_color_map: dict) -> tuple[discord.File | None, discord.Embed | None]:
        if not territory_data: return None, None
        try:
            map_to_draw_on = self.resized_map
            crop_box = None

            if guild:
                all_x, all_y = [], []
                target_territories = [v for v in territory_data.values() if v.get('guild',{}).get('prefix','').upper() == guild.upper()]
                if not target_territories:
                    pass
                else:   
                    for territory_data in target_territories:
                        loc = territory_data.get("location", {})
                        px1, py1 = self._coord_to_pixel(*loc.get("start", [0,0]))
                        px2, py2 = self._coord_to_pixel(*loc.get("end", [0,0]))
                        all_x.extend([px1 * self.scale_factor, px2 * self.scale_factor])
                        all_y.extend([py1 * self.scale_factor, py2 * self.scale_factor])

                    padding = 30
                    box = (max(0, min(all_x) - padding), max(0, min(all_y) - padding),
                       min(self.resized_map.width, max(all_x) + padding), min(self.resized_map.height, max(all_y) + padding))
                    if box[0] < box[2] and box[1] < box[3]:
                        map_to_draw_on = self.resized_map.crop(box)
                        crop_box = box
                    else:
                        crop_box = None

            # --- 最終出力 ---
            final_map = self._draw_overlays(map_to_draw_on, territory_data, guild_color_map, self.scale_factor, crop_box)
            map_bytes = BytesIO()
            final_map.save(map_bytes, format='PNG')
            map_bytes.seek(0)

            jst_tz = timezone(timedelta(hours=9))
            jst_now = datetime.now(jst_tz)

            # "年/月/日 時:分:秒" の形式に変換
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

    def create_single_territory_image(self, territory: str) -> BytesIO | None:
        """指定された単一のテリトリー画像を切り出して返す"""
        logger.info(f"--- [MapRenderer] 単一テリトリー画像生成開始: {territory}")
        try:
            terri_data = self.local_territories.get(territory)
            if not terri_data or 'Location' not in terri_data: return None
            
            # クロップ範囲の計算
            loc = terri_data.get("Location", {})
            px1, py1 = self._coord_to_pixel(*loc.get("start", [0,0]))
            px2, py2 = self._coord_to_pixel(*loc.get("end", [0,0]))
            padding = 150
            box = (min(px1,px2)-padding, min(py1,py2)-padding, max(px1,px2)+padding, max(py1,py2)+padding)
            if not (box[0] < box[2] and box[1] < box[3]): return None
            
            # 全体地図をクロップ
            cropped_map = self.map_img.crop(box)
            
            # クロップした地図の上に、共通描画関数で領地情報を描画
            final_map = self._draw_overlays(cropped_map, territory_data, guild_color_map, 1.0, box)
            
            map_bytes = BytesIO(); final_map.save(map_bytes, 'PNG'); map_bytes.seek(0)
            return map_bytes
        except Exception as e:
            logger.error(f"単一テリトリー画像の生成中にエラー: {e}", exc_info=True)
            return None
