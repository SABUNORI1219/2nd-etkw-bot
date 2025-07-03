# config.pyからレイドタイプのリストをインポート
from config import RAID_TYPES

class RaidLogicHandler:
    """
    プレイヤーデータの比較と、レイドクリアパーティの特定という、
    分析ロジックのみを担当する専門クラス。
    """
    def find_changed_players(self, current_state: dict, previous_state: dict) -> list:
        """
        2つのプレイヤー状態を比較し、レイドクリア数が増加したプレイヤーのリストを返す。
        戻り値: [{'uuid': '...', 'raid_type': 'tna'}, ...]
        """
        changed_players = []
        for uuid, current_player in current_state.items():
            if uuid in previous_state:
                previous_player = previous_state[uuid]
                
                # Playerオブジェクトのメソッドを使って、レイドデータの辞書全体を比較
                if current_player.get_all_raid_counts() != previous_player.get_all_raid_counts():
                    # 変化があった場合、どのレイドが増えたか特定
                    for raid_type in RAID_TYPES:
                        if current_player.get_raid_count(raid_type) > previous_player.get_raid_count(raid_type):
                            changed_players.append({'uuid': uuid, 'raid_type': raid_type})
                            # 1回のチェックで1プレイヤーが複数のレイドをクリアすることは稀なため、
                            # 最初に変化を見つけたらループを抜ける
                            break 
        return changed_players

    def identify_parties(self, changed_players: list, online_info: dict) -> list:
        """
        変化したプレイヤーのリストを、レイドの種類とワールド情報でグループ化し、
        4人パーティが成立したものを特定して返す。
        戻り値: [{'raid_type': 'tna', 'players': [uuid1, uuid2, ...]}, ...]
        """
        # {raid_type: {world: [uuid, ...]}} という形式でグループ化
        raid_world_groups = {}
        for change in changed_players:
            uuid = change['uuid']
            raid_type = change['raid_type']
            
            if uuid in online_info:
                world = online_info[uuid]['server']
                
                # 辞書のキーが存在しなければ作成
                if raid_type not in raid_world_groups:
                    raid_world_groups[raid_type] = {}
                if world not in raid_world_groups[raid_type]:
                    raid_world_groups[raid_type][world] = []
                
                raid_world_groups[raid_type][world].append(uuid)

        # 4人組が成立したパーティだけを抽出
        identified_parties = []
        for raid_type, worlds in raid_world_groups.items():
            for world, players in worlds.items():
                if len(players) == 4:
                    identified_parties.append({'raid_type': raid_type, 'players': players})
        
        return identified_parties
