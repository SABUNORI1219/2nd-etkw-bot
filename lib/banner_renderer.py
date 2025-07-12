from PIL import Image
import os
import logging
from io import BytesIO

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
    'CURLY_BORDER': 'cbo', 'GRADIENT': 'gra', 'GRADIENT_UP': 'gru',
    'CREEPER': 'cre', 'SKULL': 'sku', 'FLOWER': 'flo', 'MOJANG': 'moj',
    'GLOBE': 'glb', 'PIGLIN': 'pig'
}

COLOR_MAP = {
    'WHITE': 'white', 'ORANGE': 'orange', 'MAGENTA': 'magenta', 'LIGHT_BLUE': 'light_blue',
    'YELLOW': 'yellow', 'LIME': 'lime', 'PINK': 'pink', 'GRAY': 'gray',
    'LIGHT_GRAY': 'light_gray', 'CYAN': 'cyan', 'PURPLE': 'purple', 'BLUE': 'blue',
    'BROWN': 'brown', 'GREEN': 'green', 'RED': 'red', 'BLACK': 'black'
}

ASSETS_DIR = "assets/banners" # フォルダ構造の変更に合わせて修正

class BannerRenderer:
    def create_banner_image(self, banner_data: dict) -> BytesIO | None:
        if not banner_data or 'base' not in banner_data:
            return None

        try:
            # 1. ベース画像を特定
            base_color = COLOR_MAP.get(banner_data.get('base', 'WHITE').upper(), 'white')
            base_abbr = PATTERN_MAP.get('BASE', 'b')
            base_image_path = os.path.join(ASSETS_DIR, f"{base_color}-{base_abbr}.png")
            
            banner_image = Image.open(base_image_path).convert("RGBA")

            # 2. レイヤーを重ねる
            for layer in banner_data.get('layers', []):
                pattern_abbr = PATTERN_MAP.get(layer.get('pattern'))
                color_name = COLOR_MAP.get(layer.get('colour'))

                if not pattern_abbr or not color_name:
                    logger.warning(f"不明なパターン/色: {layer.get('pattern')}, {layer.get('colour')}")
                    continue

                pattern_path = os.path.join(ASSETS_DIR, f"{color_name}-{pattern_abbr}.png")
                
                if os.path.exists(pattern_path):
                    pattern_image = Image.open(pattern_path).convert("RGBA")
                    banner_image.paste(pattern_image, (0, 0), pattern_image)
                else:
                    logger.warning(f"アセットファイルが見つかりません: {pattern_path}")

            # ▼▼▼【画像の拡大処理を再調整】▼▼▼
            scale_factor = 5  # 拡大率（この数字を大きくすると、画像も大きくなります）

            original_width, original_height = banner_image.size
            new_size = (original_width * scale_factor, original_height * scale_factor)

            # NEARESTフィルタを使って、ピクセル数をそのまま拡大
            resized_image = banner_image.resize(new_size, resample=Image.Resampling.NEAREST)

            # 拡大後のサイズをログに出力
            logger.info(f"--- [Banner] 画像を {scale_factor} 倍に拡大しました。新しいサイズ: {resized_image.size}")

            # 拡大した画像をバイトデータとして返す
            final_buffer = BytesIO()
            resized_image.save(final_buffer, format='PNG')
            final_buffer.seek(0)
            logger.info("--- [Banner] ✅ バナー画像の生成と拡大に成功しました。")
            return final_buffer
            # ▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲

        except Exception as e:
            logger.error(f"バナー生成中に予期せぬエラー: {e}")
            return None
