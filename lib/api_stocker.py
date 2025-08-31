import aiohttp
import asyncio
from urllib.parse import quote
import logging
from PIL import Image
from io import BytesIO

from config import WYNNCRAFT_API_TOKEN

logger = logging.getLogger(__name__)

# 共通リクエスト関数
async def _make_request(session, url: str, *, return_bytes: bool = False, max_retries: int = 5, timeout: int = 10):
    for i in range(max_retries):
        try:
            async with session.get(url, timeout=timeout) as response:
                if 200 <= response.status < 301:
                    if return_bytes:
                        data = await response.read()
                        if not data:
                            return None
                        return data
                    if response.content_length != 0:
                        return await response.json()
                    return None
                non_retryable_codes = [400, 404, 429]
                if response.status in non_retryable_codes:
                    logger.warning(f"APIが{response.status}エラーを返しました。対象が見つかりません。URL: {url}")
                    return None
                retryable_codes = [408, 500, 502, 503, 504]
                if response.status in retryable_codes:
                    logger.warning(f"APIがステータス{response.status}を返しました。再試行します... ({i+1}/{max_retries})")
                    await asyncio.sleep(5)
                    continue
                logger.error(f"APIから予期せぬエラー: Status {response.status}, URL: {url}")
                return None
        except Exception as e:
            logger.error(f"リクエスト中に予期せぬエラー: {repr(e)}", exc_info=True)
            await asyncio.sleep(2)
    logger.error(f"最大再試行回数({max_retries}回)に達しました。URL: {url}")
    return None

class WynncraftAPI:
    """
    api.wynncraft.com関連APIのみ。認証トークン必須。
    """
    def __init__(self):
        self.headers = {
            'User-Agent': 'DiscordBot/1.0',
            'Authorization': f'Bearer {WYNNCRAFT_API_TOKEN}',
        }
        self._session = None

    async def _get_session(self):
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(headers=self.headers)
        return self._session

    async def get_guild_by_name(self, guild_name: str):
        url = f"https://api.wynncraft.com/v3/guild/{quote(guild_name)}"
        session = await self._get_session()
        return await _make_request(session, url)

    async def get_guild_by_prefix(self, guild_prefix: str):
        url = f"https://api.wynncraft.com/v3/guild/prefix/{quote(guild_prefix)}"
        session = await self._get_session()
        return await _make_request(session, url)

    async def get_official_player_data(self, player_data: str):
        url = f"https://api.wynncraft.com/v3/player/{quote(player_data)}?fullResult"
        session = await self._get_session()
        return await _make_request(session, url)

    async def get_territory_list(self):
        url = "https://api.wynncraft.com/v3/guild/list/territory"
        session = await self._get_session()
        return await _make_request(session, url)

    async def close_session(self):
        if self._session:
            await self._session.close()

class OtherAPI:
    """
    api.wynncraft.com以外のAPI用。headerは用途ごとに分ける。
    """
    def __init__(self):
        self.guild_color_headers = {
            'User-Agent': 'Mozilla/5.0 ...',
            'Referer': 'https://athena.wynntils.com/'
        }
        self.vzge_headers = {
            'User-Agent': 'Mozilla/5.0 ...',
            'Accept': 'image/webp,image/apng,image/*,*/*;q=0.8',
            'Referer': 'https://vzge.me/'
        }
        self._guild_color_session = None
        self._vzge_session = None

    async def _get_guild_color_session(self):
        if self._guild_color_session is None or self._guild_color_session.closed:
            self._guild_color_session = aiohttp.ClientSession(headers=self.guild_color_headers)
        return self._guild_color_session

    async def _get_vzge_session(self):
        if self._vzge_session is None or self._vzge_session.closed:
            self._vzge_session = aiohttp.ClientSession(headers=self.vzge_headers)
        return self._vzge_session

    async def get_guild_color_map(self):
        url = "https://athena.wynntils.com/cache/get/guildList"
        session = await self._get_guild_color_session()
        data = await _make_request(session, url)
        if isinstance(data, list):
            return {g["prefix"]: g.get("color", "#FFFFFF") for g in data if g.get("prefix")}
        return None

    async def get_vzge_skin(self, uuid: str):
        url = f"https://vzge.me/bust/256/{quote(uuid)}"
        session = await self._get_vzge_session()
        return await _make_request(session, url, return_bytes=True)

    async def get_vzge_skin_image(self, uuid: str, size: int = 196):
        data = await self.get_vzge_skin(uuid)
        if not data:
            return None
        try:
            skin = Image.open(BytesIO(data)).convert("RGBA")
            skin = skin.resize((size, size), Image.LANCZOS)
            return skin
        except Exception as e:
            logger.error(f"vzge skin image decode failed: {e}")
            return None

    async def close_session(self):
        # それぞれのセッションをclose
        for sess in [self._guild_color_session, self._vzge_session]:
            if sess:
                await sess.close()
