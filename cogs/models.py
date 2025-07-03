# APIから取得したデータを扱うための設計図（モデル）を定義します

class Player:
    def __init__(self, uuid, data):
        self.uuid = uuid
        self.data = data

    @property
    def username(self):
        return self.data.get('username', 'Unknown')

    @property
    def server(self):
        return self.data.get('server')
    
    @property
    def is_online(self):
        # Nori APIではオンラインのプレイヤーは辞書、オフラインは文字列
        # このクラスはオンラインプレイヤーを前提とする
        return True

    def get_raid_count(self, raid_name):
        # Wynncraft v3 APIの構造に合わせて修正
        raids_dict = self.data.get("guild", {}).get("raids", {})
        return raids_dict.get(raid_name, 0)

class Guild:
    def __init__(self, data):
        self.data = data
        self.name = data.get('name')

    def get_all_member_uuids(self):
        # Nori APIの構造に合わせて修正
        members_data = self.data.get("members", [])
        uuids = []
        for member in members_data:
            if isinstance(member, dict) and 'uuid' in member:
                uuids.append(member['uuid'])
        return uuids

    def get_online_members_info(self):
        # Nori APIの構造に合わせて修正
        members_data = self.data.get("members", [])
        online_info = {}
        for member in members_data:
            if isinstance(member, dict) and member.get('online'):
                online_info[member['uuid']] = {'server': member.get('server')}
        return online_info
