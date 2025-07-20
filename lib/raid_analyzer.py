import logging
from datetime import datetime, timedelta
from collections import defaultdict
from itertools import combinations

logger = logging.getLogger(__name__)
# データベースから必要な関数をインポート
from .database_handler import get_unprocessed_raid_history, mark_raid_history_as_processed, get_latest_server_before

# スコアリングの基準
SCORE_THRESHOLD = 85  # このスコア以上で通知
TIME_WINDOW_MINUTES = 3 # この時間内でのクリアを同じパーティと見なす
MAX_RECORDS_PER_RAID = 20

class RaidAnalyzer:
    def ensure_datetime(self, value):
        return datetime.fromisoformat(value) if isinstance(value, str) else value

    def _build_server_cache(self, records):
        """
        キャッシュ: { (uuid, lookback_minute): server }
        uuidごとに各クリア履歴の2分前サーバーをまとめて取得しメモリ上にキャッシュ
        """
        from collections import defaultdict
        server_cache = defaultdict(dict)
        # uuidごとに履歴をまとめる
        uuid_to_records = defaultdict(list)
        for rec in records:
            uuid = rec[1]
            clear_time = self.ensure_datetime(rec[5])
            uuid_to_records[uuid].append(clear_time)
        # uuidごとにDBアクセスをまとめて省略化
        for uuid, times in uuid_to_records.items():
            for clear_time in times:
                lookback_time = clear_time - timedelta(minutes=2)
                server_cache[uuid][lookback_time] = get_latest_server_before(uuid, lookback_time)
        return server_cache

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
            valid_records = [r for r in records if r[5] is not None]
            valid_records.sort(key=lambda x: x[5]) # タイムスタンプでソート
            recent_records = valid_records[-MAX_RECORDS_PER_RAID:] if len(valid_records) > MAX_RECORDS_PER_RAID else valid_records

            # --- ここでサーバーキャッシュを構築 ---
            server_cache = self._build_server_cache(recent_records)
            
            # まず1人ずつ「近い人リスト」を作り、その組み合わせだけcombinations
            parties = []
            seen_ids = set()
            for i, rec in enumerate(recent_records):
                rec_time = self.ensure_datetime(rec[5])
                # 3分以内の人リスト
                close_group = [r for r in recent_records if abs((self.ensure_datetime(r[5]) - rec_time).total_seconds()) <= TIME_WINDOW_MINUTES * 60]
                if len(close_group) < 4:
                    continue
                # 組み合わせ爆発防止: close_groupが10人以上なら上位10人だけ
                if len(close_group) > 10:
                    close_group = close_group[:10]
                for party_candidate in combinations(close_group, 4):
                    times = [self.ensure_datetime(p[5]) for p in party_candidate]
                    if max(times) - min(times) <= timedelta(minutes=TIME_WINDOW_MINUTES):
                        ids_tuple = tuple(sorted(p[0] for p in party_candidate))
                        if ids_tuple not in seen_ids:
                            seen_ids.add(ids_tuple)
                            parties.append(list(party_candidate))

            # --- スコアリング ---
            for party in parties:
                score, criteria = self._score_party(party, server_cache)
                logger.info(f"パーティ候補: {[p[2] for p in party]}, スコア: {score}, 詳細: {criteria}")
                if score >= SCORE_THRESHOLD:
                    confident_parties.append({'party': party, 'score': score, 'criteria': criteria})
                    processed_ids.update([p[0] for p in party])

        if processed_ids:
            mark_raid_history_as_processed(list(processed_ids))

        return confident_parties

    def _find_parties(self, records: list) -> list:
        """同じレイドをクリアしたプレイヤーリストから、4人組のパーティ候補を探す"""
        parties = []
        # タイムスタンプがNoneなレコードは除外
        # この関数は、時間差やサーバー情報に基づいてプレイヤーを4人組にするロジック
        # 簡単のため、ここでは時間が近い4人を単純にグループ化する
        valid_records = [r for r in records if r[5] is not None]
        valid_records.sort(key=lambda x: x[5]) # タイムスタンプでソート
        seen_ids = set() # 履歴IDのセットで重複排除
        
        for party_candidate in combinations(valid_records, 4):
            times = [self.ensure_datetime(p[5]) for p in party_candidate]
            if max(times) - min(times) <= timedelta(minutes=TIME_WINDOW_MINUTES):
                # 履歴IDのタプルで重複判定（IDはp[0]）
                ids_tuple = tuple(sorted(p[0] for p in party_candidate))
                if ids_tuple not in seen_ids:
                    seen_ids.add(ids_tuple)
                    parties.append(list(party_candidate))
        return parties

    def _score_party(self, party: list, server_cache=None) -> tuple[int, dict]:
        """パーティ候補をスコアリングする"""
        score = 0
        criteria = {}

        # 2分前のサーバーデータを参照
        lookback_servers = []
        lookback_info = []
        for p in party:
            uuid = p[1]
            clear_time = self.ensure_datetime(p[5])
            lookback_time = clear_time - timedelta(minutes=2)
            # キャッシュ利用
            server_at_lookback = None
            if server_cache and uuid in server_cache and lookback_time in server_cache[uuid]:
                server_at_lookback = server_cache[uuid][lookback_time]
            else:
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
