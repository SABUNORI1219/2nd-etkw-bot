# lib/utils.py
import json
import logging

logger = logging.getLogger(__name__)

def load_json_from_file(filepath: str) -> dict | list | None:
    """JSONファイルを安全に読み込む"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        # ファイルが存在しないのは、まだキャッシュが作られていないだけなのでエラーではない
        return None
    except Exception as e:
        logger.error(f"ファイル'{filepath}'の読み込みに失敗: {e}")
        return None

def save_json_to_file(filepath: str, data: dict | list):
    """データをJSONファイルに安全に書き込む"""
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        return True
    except Exception as e:
        logger.error(f"ファイル'{filepath}'への書き込みに失敗: {e}")
        return False
