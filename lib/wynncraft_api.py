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
        """Nori APIからプレイヤーのデータを取得する。衝突の場合はリストを返す。"""
        try:
            url = NORI_PLAYER_API_URL.format(player_name)
            print(f"--- [API Handler] Nori Player APIにリクエスト: {url}") # どのURLにアクセスしているかログに出す

            async with self.session.get(url) as response:
                status = response.status
                text = await response.text() # まずは生テキストとして応答を取得

                # ▼▼▼【診断ログを追加】▼▼▼
                print(f"--- [API Handler] Nori Player APIからの応答:")
                print(f"--- ステータスコード: {status}")
                print(f"--- 生データ: {text[:500]}") # 長すぎる場合を考慮し、先頭500文字だけ表示

                # 応答が成功(200)で、かつ中身がJSONであれば解析を試みる
                if status == 200:
                    try:
                        data = await response.json(content_type=None) # content_typeを無視して強制的にJSONとして解析
                        # 正常なプレイヤーデータか、衝突リストかを判別して返す
                        if (isinstance(data, dict) and 'uuid' in data) or isinstance(data, list):
                            return data
                    except Exception as e:
                        print(f"--- [API Handler] JSON解析エラー: {e}")
                        return None
                
                # プレイヤーが見つからない場合、APIはリストを返すがステータスが200でない可能性がある
                try:
                    data = await response.json(content_type=None)
                    if isinstance(data, list):
                        print("--- [API Handler] 衝突（リスト形式）を検出しました。")
                        return data
                except Exception:
                    pass # JSONでなければ何もしない

                print("--- [API Handler] 有効なプレイヤーデータとして処理できませんでした。")
                return None

        except Exception as e:
            print(f"--- [API Handler] Nori Player APIリクエスト中にエラー: {e}")
            return None
            
    async def close_session(self):
        if self.session:
            await self.session.close()
