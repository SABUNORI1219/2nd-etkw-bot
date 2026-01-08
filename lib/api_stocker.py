import aiohttp
import asyncio
from urllib.parse import quote
import logging
from PIL import Image
from io import BytesIO
from config import WYNNCRAFT_API_TOKEN

logger = logging.getLogger(__name__)

class WynncraftAPI:
    def __init__(self):
        self.headers = {
            'User-Agent': 'DiscordBot/1.0',
            'Authorization': f'Bearer {WYNNCRAFT_API_TOKEN}',
        }
        self.session = aiohttp.ClientSession(headers=self.headers)

    async def _make_request(self, url: str, *, return_bytes: bool = False, max_retries: int = 5, timeout: int = 10):
        for i in range(max_retries):
            try:
                async with self.session.get(url, timeout=timeout) as response:
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
                        if response.status == 500:
                            try:
                                body = await response.json()
                                if (
                                    isinstance(body, dict)
                                    and body.get("error") == "InternalError"
                                    and body.get("detail") == "Unable to render this guild"
                                ):
                                    logger.warning(f"APIがステータス500かつギルド未存在エラー: {body} URL: {url}")
                                    return None # リトライせず即None
                            except Exception as e:
                                logger.warning(f"500エラーのレスポンスパース失敗: {e}")
                        logger.warning(f"APIがステータス{response.status}を返しました。再試行します... ({i+1}/{max_retries})")
                        await asyncio.sleep(2)
                        continue
                    logger.error(f"APIから予期せぬエラー: Status {response.status}, URL: {url}")
                    return None
            except Exception as e:
                logger.error(f"リクエスト中に予期せぬエラー: {repr(e)}", exc_info=True)
                await asyncio.sleep(2)
        logger.error(f"最大再試行回数({max_retries}回)に達しました。URL: {url}")
        return None

    async def get_guild_by_name(self, guild_name: str):
        url = f"https://api.wynncraft.com/v3/guild/{quote(guild_name)}"
        return await self._make_request(url)

    async def get_guild_by_prefix(self, guild_prefix: str):
        url = f"https://api.wynncraft.com/v3/guild/prefix/{quote(guild_prefix)}"
        return await self._make_request(url)

    async def get_official_player_data(self, player_data: str):
        url = f"https://api.wynncraft.com/v3/player/{quote(player_data)}?fullResult"
        return await self._make_request(url)

    async def get_territory_list(self):
        url = "https://api.wynncraft.com/v3/guild/list/territory"
        return await self._make_request(url)

    async def close(self):
        await self.session.close()


class OtherAPI:
    def __init__(self):
        self.guild_color_headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': 'https://athena.wynntils.com/'
        }
        self.vzge_headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'image/webp,image/apng,image/*,*/*;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Accept-Language': 'en-US,en;q=0.9',
            'Cache-Control': 'no-cache',
            'Referer': 'https://vzge.me/'
        }
        # コネクション最適化
        connector = aiohttp.TCPConnector(
            limit=20,  # 総接続数制限
            limit_per_host=5,  # ホスト別接続数制限
            ttl_dns_cache=300,  # DNS キャッシュ時間
            use_dns_cache=True,  # DNS キャッシュ有効
            keepalive_timeout=30,  # Keep-Alive タイムアウト
            enable_cleanup_closed=True  # 閉じた接続のクリーンアップ
        )
        self.session = aiohttp.ClientSession(connector=connector)

    async def _make_request(self, url: str, *, headers=None, return_bytes: bool = False, max_retries: int = 5, timeout: int = 6):
        for i in range(max_retries):
            try:
                # より短い個別タイムアウト設定
                timeout_obj = aiohttp.ClientTimeout(total=timeout, connect=3)
                async with self.session.get(url, headers=headers, timeout=timeout_obj) as response:
                    if 200 <= response.status < 301:
                        if return_bytes:
                            data = await response.read()
                            return data if data else None
                        if response.content_length != 0:
                            return await response.json()
                        return None
                    if response.status in [400, 404, 429]:
                        logger.warning(f"APIが{response.status}エラーを返しました。URL: {url}")
                        return None
                    if response.status in [408, 500, 502, 503, 504]:
                        # 短めの間隔で素早くリトライ
                        wait_time = min(1.5 ** i, 4)  # 指数バックオフ、最大4秒
                        logger.warning(f"APIが{response.status}。{wait_time:.1f}秒後に再試行 ({i+1}/{max_retries}) URL: {url}")
                        await asyncio.sleep(wait_time)
                        continue
                    logger.error(f"API予期せぬエラー: Status {response.status}, URL: {url}")
                    return None
            except asyncio.TimeoutError:
                wait_time = min(1.0 ** i, 2)  # タイムアウト時はより短い間隔
                logger.warning(f"タイムアウト。{wait_time:.1f}秒後に再試行 ({i+1}/{max_retries}) URL: {url}")
                await asyncio.sleep(wait_time)
                continue
            except Exception as e:
                logger.error(f"APIリクエスト例外: {repr(e)}", exc_info=True)
                await asyncio.sleep(1.5)
        logger.error(f"最大再試行回数({max_retries})到達。URL: {url}")
        return None

    async def get_guild_color_map(self):
        url = "https://athena.wynntils.com/cache/get/guildList"
        data = await self._make_request(url, headers=self.guild_color_headers)
        if isinstance(data, list):
            return {g["prefix"]: g.get("color", "#FFFFFF") for g in data if g.get("prefix")}
        return None

    async def get_vzge_skin(self, uuid: str):
        url = f"https://vzge.me/bust/256/{quote(uuid)}"
        return await self._make_request(url, headers=self.vzge_headers, return_bytes=True)

    async def get_vzge_skin_image(self, uuid: str, size: int = 196):
        data = await self.get_vzge_skin(uuid)
        if not data:
            return None
        buf = BytesIO(data)
        try:
            with Image.open(buf) as skin:
                skin = skin.convert("RGBA")
                skin = skin.resize((size, size), Image.LANCZOS)
                return skin
        except Exception as e:
            logger.error(f"vzge skin image decode failed: {e}")
            return None
        finally:
            buf.close()

    async def close(self):
        await self.session.close()
