from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
import os
import logging
import json
import discord # discord.File と discord.Embed を使うためにインポート
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
        """ゲーム内座標を画像上のピクセル座標に変換する"""
        return x + 2383, z + 6572

    def _hex_to_rgb(self, hex_color: str) -> tuple:
        """HEXカラーコードをRGBタプルに変換する"""
        hex_color = hex_color.lstrip('#')
        try:
            return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        except ValueError:
            return (255, 255, 255) # 変換に失敗した場合は白を返す

    def create_territory_map(self, territory_data: dict, guild_color_map: dict) -> tuple[discord.File | None, discord.Embed | None]:
        """テリトリーデータとギルドカラーマップを受け取り、地図画像とEmbedを生成する"""
        if not territory_data: return None, None
        
        try:
            map_copy = self.map_img.copy()
            overlay = Image.new("RGBA", map_copy.size)
            overlay_draw = ImageDraw.Draw(overlay)
            draw = ImageDraw.Draw(map_copy)

            # --- 1. コネクション（交易路）の線を描画 ---
            for name, data in self.local_territories.items():
                if "Trading Routes" not in data or "Location" not in data: continue
                
                try:
                    x1 = (data["Location"]["start"][0] + data["Location"]["end"][0]) // 2
                    z1 = (data["Location"]["start"][1] + data["Location"]["end"][1]) // 2
                    px1, py1 = self._coord_to_pixel(x1, z1)

                    for destination_name in data["Trading Routes"]:
                        dest_data = self.local_territories.get(destination_name)
                        if not dest_data or "Location" not in dest_data: continue
                        
                        x2 = (dest_data["Location"]["start"][0] + dest_data["Location"]["end"][0]) // 2
                        z2 = (dest_data["Location"]["start"][1] + dest_data["Location"]["end"][1]) // 2
                        px2, py2 = self._coord_to_pixel(x2, z2)
                        
                        draw.line([(px1, py1), (px2, py2)], fill=(10, 10, 10, 128), width=5)
                except KeyError:
                    continue

            # --- 2. 所有されているテリトリーをギルドの色で描画 ---
            for name, info in territory_data.items():
                if 'location' not in info or 'guild' not in info: continue
                
                prefix = info["guild"]["prefix"]
                # ギルドカラーマップから色を取得、なければ白
                color_hex = guild_color_map.get(prefix, "#FFFFFF")
                color_rgb = self._hex_to_rgb(color_hex)
                
                start_x, start_z = info["location"]["start"]
                end_x, end_z = info["location"]["end"]
                px1, py1 = self._coord_to_pixel(start_x, start_z)
                px2, py2 = self._coord_to_pixel(end_x, end_z)
                x_min, x_max = sorted([px1, px2])
                y_min, y_max = sorted([py1, py2])

                # 半透明のオーバーレイを描画
                overlay_draw.rectangle([x_min, y_min, x_max, y_max], fill=(*color_rgb, 64))
                # 枠線を描画
                draw.rectangle([x_min, y_min, x_max, y_max], outline=color_rgb, width=8)
                # ギルドのプレフィックスを描画
                text_x, text_y = (x_min + x_max) / 2, (y_min + y_max) / 2
                draw.text((text_x, text_y), prefix, font=self.font, fill=color_rgb, anchor="mm", stroke_width=4, stroke_fill="black")

            # オーバーレイと地図を合成
            final_map = Image.alpha_composite(map_copy, overlay)

            # 画像をバイトデータに変換
            map_bytes = BytesIO()
            final_map.save(map_bytes, format='PNG', optimize=True)
            map_bytes.seek(0)
            
            file = discord.File(map_bytes, filename="wynn_map.png")
            embed = discord.Embed(
                title="Wynncraft Territory Map",
                color=discord.Color.green()
            )
            embed.set_image(url="attachment://wynn_map.png")
            embed.set_footer(text=f"Generated at {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
            
            return file, embed

        except Exception as e:
            logger.error(f"マップ生成中にエラー: {e}", exc_info=True)
            return None, None
