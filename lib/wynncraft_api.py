import aiohttp
import asyncio
from urllib.parse import quote
import logging # printより確実なロギングモジュールをインポート

# ロギングの設定
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 設定ファイルからAPIのURLをインポート
from config import (
    NORI_GUILD_API_URL,
    NORI_PLAYER_API_URL,
    WYNN_PLAYER_API_URL,
    WYNN_GUILD_BY_NAME_API_URL,
    WYNN_GUILD_BY_PREFIX_API_URL
)

class WynncraftAPI:
    def __init__(self):
        # ▼▼▼【修正点1】身分証（User-Agentヘッダー）を定義▼▼▼
        self.headers = {'User-Agent': 'DiscordBot/1.0 (Contact: YourDiscord#1234)'}
        self.session = aiohttp.ClientSession(headers=self.headers)

    async def get_guild_by_name(self, guild_name: str) -> dict | None:
        """Wynncraft公式APIから、フルネームでギルドデータを取得する"""
        try:
            url = WYNN_GUILD_BY_NAME_API_URL.format(quote(guild_name))
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    # 公式APIはデータが見つかるとリストで返すため、最初の要素を取得
                    return data if data else None
                return None
        except Exception as e:
            logger.error(f"--- [API Handler] Wynncraft Guild (Name) APIリクエスト中にエラー: {e}")
            return None

    async def get_guild_by_prefix(self, guild_prefix: str) -> dict | None:
        """Wynncraft公式APIから、プレフィックスでギルドデータを取得する"""
        try:
            url = WYNN_GUILD_BY_PREFIX_API_URL.format(quote(guild_prefix))
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    # プレフィックス検索は単一の結果を返すことが多い
                    return data if data else None
                return None
        except Exception as e:
            logger.error(f"--- [API Handler] Wynncraft Guild (Prefix) APIリクエスト中にエラー: {e}")
            return None

    async def get_nori_guild_data(self, guild_identifier: str) -> dict | None:
        """Nori APIからギルドの基本データを取得する"""
        try:
            encoded_identifier = quote(guild_identifier)
            url = NORI_GUILD_API_URL.format(encoded_identifier)
            
            # ▼▼▼【修正点2】リクエストにヘッダーを添付▼▼▼
            async with self.session.get(url) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    # サーバーからの応答内容もログに出力して、何が起きているか確認する
                    error_text = await response.text()
                    logger.error(f"--- [API Handler] Nori Guild APIエラー: Status {response.status}, Body: {error_text[:200]}")
                    return None
        except Exception as e:
            logger.error(f"--- [API Handler] Nori Guild APIリクエスト中にエラー: {e}")
            return None

    async def get_wynn_player_data(self, player_uuid: str) -> dict | None:
        """Wynncraft公式APIからプレイヤーの詳細データを取得する"""
        if not player_uuid: return None
        try:
            formatted_uuid = player_uuid.replace('-', '')
            url = WYNN_PLAYER_API_URL.format(formatted_uuid)
            async with self.session.get(url) as response:
                if response.status == 200: 
                    return await response.json()
                else: 
                    return None
        except Exception as e:
            logger.error(f"--- [API Handler] プレイヤーデータ取得中にエラー (UUID: {player_uuid}): {e}")
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

    async def get_nori_player_data(self, player_identifier: str) -> dict | list | None:
        """Nori APIからプレイヤーのデータを取得する"""
        try:
            url = NORI_PLAYER_API_URL.format(player_identifier)
            # ▼▼▼【修正点2】リクエストにヘッダーを添付▼▼▼
            async with self.session.get(url) as response:
                if 200 <= response.status < 300 and response.content_length != 0:
                    return await response.json()
                else:
                    return None
        except Exception as e:
            logger.error(f"--- [API Handler] Nori Player APIリクエスト中にエラー: {e}")
            return None
    async def get_territory_list(self) -> dict | None:
        """Wynncraft公式APIから、現在の全テリトリー所有者リストを取得する"""
        try:
            # このURLはconfig.pyで定義しても良いが、一箇所でしか使わないため直接記述
            url = "https://api.wynncraft.com/v3/guild/list/territory"
            async with self.session.get(url) as response:
                if response.status == 200:
                    return await response.json()
                return None
        except Exception as e:
            logger.error(f"--- [API Handler] Wynncraft Territory APIリクエスト中にエラー: {e}")
            return None
            
    async def close_session(self):
        if self.session:
            await self.session.close()
