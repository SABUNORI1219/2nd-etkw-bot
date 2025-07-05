import aiohttp
import asyncio

# 設定ファイルからAPIのURLをインポート
from config import NORI_GUILD_API_URL, WYNN_PLAYER_API_URL, NORI_PLAYER_API_URL

class WynncraftAPI:
    """
    Wynncraft APIとの全ての通信を担当する専門クラス。
    """
    def __init__(self):
        self.session = aiohttp.ClientSession()

    async def get_nori_guild_data(self) -> dict | None:
        """Nori APIからギルドの基本データを取得する"""
        try:
            async with self.session.get(NORI_GUILD_API_URL) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    print(f"--- [API Handler] ギルドAPIエラー: {response.status}")
                    return None
        except Exception as e:
            print(f"--- [API Handler] ギルドAPIリクエスト中にエラー: {e}")
            return None

    async def get_wynn_player_data(self, player_uuid: str) -> dict | None:
        """Wynncraft公式APIからプレイヤーの詳細データを取得する"""
        if not player_uuid: return None
        try:
            formatted_uuid = player_uuid.replace('-', '')
            url = WYNN_PLAYER_API_URL.format(formatted_uuid)
            async with self.session.get(url) as response:
                if response.status == 200: return await response.json()
                else: return None
        except Exception as e:
            print(f"--- [API Handler] プレイヤーデータ取得中にエラー (UUID: {player_uuid}): {e}")
            return None
    
    async def get_uuid_from_name(self, player_name: str) -> str | None:
        """プレイヤー名からUUIDを取得する"""
        try:
            url = WYNN_PLAYER_API_URL.format(player_name)
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get('uuid')
                else:
                    return None
        except Exception:
            return None

    async def get_nori_player_data(self, player_name: str) -> dict | list | None:
        """Nori APIからプレイヤーのデータを取得する。衝突の場合はリストを、見つからない場合はNoneを返す。"""
        try:
            url = NORI_PLAYER_API_URL.format(player_name)
            async with self.session.get(url) as response:
                data = await response.json()

                # ▼▼▼【修正点】APIからの応答を厳密に判別する ▼▼▼
                # 応答がリスト形式（衝突）か、有効な辞書形式（単一プレイヤー）の場合
                if isinstance(data, list) or (isinstance(data, dict) and 'uuid' in data):
                    return data
                
                # "No player found" という意図されたエラーの場合
                if isinstance(data, dict) and "Error" in data and "No player found" in data["Error"]:
                    return None # この場合のみ「見つからなかった(None)」と判断

                # その他の予期せぬエラー
                print(f"--- [API Handler] Nori Player APIから予期せぬ応答: {response.status}, {data}")
                return None
                
        except Exception as e:
            print(f"--- [API Handler] Nori Player APIリクエスト中にエラー: {e}")
            return None
            
    async def close_session(self):
        if self.session:
            await self.session.close()
