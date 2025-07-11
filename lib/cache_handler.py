import json
import os
from datetime import datetime, timedelta

CACHE_DIR = "cache" # キャッシュファイルを保存するフォルダ名
CACHE_EXPIRATION_MINUTES = 1 # キャッシュの有効期間（分）

class CacheHandler:
    """
    JSONファイルへのデータの読み書きと、キャッシュの鮮度管理を担当する。
    """
    def __init__(self):
        # cacheフォルダがなければ作成する
        if not os.path.exists(CACHE_DIR):
            os.makedirs(CACHE_DIR)

    def _get_cache_path(self, key: str) -> str:
        """キャッシュファイルのパスを生成する"""
        return os.path.join(CACHE_DIR, f"{key}.json")

    def get_cache(self, key: str, ignore_freshness: bool = False) -> dict | list | None:
        """キャッシュを読み込み、新鮮であればデータを返す"""
        path = self._get_cache_path(key)
        if not os.path.exists(path):
            return None # ファイルが存在しない

        try:
            with open(path, 'r', encoding='utf-8') as f:
                cached_data = json.load(f)
            
            # 有効期限をチェック
            if not ignore_freshness:
                cache_time = datetime.fromisoformat(cached_data['timestamp'])
                if datetime.now() - cache_time > timedelta(minutes=CACHE_EXPIRATION_MINUTES):
                    return None # キャッシュが古い
            
            return cached_data['data'] # 新鮮なデータを返す
        
        except (json.JSONDecodeError, KeyError):
            return None # ファイルが壊れているか、形式が違う

    def set_cache(self, key: str, data: dict | list):
        """新しいデータをタイムスタンプ付きでキャッシュに保存する"""
        path = self._get_cache_path(key)
        
        payload = {
            'timestamp': datetime.now().isoformat(),
            'data': data
        }
        
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, indent=4)
