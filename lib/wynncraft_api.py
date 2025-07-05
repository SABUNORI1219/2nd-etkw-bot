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

    async def get_nori_guild_data(self, guild_identifier: str) -> dict | None:
        """Nori APIからギルドの基本データを取得する"""
        try:
            # ギルド名またはプレフィックスで検索
            url = NORI_GUILD_API_URL.format(guild_identifier.replace(' ', '%20'))
            async with self.session.get(url) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    print(f"--- [API Handler] Nori Guild APIエラー: {response.status}")
                    return None
        except Exception as e:
            print(f"--- [API Handler] Nori Guild APIリクエスト中にエラー: {e}")
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

    async def get_nori_player_data(self, player_name: str) -> dict | None:
        """
        Nori APIからプレイヤーのデータを取得する。
        成功すればデータ(辞書)、失敗すればNoneを返す。
        """
        try:
            url = NORI_PLAYER_API_URL.format(player_name)
            async with self.session.get(url) as response:
                # 応答が成功(200番台)で、かつ中身があればJSONとして返す
                if 200 <= response.status < 300 and response.content_length != 0:
                    return await response.json()
                else:
                    # それ以外はすべて「見つからなかった」と判断する
                    return None
        except Exception as e:
            print(f"--- [API Handler] Nori Player APIリクエスト中にエラー: {e}")
            return None
            
    async def close_session(self):
        if self.session:
            await self.session.close()
