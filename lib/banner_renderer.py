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
        logger.info("--- [Banner] バナー生成プロセスを開始します。")

        if not banner_data or 'base' not in banner_data:
            logger.warning("--- [Banner] 警告: 無効なバナーデータ、または 'base' キーが存在しません。")
            return None

        try:
            # 1. ベース画像を特定
            base_color_name = banner_data.get('base', 'WHITE').upper()
            base_color_file = COLOR_MAP.get(base_color_name)
            if not base_color_file:
                logger.error(f"--- [Banner] エラー: 不明なベース色名です: {base_color_name}")
                return None
            
            base_abbr = PATTERN_MAP.get('BASE', 'b')
            base_image_path = os.path.join(ASSETS_DIR, f"{base_color_file}-{base_abbr}.png")
            
            logger.info(f"--- [Banner] ステップ1: ベース画像を読み込みます → {base_image_path}")
            if not os.path.exists(base_image_path):
                logger.error(f"--- [Banner] エラー: ベース画像ファイルが見つかりません！ パス: {base_image_path}")
                return None
            
            banner_image = Image.open(base_image_path).convert("RGBA")

            # 2. レイヤーを重ねる
            layers = banner_data.get('layers', [])
            logger.info(f"--- [Banner] ステップ2: {len(layers)}層のレイヤー処理を開始します。")
            for i, layer in enumerate(layers):
                pattern_api_name = layer.get('pattern')
                color_api_name = layer.get('colour')

                pattern_abbr = PATTERN_MAP.get(pattern_api_name)
                color_file_name = COLOR_MAP.get(color_api_name)

                if not pattern_abbr or not color_file_name:
                    logger.warning(f"--- [Banner] レイヤー{i+1}: 不明なパターン/色のためスキップします: {pattern_api_name}, {color_api_name}")
                    continue

                pattern_path = os.path.join(ASSETS_DIR, f"{color_file_name}-{pattern_abbr}.png")
                logger.info(f"--- [Banner] レイヤー{i+1}: 模様画像を読み込みます → {pattern_path}")
                
                if os.path.exists(pattern_path):
                    pattern_image = Image.open(pattern_path).convert("RGBA")
                    banner_image.paste(pattern_image, (0, 0), pattern_image)
                    pattern_image.close()
                else:
                    logger.error(f"--- [Banner] エラー: レイヤー{i+1}のアセットファイルが見つかりません！ パス: {pattern_path}")
                    # 1つでもファイルが見つからない場合は、不完全なバナーになるため生成を中止
                    return None

            # 3. 完成画像をバイトデータとして返す
            final_buffer = BytesIO()
            banner_image.save(final_buffer, format='PNG')
            final_buffer.seek(0)
            logger.info("--- [Banner] ✅ バナー画像の生成に成功しました。")
            return final_buffer

        except Exception as e:
            logger.error(f"--- [Banner] 予期せぬエラーでバナー生成に失敗: {e}", exc_info=True)
            return None
