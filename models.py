# models.py

class Player:
    """Wynncraftプレイヤー一人のデータを扱うためのクラス"""
    def __init__(self, uuid, api_data):
        self.uuid = uuid
        self.data = api_data
    
    @property
    def username(self) -> str:
        """プレイヤー名を取得します。"""
        return self.data.get('username', 'Unknown')

    @property
    def server(self):
        return self.data.get('server')
    
    @property
    def is_online(self):
        return True

    def get_raid_count(self, raid_name: str) -> int:
        # Wynncraft v3 APIの構造に合わせて修正
        raids_dict = self.data.get("guild", {}).get("raids", {})
        return raids_dict.get(raid_name, 0)

class Guild:
    """Wynncraftギルド全体のデータを扱うためのクラス"""
    def __init__(self, api_data):
        self.data = api_data
        self.name = self.data.get('name', 'Unknown')

    def get_all_member_uuids(self) -> list:
        """ギルドに所属する全メンバーのUUIDリストを取得します。"""
        members_data = self.data.get("members", [])
        uuids = [
            member['uuid']
            for member in members_data
            if isinstance(member, dict) and 'uuid' in member
        ]
        return uuids

    def get_online_members_info(self) -> dict:
        """オンラインのメンバーの情報（UUIDとサーバー）を取得します。"""
        members_data = self.data.get("members", [])
        online_info = {
            member['uuid']: {'server': member.get('server')}
            for member in members_data
            if isinstance(member, dict) and member.get('online')
        }
        return online_info
