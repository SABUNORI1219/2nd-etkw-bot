from PIL import Image
import os
import logging
from io import BytesIO

logger = logging.getLogger(__name__)

# あなたが作成してくれた、API名とファイル名の対応表
PATTERN_MAP = {
    'base': 'b', 'STRIPE_BOTTOM': 'bs', 'STRIPE_TOP': 'ts', 'STRIPE_LEFT': 'ls',
    'STRIPE_RIGHT': 'rs', 'STRIPE_CENTER': 'cs', 'STRIPE_MIDDLE': 'ms',
    'STRIPE_DOWNRIGHT': 'drs', 'STRIPE_DOWNLEFT': 'dls', 'STRIPE_SMALL': 'ss',
    'CROSS': 'cr', 'STRAIGHT_CROSS': 'sc', 'DIAGONAL_LEFT': 'ld',
    'DIAGONAL_RIGHT_MIRROR': 'rud', 'DIAGONAL_LEFT_MIRROR': 'lud',
    'DIAGONAL_RIGHT': 'rd', 'HALF_VERTICAL_LEFT': 'vh', 'HALF_VERTICAL_RIGHT': 'vhr',
    'HALF_HORIZONTAL': 'hh', 'HALF_HORIZONTAL_MIRROR': 'hhb',
    'SQUARE_BOTTOM_LEFT': 'bl', 'SQUARE_BOTTOM_RIGHT': 'br',
    'SQUARE_TOP_LEFT': 'tl', 'SQUARE_TOP_RIGHT': 'tr', 'TRIANGLE_BOTTOM': 'bt',
    'TRIANGLE_TOP': 'tt', 'TRIANGLES_BOTTOM': 'bts', 'TRIANGLES_TOP': 'tts',
    'CIRCLE_MIDDLE': 'mc', 'RHOMBUS_MIDDLE': 'mr', 'BORDER': 'bo',
    'CURLY_BORDER': 'cbo', 'GRADIENT': 'gra', 'GRADIENT_UP': 'gru',
    'CREEPER': 'cre', 'SKULL': 'sku', 'FLOWER': 'flo', 'MOJANG': 'moj',
    'GLOBE': 'glb', 'PIGLIN': 'pig' # APIは'Piglin'を返す可能性があるため追加
}

# 色の名前をファイルで使われる小文字に変換する
# (Wynncraftのバナーで使われる16色)
COLOR_MAP = {
    'WHITE': 'white', 'ORANGE': 'orange', 'MAGENTA': 'magenta', 'LIGHT_BLUE': 'light_blue',
    'YELLOW': 'yellow', 'LIME': 'lime', 'PINK': 'pink', 'GRAY': 'gray',
    'LIGHT_GRAY': 'light_gray', 'CYAN': 'cyan', 'PURPLE': 'purple', 'BLUE': 'blue',
    'BROWN': 'brown', 'GREEN': 'green', 'RED': 'red', 'BLACK': 'black'
}

ASSETS_DIR = "assets/banners"

class BannerRenderer:
    """
    Wynncraftのギルドバナーデータを元に、画像を生成する担当者。
    """
    def create_banner_image(self, banner_data: dict) -> BytesIO | None:
        """
        バナーデータを受け取り、Pillowを使って画像を合成し、
        Discordに送信可能なバイトデータとして返す。
        """
        if not banner_data or 'base' not in banner_data:
            logger.warning("無効なバナーデータが渡されました。")
            return None

        try:
            # 1. ベースとなる色の画像パスを特定
            base_color_name = banner_data.get('base', 'WHITE').upper()
            base_color_file = COLOR_MAP.get(base_color_name, 'white')
            base_image_path = os.path.join(ASSETS_DIR, "base", f"{base_color_file}.png")
            
            # ベース画像を開く
            banner_image = Image.open(base_image_path).convert("RGBA")

            # 2. レイヤーを順番に重ねていく
            layers = banner_data.get('layers', [])
            for layer in layers:
                pattern_api_name = layer.get('pattern')
                color_api_name = layer.get('colour')

                # 対応表を使って、ファイル名用の略称と色名を取得
                pattern_abbr = PATTERN_MAP.get(pattern_api_name)
                color_file_name = COLOR_MAP.get(color_api_name)

                if not pattern_abbr or not color_file_name:
                    logger.warning(f"不明なパターンまたは色です: {pattern_api_name}, {color_api_name}")
                    continue

                # 正しいファイルパスを組み立てる
                pattern_path = os.path.join(ASSETS_DIR, "patterns", f"{color_file_name}-{pattern_abbr}.png")
                
                if os.path.exists(pattern_path):
                    pattern_image = Image.open(pattern_path).convert("RGBA")
                    # ベース画像の上にパターンを重ねる（マスクとしてパターン画像を使用）
                    banner_image.paste(pattern_image, (0, 0), pattern_image)
                else:
                    logger.warning(f"アセットファイルが見つかりません: {pattern_path}")

            # 3. 完成した画像をファイルではなく、メモリ上のバイトデータに保存
            final_buffer = BytesIO()
            banner_image.save(final_buffer, format='PNG')
            final_buffer.seek(0) # ポインタを先頭に戻す

            return final_buffer

        except FileNotFoundError as e:
            logger.error(f"バナーのベース画像が見つかりません: {e}")
            return None
        except Exception as e:
            logger.error(f"バナー生成中に予期せぬエラー: {e}")
            return None
