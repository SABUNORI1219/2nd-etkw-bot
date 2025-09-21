from PIL import Image
import os
import logging
from io import BytesIO
import numpy as np

logger = logging.getLogger(__name__)

PATTERN_MAP = {
    'BASE': 'background', 'STRIPE_BOTTOM': 'bs', 'STRIPE_TOP': 'ts', 'STRIPE_LEFT': 'ls',
    'STRIPE_RIGHT': 'rs', 'STRIPE_CENTER': 'cs', 'STRIPE_MIDDLE': 'ms',
    'STRIPE_DOWNRIGHT': 'drs', 'STRIPE_DOWNLEFT': 'dls', 'STRIPE_SMALL': 'ss',
    'CROSS': 'cr', 'STRAIGHT_CROSS': 'sc', 'DIAGONAL_LEFT': 'ld',
    'DIAGONAL_RIGHT_MIRROR': 'rud', 'DIAGONAL_LEFT_MIRROR': 'lud',
    'DIAGONAL_RIGHT': 'rd', 'HALF_VERTICAL': 'vh', 'HALF_VERTICAL_RIGHT': 'vhr',
    'HALF_HORIZONTAL': 'hh', 'HALF_HORIZONTAL_MIRROR': 'hhb',
    'SQUARE_BOTTOM_LEFT': 'bl', 'SQUARE_BOTTOM_RIGHT': 'br',
    'SQUARE_TOP_LEFT': 'tl', 'SQUARE_TOP_RIGHT': 'tr', 'TRIANGLE_BOTTOM': 'bt',
    'TRIANGLE_TOP': 'tt', 'TRIANGLES_BOTTOM': 'bts', 'TRIANGLES_TOP': 'tts',
    'CIRCLE_MIDDLE': 'mc', 'RHOMBUS_MIDDLE': 'mr', 'BORDER': 'bo',
    'CURLY_BORDER': 'cbo', 'BRICKS': 'bri', 'GRADIENT': 'gra', 'GRADIENT_UP': 'gru',
    'CREEPER': 'cre', 'SKULL': 'sku', 'FLOWER': 'flo', 'MOJANG': 'moj',
    'GLOBE': 'glb', 'PIGLIN': 'pig'
}

COLOR_MAP = {
    'WHITE': 'white', 'ORANGE': 'orange', 'MAGENTA': 'magenta', 'LIGHT_BLUE': 'light_blue',
    'YELLOW': 'yellow', 'LIME': 'lime', 'PINK': 'pink', 'GRAY': 'gray',
    'SILVER': 'light_gray', 'CYAN': 'cyan', 'PURPLE': 'purple', 'BLUE': 'blue',
    'BROWN': 'brown', 'GREEN': 'green', 'RED': 'red', 'BLACK': 'black'
}

ASSETS_DIR = "assets/banners"

def remove_border_lines(img, line_colors, tolerance=25, alpha_value=0):
    arr = np.array(img)
    mask = np.zeros(arr.shape[:2], dtype=bool)
    for color in line_colors:
        r, g, b = color
        diff = np.abs(arr[..., :3] - [r, g, b])
        mask |= (diff < tolerance).all(axis=-1)
    arr[..., 3][mask] = alpha_value
    return Image.fromarray(arr, 'RGBA')

class BannerRenderer:
    def create_banner_image(self, banner_data: dict) -> BytesIO | None:
        if not banner_data or not isinstance(banner_data, dict) or 'base' not in banner_data:
            # 白色ベース画像パス
            base_image_path = os.path.join(ASSETS_DIR, "white-background.png")
            try:
                banner_image = Image.open(base_image_path).convert("RGBA")
                scale_factor = 5
                original_width, original_height = banner_image.size
                new_size = (original_width * scale_factor, original_height * scale_factor)
                resized_image = banner_image.resize(new_size, resample=Image.Resampling.NEAREST)
                final_buffer = BytesIO()
                resized_image.save(final_buffer, format='PNG')
                final_buffer.seek(0)
                return final_buffer
            except Exception as e:
                logger.error(f"白ベース画像生成失敗: {e}")
                return None

        try:
            base_color = COLOR_MAP.get(banner_data.get('base', 'WHITE').upper(), 'white')
            base_abbr = PATTERN_MAP.get('BASE', 'b')
            base_image_path = os.path.join(ASSETS_DIR, f"{base_color}-{base_abbr}.png")
            banner_image = Image.open(base_image_path).convert("RGBA")

            # 枠線色リスト (白は除外)
            border_colors = [
                (60, 40, 30),   # dark brown
                (110, 80, 50),  # light brown
                (0, 0, 0),      # black
                # (255, 255, 255) # white ← 除外
            ]
            # 枠線消去処理を適用するパターン
            border_remove_patterns = {'cr', 'bo', 'sc', 'ld', 'rd', 'rud', 'lud'} # 十字・縁など

            for layer in banner_data.get('layers', []):
                pattern_abbr = PATTERN_MAP.get(layer.get('pattern'))
                color_name = COLOR_MAP.get(layer.get('colour'))

                if not pattern_abbr or not color_name:
                    logger.warning(f"不明なパターン/色: {layer.get('pattern')}, {layer.get('colour')}")
                    continue

                pattern_path = os.path.join(ASSETS_DIR, f"{color_name}-{pattern_abbr}.png")
                if os.path.exists(pattern_path):
                    pattern_image_src = Image.open(pattern_path)
                    try:
                        pattern_image = pattern_image_src.convert("RGBA")
                        if pattern_abbr in border_remove_patterns:
                            pattern_image_src.close()
                            pattern_image_src = pattern_image
                            pattern_image = remove_border_lines(pattern_image, border_colors, tolerance=25, alpha_value=0)
                        if banner_image.size == pattern_image.size:
                            banner_image = Image.alpha_composite(banner_image, pattern_image)
                        else:
                            banner_image.paste(pattern_image, (0, 0), pattern_image)
                    finally:
                        pattern_image_src.close()
                else:
                    logger.warning(f"アセットファイルが見つかりません: {pattern_path}")
    
            scale_factor = 5
            original_width, original_height = banner_image.size
            new_size = (original_width * scale_factor, original_height * scale_factor)
            resized_image = banner_image.resize(new_size, resample=Image.Resampling.NEAREST)

            final_buffer = BytesIO()
            resized_image.save(final_buffer, format='PNG')
            final_buffer.seek(0)
            return final_buffer

        except Exception as e:
            logger.error(f"バナー生成中に予期せぬエラー: {e}")
            return None
