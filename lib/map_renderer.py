from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
import discord
import os
import logging
import json

logger = logging.getLogger(__name__)

# アセットとフォントのパスを定義
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS_PATH = os.path.join(project_root, "assets", "map")
FONT_PATH = os.path.join(project_root, "assets", "fonts", "NotoSansJP-Bold.ttf")

class MapRenderer:
    def __init__(self):
        try:
            self.map_img = Image.open(os.path.join(ASSETS_PATH, "main-map.png")).convert("RGBA")
            with open(os.path.join(ASSETS_PATH, "territories.json"), "r") as f:
                self.local_territories = json.load(f)
            self.font = ImageFont.truetype(FONT_PATH, 40)
        except FileNotFoundError as e:
            logger.error(f"マップ生成に必要なアセットが見つかりません: {e}")
            raise

    def _coord_to_pixel(self, x, z):
        """ゲーム内座標を画像上のピクセル座標に変換する"""
        return x + 2383, z + 6572

    def create_territory_map(self, territory_data: dict) -> tuple[BytesIO | None, discord.Embed | None]:
        """テリトリーデータを受け取り、地図画像とEmbedを生成する"""
        if not territory_data: return None, None
        
        try:
            map_copy = self.map_img.copy()
            overlay = Image.new("RGBA", map_copy.size)
            overlay_draw = ImageDraw.Draw(overlay)
            draw = ImageDraw.Draw(map_copy)

            for name, info in territory_data.items():
                if 'location' not in info: continue
                
                # テリトリー領域を描画
                start_x, start_z = info["location"]["start"]
                end_x, end_z = info["location"]["end"]
                px1, py1 = self._coord_to_pixel(start_x, start_z)
                px2, py2 = self._coord_to_pixel(end_x, end_z)

                # ▼▼▼【エラー修正箇所】座標の大小を揃える▼▼▼
                # x座標の小さい方をx_min、大きい方をx_maxとする
                x_min, x_max = sorted([px1, px2])
                # y座標の小さい方をy_min、大きい方をy_maxとする
                y_min, y_max = sorted([py1, py2])
                
                # 半透明のオーバーレイを描画
                overlay_draw.rectangle([px1, py1, px2, py2], fill=(128, 128, 128, 64))
                # 枠線を描画
                draw.rectangle([px1, py1, px2, py2], outline="white", width=8)

                # ギルドのプレフィックスを描画
                prefix = info["guild"]["prefix"]
                text_x = (px1 + px2) / 2
                text_y = (py1 + py2) / 2
                draw.text((text_x, text_y), prefix, font=self.font, fill="white", anchor="mm", stroke_width=2, stroke_fill="black")

            # オーバーレイと地図を合成
            final_map = Image.alpha_composite(map_copy, overlay)

            # 画像をバイトデータに変換
            map_bytes = BytesIO()
            final_map.save(map_bytes, format='PNG', optimize=True)
            map_bytes.seek(0)
            
            file = discord.File(map_bytes, filename="wynn_map.png")
            embed = discord.Embed(
                title="Wynncraft Territory Map",
                description="現在のテリトリー所有状況です。",
                color=discord.Color.green()
            )
            embed.set_image(url="attachment://wynn_map.png")
            embed.set_footer(text=f"Generated at {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
            
            return file, embed

        except Exception as e:
            logger.error(f"マップ生成中にエラー: {e}", exc_info=True)
            return None, None
