import logging
from datetime import timedelta
from collections import defaultdict

logger = logging.getLogger(__name__)

SCORE_THRESHOLD = 80
TIME_WINDOW_MINUTES = 3
SERVER_MATCH_SCORE = 50
SERVER_PARTIAL_SCORE = 20
TIME_SCORE_60 = 50
TIME_SCORE_120 = 30
TIME_SCORE_OTHER = 10

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
    if len(servers) == 4:
        unique_servers = set(servers)
        if len(unique_servers) == 1 and None not in unique_servers:
            score += SERVER_MATCH_SCORE
            criteria['server_match'] = f"全員同じサーバー({servers[0]})"
        else:
            score += SERVER_PARTIAL_SCORE
            criteria['server_match'] = f"サーバーが一部異なる: {servers}"
    first_time = min([p["clear_time"] for p in party])
    last_time = max([p["clear_time"] for p in party])
    time_diff = (last_time - first_time).total_seconds()
    if time_diff <= 60:
        score += TIME_SCORE_60
    elif time_diff <= 120:
        score += TIME_SCORE_120
    else:
        score += TIME_SCORE_OTHER
    criteria['time_proximity'] = f"{int(time_diff)}秒差"
    server = servers[0] if servers and servers[0] is not None else None
    return score, criteria, server
