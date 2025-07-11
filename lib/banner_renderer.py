from PIL import Image
import os
import logging

logger = logging.getLogger(__name__)

ASSETS_DIR = "assets/banners" # 部品画像が保存されているフォルダ

class BannerRenderer:
    """
    Wynncraftのギルドバナーデータを元に、画像を生成する担当者。
    """
    def __init__(self):
        # 部品フォルダの存在を確認
        if not os.path.exists(ASSETS_DIR):
            logger.error(f"アセットフォルダ '{ASSETS_DIR}' が見つかりません。")
            raise FileNotFoundError(f"Banner assets directory not found at '{ASSETS_DIR}'")

    def create_banner_image(self, banner_data: dict):
        """
        バナーデータを受け取り、Pillowを使って画像を合成する。
        """
        if not banner_data or 'base' not in banner_data:
            logger.warning("無効なバナーデータが渡されました。")
            return None

        try:
            # 1. ベースとなる色の画像を読み込む
            base_color = banner_data.get('base', 'WHITE').upper()
            base_image_path = os.path.join(ASSETS_DIR, "base", f"{base_color}.png")
            banner = Image.open(base_image_path).convert("RGBA")

            # 2. レイヤーを順番に重ねていく
            layers = banner_data.get('layers', [])
            for layer in layers:
                pattern_name = layer.get('pattern', '').upper()
                color_name = layer.get('colour', 'WHITE').upper()

                pattern_path = os.path.join(ASSETS_DIR, "patterns", f"{pattern_name}.png")
                
                # パターン画像が存在する場合のみ処理
                if os.path.exists(pattern_path):
                    pattern_image = Image.open(pattern_path).convert("RGBA")
                    
                    # パターンの色を変更する（高度な処理）
                    # ここでは、簡単のため、色付きのパターン画像を直接読み込むことを想定
                    # TODO: 色を動的に変更するロジックを後で追加
                    
                    # ベース画像の上にパターンを重ねる
                    banner.paste(pattern_image, (0, 0), pattern_image)

            return banner

        except FileNotFoundError as e:
            logger.error(f"バナーの部品画像が見つかりません: {e}")
            return None
        except Exception as e:
            logger.error(f"バナー生成中に予期せぬエラーが発生しました: {e}")
            return None
