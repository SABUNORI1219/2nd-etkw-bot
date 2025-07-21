import logging
from datetime import datetime, timedelta
from collections import defaultdict, deque
from .db import fetch_individual_raid_history, get_last_server_before, insert_history

logger = logging.getLogger(__name__)

SCORE_THRESHOLD = 85
TIME_WINDOW_MINUTES = 3
SERVER_MATCH_SCORE = 50
SERVER_PARTIAL_SCORE = 20
TIME_SCORE_60 = 50
TIME_SCORE_120 = 30
TIME_SCORE_OTHER = 10

def estimate_and_save_parties():
    """
    個人クリア履歴からパーティ推定し、認定できるものをguild_raid_historyに保存する
    """
    # 個人クリア履歴を時系列で取得
    # fetch_individual_raid_history()の返り値: List of (player_name, raid_name, clear_time[datetime])
    clears = fetch_individual_raid_history()
    if not clears:
        logger.info("クリア履歴がありません")
        return []

    # レイドごとに分割
    clears_by_raid = defaultdict(list)
    for rec in clears:
        clears_by_raid[rec[1]].append(rec)
    
    saved_parties = []
    for raid, records in clears_by_raid.items():
        # 時刻順にソート
        records.sort(key=lambda x: x[2])  # x[2]: clear_time
        # スライディングウィンドウで4人組を抽出
        for i in range(len(records) - 3):
            party_candidate = records[i:i+4]
            first_time = party_candidate[0][2]
            last_time = party_candidate[-1][2]
            if (last_time - first_time) <= timedelta(minutes=TIME_WINDOW_MINUTES):
                score, criteria, server = _score_party(party_candidate)
                logger.info(f"パーティ候補: レイド名: {raid} / メンバー: {[p[0] for p in party_candidate]}, スコア: {score}, 詳細: {criteria}")
                if score >= SCORE_THRESHOLD:
                    members = [p[0] for p in party_candidate]
                    insert_history(
                        raid_name=raid,
                        clear_time=first_time,
                        party_members=members,
                        server_name=server,
                        trust_score=score
                    )
                    saved_parties.append({
                        "raid_name": raid,
                        "clear_time": first_time,
                        "members": members,
                        "server": server,
                        "trust_score": score,
                        "criteria": criteria
                    })
    return saved_parties

def _score_party(party):
    """
    party: [(player_name, raid_name, clear_time), ...] の4人組
    サーバー一致度・時間差でスコアリング
    """
    # サーバーログから直前サーバーを取得
    servers = []
    for p in party:
        server = get_last_server_before(p[0], p[2])
        servers.append(server)
    criteria = {}
    score = 0
    if len(servers) == 4:
        unique_servers = set(servers)
        if len(unique_servers) == 1 and None not in unique_servers:
            score += SERVER_MATCH_SCORE
            criteria['server_match'] = f"全員同じサーバー({servers[0]})"
        else:
            score += SERVER_PARTIAL_SCORE
            criteria['server_match'] = f"サーバーが一部異なる: {servers}"
    # 時間差スコア
    first_time = party[0][2]
    last_time = party[-1][2]
    time_diff = (last_time - first_time).total_seconds()
    if time_diff <= 60:
        score += TIME_SCORE_60
    elif time_diff <= 120:
        score += TIME_SCORE_120
    else:
        score += TIME_SCORE_OTHER
    criteria['time_proximity'] = f"{int(time_diff)}秒差"
    # サーバー名代表値
    server = servers[0] if servers and servers[0] is not None else None
    return score, criteria, server
