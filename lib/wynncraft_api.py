import aiohttp
import asyncio

# 設定ファイルからAPIのURLをインポート
from config import GUILD_API_URL, PLAYER_API_URL

class WynncraftAPI:
    """
    Wynncraft APIとの全ての通信を担当する専門クラス。
    """
    def __init__(self):
        # aiohttpのセッションをクラス内で保持すると、より効率的になります
        self.session = aiohttp.ClientSession()

    async def get_guild_data(self) -> dict | None:
        """Nori APIからギルドの基本データを取得する"""
        try:
            async with self.session.get(GUILD_API_URL) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    print(f"--- [API Handler] ギルドAPIエラー: {response.status}")
                    return None
        except Exception as e:
            print(f"--- [API Handler] ギルドAPIリクエスト中にエラー: {e}")
            return None

    async def get_player_data(self, player_uuid: str) -> dict | None:
        """Wynncraft公式APIからプレイヤーの詳細データを取得する"""
        if not player_uuid:
            return None
        
        try:
            # v3 APIはハイフンなしUUIDを要求する
            formatted_uuid = player_uuid.replace('-', '')
            url = PLAYER_API_URL.format(formatted_uuid)
            
            async with self.session.get(url) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    # プレイヤーが存在しない場合(404)などはエラーではなくNoneを返す
                    return None
        except Exception as e:
            print(f"--- [API Handler] プレイヤーデータ取得中にエラー (UUID: {player_uuid}): {e}")
            return None
    
    async def get_uuid_from_name(self, player_name: str) -> str | None:
        """プレイヤー名からUUIDを取得する"""
        try:
            # v3 APIはプレイヤー名でも検索可能
            url = PLAYER_API_URL.format(player_name)
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get('uuid')
                else:
                    return None
        except Exception:
            return None

    async def close_session(self):
        """Bot終了時にセッションをクローズする"""
        if self.session:
            await self.session.close()
