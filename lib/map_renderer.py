from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
import os
import logging
import json
import discord
from datetime import datetime, timezone

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

    # ▼▼▼【関数全体を、クロップと色分けに対応するように修正】▼▼▼
    def create_territory_map(self, territories_to_render: dict, guild_color_map: dict) -> tuple[discord.File | None, discord.Embed | None]:
        if not territories_to_render: return None, None
        
        try:
            map_to_draw_on = self.map_img.copy()
            
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
                    all_x.extend([px1, px2])
                    all_y.extend([py1, py2])
                
                if all_x and all_y:
                    padding = 200 # 切り取る領域の周囲の余白
                    box = (max(0, min(all_x) - padding), 
                           max(0, min(all_y) - padding),
                           min(self.map_img.width, max(all_x) + padding),
                           min(self.map_img.height, max(all_y) + padding))
                    map_to_draw_on = map_to_draw_on.crop(box)

            # --- 描画処理 ---
            overlay = Image.new("RGBA", map_to_draw_on.size, (0,0,0,0))
            overlay_draw = ImageDraw.Draw(overlay)
            draw = ImageDraw.Draw(map_to_draw_on)

            for name, info in territories_to_render.items():
                if 'location' not in info or 'guild' not in info: continue
                
                prefix = info["guild"]["prefix"]
                color_hex = guild_color_map.get(prefix, "#FFFFFF")
                color_rgb = self._hex_to_rgb(color_hex)
                
                start_x, start_z = info["location"]["start"]
                end_x, end_z = info["location"]["end"]
                px1, py1 = self._coord_to_pixel(start_x, start_z)
                px2, py2 = self._coord_to_pixel(end_x, end_z)
                
                # クロップ後の相対座標に変換
                if is_zoomed:
                    px1, px2 = px1 - box[0], px2 - box[0]
                    py1, py2 = py1 - box[1], py2 - box[1]

                x_min, x_max = sorted([px1, px2])
                y_min, y_max = sorted([py1, py2])
                
                overlay_draw.rectangle([x_min, y_min, x_max, y_max], fill=(*color_rgb, 64))
                draw.rectangle([x_min, y_min, x_max, y_max], outline=color_rgb, width=4)
                text_x, text_y = (x_min + x_max) / 2, (y_min + y_max) / 2
                draw.text((text_x, text_y), prefix, font=self.font, fill=color_rgb, anchor="mm", stroke_width=2, stroke_fill="black")

            final_map = Image.alpha_composite(map_to_draw_on, overlay)

            # --- 最終出力 ---
            map_bytes = BytesIO()
            final_map.save(map_bytes, format='PNG')
            map_bytes.seek(0)
            
            file = discord.File(map_bytes, filename="wynn_map.png")
            embed = discord.Embed(title="Wynncraft Territory Map", color=discord.Color.green())
            embed.set_image(url="attachment://wynn_map.png")
            
            return file, embed

        except Exception as e:
            logger.error(f"マップ生成中にエラー: {e}", exc_info=True)
            return None, None
