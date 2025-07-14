import json
import os
from datetime import datetime, timedelta
import logging
from .utils import load_json_from_file, save_json_to_file # ⬅️ 新しい便利関数をインポート

logger = logging.getLogger(__name__)

CACHE_DIR = "cache" # キャッシュファイルを保存するフォルダ名
CACHE_EXPIRATION_MINUTES = 1 # キャッシュの有効期間（分）

class CacheHandler:
    def __init__(self):
        if not os.path.exists(CACHE_DIR):
            os.makedirs(CACHE_DIR)

    def _get_cache_path(self, key: str) -> str:
        safe_key = key.replace("/", "_").replace("\\", "_")
        return os.path.join(CACHE_DIR, f"{safe_key}.json")

    def get_cache(self, key: str, ignore_freshness: bool = False) -> dict | list | None:
        path = self._get_cache_path(key)
        
        # ▼▼▼【修正点】ファイルの読み込みを便利関数に任せる▼▼▼
        cached_data = load_json_from_file(path)
        if not cached_data:
            return None
        # ▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲

        if not ignore_freshness:
            try:
                cache_time = datetime.fromisoformat(cached_data['timestamp'])
                if datetime.now() - cache_time > timedelta(minutes=CACHE_EXPIRATION_MINUTES):
                    logger.info(f"キャッシュ '{key}' は有効期限切れです。")
                    return None
            except (KeyError, TypeError):
                return None
        
        logger.info(f"キャッシュ '{key}' からデータを読み込みました。")
        return cached_data.get('data')

    def set_cache(self, key: str, data: dict | list):
        if not data: return
        path = self._get_cache_path(key)
        payload = {'timestamp': datetime.now().isoformat(), 'data': data}
        
        # ▼▼▼【修正点】ファイルの書き込みを便利関数に任せる▼▼▼
        success = save_json_to_file(path, payload)
        if success:
            logger.info(f"'{key}' のデータをキャッシュに保存しました。")
        # ▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲
