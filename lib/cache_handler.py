import json
import os
from datetime import datetime, timedelta
import logging
from .utils import load_json_from_file, save_json_to_file

logger = logging.getLogger(__name__)

CACHE_DIR = "cache"
CACHE_EXPIRATION_MINUTES = 1

class CacheHandler:
    def __init__(self):
        if not os.path.exists(CACHE_DIR):
            os.makedirs(CACHE_DIR)

    def _get_cache_path(self, key: str) -> str:
        safe_key = key.replace("/", "_").replace("\\", "_")
        return os.path.join(CACHE_DIR, f"{safe_key}.json")

    def get_cache(self, key: str, ignore_freshness: bool = False) -> dict | list | None:
        path = self._get_cache_path(key)
        cached_data = load_json_from_file(path)
        if not cached_data:
            return None
        if not ignore_freshness:
            try:
                cache_time = datetime.fromisoformat(cached_data['timestamp'])
                if datetime.now() - cache_time > timedelta(minutes=CACHE_EXPIRATION_MINUTES):
                    logger.info(f"キャッシュ '{key}' は有効期限切れです。")
                    # 有効期限切れのファイルは削除
                    try:
                        os.remove(path)
                        logger.info(f"期限切れキャッシュファイル {path} を削除しました。")
                    except Exception:
                        pass
                    return None
            except (KeyError, TypeError):
                return None
        logger.info(f"キャッシュ '{key}' からデータを読み込みました。")
        return cached_data.get('data')

    def set_cache(self, key: str, data: dict | list):
        if not data: return
        path = self._get_cache_path(key)
        payload = {'timestamp': datetime.now().isoformat(), 'data': data}
        success = save_json_to_file(path, payload)
        if success:
            logger.info(f"'{key}' のデータをキャッシュに保存しました。")

    def cleanup_expired_cache(self):
        """ キャッシュディレクトリ内の期限切れファイルをすべて削除 """
        now = datetime.now()
        for fname in os.listdir(CACHE_DIR):
            if not fname.endswith('.json'):
                continue
            fpath = os.path.join(CACHE_DIR, fname)
            data = load_json_from_file(fpath)
            if not data:
                continue
            try:
                cache_time = datetime.fromisoformat(data['timestamp'])
                if now - cache_time > timedelta(minutes=CACHE_EXPIRATION_MINUTES):
                    os.remove(fpath)
                    logger.info(f"期限切れキャッシュファイル {fpath} をクリーンアップで削除しました。")
            except Exception:
                continue
