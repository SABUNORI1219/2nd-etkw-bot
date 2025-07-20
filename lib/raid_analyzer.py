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
            if len(records) < 4:
                continue

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
        # タイムスタンプがNoneなレコードは除外
        valid_records = [r for r in records if r[5] is not None]
        # この関数は、時間差やサーバー情報に基づいてプレイヤーを4人組にするロジック
        # 簡単のため、ここでは時間が近い4人を単純にグループ化する
        valid_records.sort(key=lambda x: x[5]) # タイムスタンプでソート
        for i in range(len(valid_records) - 3):
            party_candidate = valid_records[i:i+4]
            first_time = self.ensure_datetime(party_candidate[0][5])
            last_time = self.ensure_datetime(party_candidate[-1][5])
            if (last_time - first_time) <= timedelta(minutes=TIME_WINDOW_MINUTES):
                parties.append(party_candidate)
        return parties

    def _score_party(self, party: list) -> tuple[int, dict]:
        """パーティ候補をスコアリングする"""
        score = 0
        criteria = {}

        # 2分前のサーバーデータを参照
        lookback_servers = []
        lookback_info = []
        for p in party:
            uuid = p[1]
            clear_time = self.ensure_datetime(p[5])
            lookback_time = clear_time - timedelta(minutes=SERVER_LOOKBACK_MINUTES)
            server_at_lookback = get_latest_server_before(uuid, lookback_time)
            lookback_servers.append(server_at_lookback)
            lookback_info.append({'uuid': uuid, 'clear_time': clear_time, 'lookback_time': lookback_time, 'server': server_at_lookback})
        
        # サーバーの一致度をスコアリング（2分前のデータで判定）
        valid_servers = [s for s in lookback_servers if s is not None]
        if len(valid_servers) == 4:
            if len(set(valid_servers)) == 1:
                score += 50
                criteria['server_match'] = f"全員が直前サーバー一致 ({valid_servers[0]})"
            else:
                score += 20
                criteria['server_match'] = f"直前サーバーが一部異なる: {valid_servers}"
        else:
            criteria['server_match'] = f"一部の直前サーバー情報が欠損: {lookback_info}"

        # 時間差をスコアリング
        first_time = self.ensure_datetime(party[0][5])
        last_time = self.ensure_datetime(party[-1][5])
        time_diff = (last_time - first_time).total_seconds()
        if time_diff <= 60:
            score += 50; criteria['time_proximity'] = f"1分以内にクリア ({int(time_diff)}秒差)"
        elif time_diff <= 120:
            score += 30; criteria['time_proximity'] = f"2分以内にクリア ({int(time_diff)}秒差)"
        else:
            score += 10; criteria['time_proximity'] = f"3分以内にクリア ({int(time_diff)}秒差)"
            
        return score, criteria
