from config import RAID_TYPES

class Player:
    """
    プレイヤー一人ひとりの情報を保持するためのシンプルなデータクラス。
    """
    def __init__(self, name: str, uuid: str):
        self.name = name
        self.uuid = uuid
        self._raid_counts = {raid_type: 0 for raid_type in RAID_TYPES}

    def set_raid_counts(self, raid_data: dict):
        """APIから取得したレイドデータの辞書をセットする"""
        for raid_type in RAID_TYPES:
            # APIのレイド名はスペースを含むため、configの定義と合わせる必要がある
            # ここではAPIのキーがconfigと一致していると仮定
            self._raid_counts[raid_type] = raid_data.get(raid_type, 0)

    def get_raid_count(self, raid_type: str) -> int:
        """指定されたレイドのクリア回数を返す"""
        return self._raid_counts.get(raid_type, 0)

    def get_all_raid_counts(self) -> dict:
        """全てのレイドクリア回数の辞書を返す"""
        return self._raid_counts
