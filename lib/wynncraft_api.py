import aiohttp
import asyncio
from urllib.parse import quote
import logging

logger = logging.getLogger(__name__)

# configからURLテンプレートをインポート
from config import (
    NORI_GUILD_API_URL, NORI_PLAYER_API_URL,
    WYNN_PLAYER_API_URL, WYNN_GUILD_BY_NAME_API_URL, WYNN_GUILD_BY_PREFIX_API_URL
)

class WynncraftAPI:
    def __init__(self):
        self.headers = {'User-Agent': 'DiscordBot/1.0'}
        self._session = None # ⬅️ 最初はセッションを空にしておく

    async def _get_session(self) -> aiohttp.ClientSession:
        """非同期にセッションを初期化、または既存のものを返す"""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(headers=self.headers)
        return self._session

    # ▼▼▼【ここからが新しいリトライ機能の心臓部】▼▼▼
    async def _make_request(self, url: str) -> dict | list | None:
        """APIにリクエストを送信し、失敗した場合は再試行する共通メソッド"""
        session = await self._get_session()
        max_retries = 5
        for i in range(max_retries):
            try:
                async with self.session.get(url, timeout=10) as response:
                    # 成功した場合
                    if 200 <= response.status < 300:
                        return await response.json()
                    
                    # 再試行すべきエラーコードか判定
                    retryable_codes = [408, 429, 500, 502, 503, 504]
                    if response.status in retryable_codes:
                        logger.warning(f"--- [API Handler] APIがステータス{response.status}を返しました。再試行します... ({i+1}/{max_retries}) URL: {url}")
                        await asyncio.sleep(2) # 2秒待ってから再試行
                        continue
                    
                    # 再試行しないエラー
                    logger.error(f"--- [API Handler] APIから予期せぬエラー: Status {response.status}, URL: {url}")
                    return None

            except asyncio.TimeoutError:
                logger.warning(f"--- [API Handler] APIリクエストがタイムアウトしました。再試行します... ({i+1}/{max_retries}) URL: {url}")
                await asyncio.sleep(2)
            except Exception as e:
                logger.error(f"--- [API Handler] リクエスト中に予期せぬエラー: {e}", exc_info=True)
                return None
        
        logger.error(f"--- [API Handler] 最大再試行回数({max_retries}回)に達しました。URL: {url}")
        return None
    # ▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲

    # ▼▼▼【ここから下の全てのメソッドを、新しいリトライ機能を使うように修正】▼▼▼
    
    async def get_guild_by_name(self, guild_name: str) -> dict | None:
        url = WYNN_GUILD_BY_NAME_API_URL.format(quote(guild_name))
        data = await self._make_request(url)
        return data[0] if isinstance(data, list) and data else None

    async def get_guild_by_prefix(self, guild_prefix: str) -> dict | None:
        url = WYNN_GUILD_BY_PREFIX_API_URL.format(quote(guild_prefix))
        data = await self._make_request(url)
        return data[0] if isinstance(data, list) and data else None
        
    async def get_nori_guild_data(self, guild_identifier: str) -> dict | list | None:
        url = NORI_GUILD_API_URL.format(quote(guild_identifier))
        return await self._make_request(url)

    async def get_nori_player_data(self, player_identifier: str) -> dict | list | None:
        url = NORI_PLAYER_API_URL.format(quote(player_identifier))
        return await self._make_request(url)

    async def get_territory_list(self) -> dict | None:
        url = "https://api.wynncraft.com/v3/guild/list/territory"
        return await self._make_request(url)

    async def get_guild_color_map(self) -> dict | None:
        url = "https://athena.wynntils.com/cache/get/guildList"
        data = await self._make_request(url)
        if isinstance(data, list):
            return {g["prefix"]: g.get("color", "#FFFFFF") for g in data if g.get("prefix")}
        return None
    
    async def close_session(self):
        if self.session:
            await self.session.close()
