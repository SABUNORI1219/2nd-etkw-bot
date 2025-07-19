import logging
from datetime import datetime, timedelta
from collections import defaultdict

logger = logging.getLogger(__name__)
# データベースから必要な関数をインポート
from .database_handler import get_unprocessed_raid_history, mark_raid_history_as_processed

# スコアリングの基準
SCORE_THRESHOLD = 85  # このスコア以上で通知
TIME_WINDOW_MINUTES = 3 # この時間内でのクリアを同じパーティと見なす

class RaidAnalyzer:
    def ensure_datetime(self, value):
        return datetime.fromisoformat(value) if isinstance(value, str) else value

    def analyze_raids(self) -> list:
        """未処理のレイド履歴を分析し、ギルドレイドパーティを推定する"""
        history = get_unprocessed_raid_history()
        if not history:
            return []

        # レイドの種類ごとにクリア履歴をグループ分け
        raids_by_type = defaultdict(list)
        for record in history:
            raids_by_type[record[3]].append(record) # record[3]はraid_name

        confident_parties = []
        processed_ids = []

        for raid_name, records in raids_by_type.items():
            if len(records) < 4: continue

            # 時間が近いプレイヤーでパーティを組む
            possible_parties = self._find_parties(records)

            for party in possible_parties:
                score, criteria = self._score_party(party)
                logger.info(f"パーティ候補: {[p[2] for p in party]}, スコア: {score}, 詳細: {criteria}")
                
                if score >= SCORE_THRESHOLD:
                    confident_parties.append({'party': party, 'score': score, 'criteria': criteria})
                
                # 分析済みの履歴IDを記録
                processed_ids.extend([p[0] for p in party])
        
        if processed_ids:
            mark_raid_history_as_processed(list(set(processed_ids)))

        return confident_parties

    def _find_parties(self, records: list) -> list:
        """同じレイドをクリアしたプレイヤーリストから、4人組のパーティ候補を探す"""
        parties = []
        # この関数は、時間差やサーバー情報に基づいてプレイヤーを4人組にするロジック
        # 簡単のため、ここでは時間が近い4人を単純にグループ化する
        records.sort(key=lambda x: x[5]) # タイムスタンプでソート
        for i in range(len(records) - 3):
            party_candidate = records[i:i+4]
            first_time = self.ensure_datetime(party_candidate[0][5])
            last_time = self.ensure_datetime(party[-1][5])
            if (last_time - first_time) <= timedelta(minutes=TIME_WINDOW_MINUTES):
                parties.append(party_candidate)
        return parties

    def _score_party(self, party: list) -> tuple[int, dict]:
        """パーティ候補をスコアリングする"""
        score = 0
        criteria = {}
        
        # サーバーの一致度をスコアリング
        servers = [p[4] for p in party if p[4] is not None]
        if len(servers) == 4:
            if len(set(servers)) == 1:
                score += 50; criteria['server_match'] = f"全員が同じサーバー ({servers[0]})"
            else:
                score += 20; criteria['server_match'] = "サーバーが一部異なる"
        else:
            criteria['server_match'] = "一部のサーバー情報が欠損"

        # 時間差をスコアリング
        first_time = self.ensure_datetime(party_candidate[0][5])
        last_time = self.ensure_datetime(party[-1][5])
        time_diff = (last_time - first_time).total_seconds()
        if time_diff <= 60:
            score += 50; criteria['time_proximity'] = f"1分以内にクリア ({int(time_diff)}秒差)"
        elif time_diff <= 120:
            score += 30; criteria['time_proximity'] = f"2分以内にクリア ({int(time_diff)}秒差)"
        else:
            score += 10; criteria['time_proximity'] = f"3分以内にクリア ({int(time_diff)}秒差)"
            
        return score, criteria
