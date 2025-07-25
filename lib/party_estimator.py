import logging
from datetime import timedelta
from collections import defaultdict

logger = logging.getLogger(__name__)

SCORE_THRESHOLD = 80
TIME_WINDOW_MINUTES = 3

# サーバー一致度を細かく
SERVER_ALL_MATCH_SCORE = 50
SERVER_THREE_MATCH_SCORE = 35
SERVER_TWO_MATCH_SCORE = 20
SERVER_PARTIAL_SCORE = 10

# 時間差スコア
TIME_ALL_MATCH_SCORE = 50
TIME_30_SEC_SCORE = 40
TIME_60_SEC_SCORE = 30
TIME_120_SEC_SCORE = 10
TIME_OTHER_SCORE = 0

def _round_time(dt):
    # 秒単位で丸める
    return dt.replace(microsecond=0)

def estimate_and_save_parties(clear_events):
    events_by_raid = defaultdict(list)
    for event in clear_events:
        events_by_raid[event["raid_name"]].append(event)

    saved_parties = []
    party_keys = set()

    for raid, events in events_by_raid.items():
        events.sort(key=lambda x: x["clear_time"])
        for i in range(len(events) - 3):
            party_candidate = events[i:i+4]
            member_names = [p["player"] for p in party_candidate]
            # パーティ重複防止：順序無視でメンバーセット化
            member_set = frozenset(member_names)
            # 時間差判定
            first_time = min([p["clear_time"] for p in party_candidate])
            last_time = max([p["clear_time"] for p in party_candidate])
            if len(member_set) < 4:
                continue
            if (last_time - first_time) <= timedelta(minutes=TIME_WINDOW_MINUTES):
                score, criteria, server = _score_party(party_candidate)
                logger.info(
                    f"パーティ候補: レイド名: {raid} / メンバー: {member_names}, スコア: {score}, 詳細: {criteria}"
                )
                # --- 強化重複排除 ---
                rounded_time = _round_time(first_time)
                key = (raid, rounded_time, member_set)
                if score >= SCORE_THRESHOLD and key not in party_keys:
                    party_keys.add(key)
                    party = {
                        "raid_name": raid,
                        "clear_time": first_time,
                        "members": sorted(member_set),  # 順序安定化
                        "server": server,
                        "trust_score": score,
                        "criteria": criteria
                    }
                    saved_parties.append(party)
    return saved_parties

def _score_party(party):
    servers = [p["server"] for p in party]
    criteria = {}
    score = 0
    # サーバー一致度
    unique_servers = set(servers)
    same_server_count = max([servers.count(s) for s in unique_servers]) if servers else 0
    if len(unique_servers) == 1 and None not in unique_servers:
        score += SERVER_ALL_MATCH_SCORE
        criteria['server_match'] = f"全員同じサーバー({servers[0]})"
    elif same_server_count == 3:
        score += SERVER_THREE_MATCH_SCORE
        criteria['server_match'] = f"3人同じサーバー({servers})"
    elif same_server_count == 2:
        score += SERVER_TWO_MATCH_SCORE
        criteria['server_match'] = f"2人同じサーバー({servers})"
    else:
        score += SERVER_PARTIAL_SCORE
        criteria['server_match'] = f"サーバーがバラバラ: {servers}"

    # クリア時間の近さ
    times = [p["clear_time"] for p in party]
    min_time = min(times)
    max_time = max(times)
    time_diff = (max_time - min_time).total_seconds()
    if time_diff == 0:
        score += TIME_ALL_MATCH_SCORE
        criteria['time_proximity'] = "全員同時"
    elif time_diff <= 30:
        score += TIME_30_SEC_SCORE
        criteria['time_proximity'] = f"{int(time_diff)}秒差（30秒以内）"
    elif time_diff <= 60:
        score += TIME_60_SEC_SCORE
        criteria['time_proximity'] = f"{int(time_diff)}秒差（60秒以内）"
    elif time_diff <= 120:
        score += TIME_120_SEC_SCORE
        criteria['time_proximity'] = f"{int(time_diff)}秒差（120秒以内）"
    else:
        score += TIME_OTHER_SCORE
        criteria['time_proximity'] = f"{int(time_diff)}秒差（遠い）"

    server = servers[0] if servers and servers[0] is not None else None
    return score, criteria, server
