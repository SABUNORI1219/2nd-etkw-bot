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
            original_w, original_h = self.original_map.size
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

    def create_territory_map(self, territory_data: dict, territories_to_render: dict, guild_color_map: dict) -> tuple[discord.File | None, discord.Embed | None]:
        if not territories_to_render: return None, None
        
        try:
            map_to_draw_on = self.resized_map.copy()
            box = None
            
            # --- クロップ処理 ---
            all_x = []
            all_y = []
            is_zoomed = len(territories_to_render) < len(self.local_territories)

            if is_zoomed:
                for terri_data in territories_to_render.values():
                    loc = terri_data.get("location", {})
                    start_x, start_z = loc.get("start", [0,0])
                    end_x, end_z = loc.get("end", [0,0])
                    px1, py1 = self._coord_to_pixel(start_x, start_z)
                    px2, py2 = self._coord_to_pixel(end_x, end_z)
                    all_x.extend([px1 * scale_factor, px2 * scale_factor])
                    all_y.extend([py1 * scale_factor, py2 * scale_factor])
                
                if all_x and all_y:
                    padding = 200 # 切り取る領域の周囲の余白
                    box = (max(0, min(all_x) - padding), 
                           max(0, min(all_y) - padding),
                           min(self.resized_map.width, max(all_x) + padding),
                           min(self.resized_map.height, max(all_y) + padding))
                    map_to_draw_on = map_to_draw_on.crop(box)

            # --- 描画処理 ---
            overlay = Image.new("RGBA", map_to_draw_on.size, (0,0,0,0))
            overlay_draw = ImageDraw.Draw(overlay)
            draw = ImageDraw.Draw(map_to_draw_on)

            # 1. 全ての交易路を地図の裏側に薄く描画する
            for name, data in self.local_territories.items():
                if "Trading Routes" not in data or "Location" not in data: continue
                
                try:
                    # 出発点の中心座標を計算
                    x1 = (data["Location"]["start"][0] + data["Location"]["end"][0]) // 2
                    z1 = (data["Location"]["start"][1] + data["Location"]["end"][1]) // 2
                    px1, py1 = self._coord_to_pixel(x1, z1)
                    scaled_px1, scaled_py1 = px1 * self.scale_factor, py1 * self.scale_factor

                    for destination_name in data["Trading Routes"]:
                        dest_data = self.local_territories.get(destination_name)
                        if not dest_data or "Location" not in dest_data: continue
                        
                        # 到着点の中心座標を計算
                        x2 = (dest_data["Location"]["start"][0] + dest_data["Location"]["end"][0]) // 2
                        z2 = (dest_data["Location"]["start"][1] + dest_data["Location"]["end"][1]) // 2
                        px2, py2 = self._coord_to_pixel(x2, z2)
                        scaled_px2, scaled_py2 = px2 * self.scale_factor, py2 * self.scale_factor
                        
                        # クロップ後の相対座標に変換
                        if is_zoomed and box:
                            px1_rel, px2_rel = scaled_px1 - box[:2][0], scaled_px2 - box[:2][0]
                            py1_rel, py2_rel = scaled_py1 - box[:2][1], scaled_py2 - box[:2][1]
                            draw.line([(px1_rel, py1_rel), (px2_rel, py2_rel)], fill=(10, 10, 10, 128), width=3)
                        else:
                            draw.line([(px1, py1), (px2, py2)], fill=(10, 10, 10, 128), width=3)
                except KeyError:
                    continue

            # --- 2. 全てのテリトリーを描画 ---
            for name, info in territory_data.items():
                if 'location' not in info or 'guild' not in info: continue
                
                px1, py1 = self._coord_to_pixel(*info["location"]["start"])
                px2, py2 = self._coord_to_pixel(*info["location"]["end"])
                scaled_px1, scaled_py1 = px1 * self.scale_factor, py1 * self.scale_factor
                scaled_px2, scaled_py2 = px2 * self.scale_factor, py2 * self.scale_factor
                
                # クロップ後の相対座標に変換
                if is_zoomed and box:
                    px1_rel, px2_rel = scaled_px1 - box[:2][0], scaled_px2 - box[:2][0]
                    py1_rel, py2_rel = scaled_py1 - box[:2][1], scaled_py2 - box[:2][1]
                else:
                    px1_rel, py1_rel, px2_rel, py2_rel = scaled_px1, scaled_py1, scaled_px2, scaled_py2
                
                x_min, x_max = sorted([px1_rel, px2_rel])
                y_min, y_max = sorted([py1_rel, py2_rel])

                # 描画範囲がクロップ後の画像内に収まっているかチェック
                if x_max > 0 and y_max > 0 and x_min < map_to_draw_on.width and y_min < map_to_draw_on.height:
                    prefix = info["guild"]["prefix"]
                    color_hex = guild_color_map.get(prefix, "#FFFFFF")
                    color_rgb = self._hex_to_rgb(color_hex)

                    overlay_draw.rectangle([x_min, y_min, x_max, y_max], fill=(*color_rgb, 64))
                    draw.rectangle([x_min, y_min, x_max, y_max], outline=color_rgb, width=4)
                    draw.text(((x_min + x_max)/2, (y_min + y_max)/2), prefix, font=self.font, fill=color_rgb, anchor="mm", stroke_width=2, stroke_fill="black")

            final_map = Image.alpha_composite(map_to_draw_on, overlay)

            # --- 最終出力 ---
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
