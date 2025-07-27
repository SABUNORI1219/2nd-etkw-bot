import logging
from datetime import timedelta
from collections import defaultdict

logger = logging.getLogger(__name__)

SCORE_THRESHOLD = 80
TIME_WINDOW_MINUTES = 5

SERVER_ALL_MATCH_SCORE = 50
SERVER_PARTIAL_SCORE = 0

TIME_ALL_MATCH_SCORE = 50
TIME_30_SEC_SCORE = 40
TIME_60_SEC_SCORE = 30
TIME_120_SEC_SCORE = 20
TIME_300_SEC_SCORE = 10
TIME_OTHER_SCORE = 0

def _round_time(dt):
    return dt.replace(microsecond=0)

def remove_events_from_window(window, party_candidate, time_threshold=500):
    # party_candidateに含まれるイベントをwindowから除去（5分＝300秒以内）
    to_remove = []
    candidate_names = set(p["player"] for p in party_candidate)
    raid_name = party_candidate[0]["raid_name"]
    times = [p["clear_time"] for p in party_candidate]
    min_time = min(times)
    max_time = max(times)
    for e in window:
        if (
            e["raid_name"] == raid_name
            and e["player"] in candidate_names
            and min_time <= e["clear_time"] <= max_time
        ):
            to_remove.append(e)
    for e in to_remove:
        try:
            window.remove(e)
        except ValueError:
            pass

def estimate_and_save_parties(clear_events, window=None):
    events_by_raid = defaultdict(list)
    for event in clear_events:
        events_by_raid[event["raid_name"]].append(event)

    saved_parties = []
    party_keys = set()
    window_set = set(id(e) for e in window) if window is not None else set()  # eventのidで管理

    # 追加: サーバーごと・時間ごとのグループ化を優先
    for raid, events in events_by_raid.items():
        events.sort(key=lambda x: x["clear_time"])

        # --- 1. サーバー単位でグループ化してパーティ認定を優先 ---
        server_events = defaultdict(list)
        for e in events:
            server_events[e["server"]].append(e)
        for server, s_events in server_events.items():
            if server is None:
                continue
            s_events.sort(key=lambda x: x["clear_time"])
            for i in range(len(s_events) - 3):
                party_candidate = s_events[i:i+4]
                member_names = [p["player"] for p in party_candidate]
                member_set = frozenset(member_names)
                first_time = min([p["clear_time"] for p in party_candidate])
                last_time = max([p["clear_time"] for p in party_candidate])
                if len(member_set) < 4:
                    continue
                score, criteria, _ = _score_party(party_candidate)
                rounded_time = _round_time(first_time)
                key = (raid, rounded_time, member_set)
                if (
                    (last_time - first_time) <= timedelta(minutes=TIME_WINDOW_MINUTES)
                    and key not in party_keys
                ):
                    # サーバー一致グループは強制的に認定
                    party_keys.add(key)
                    party = {
                        "raid_name": raid,
                        "clear_time": first_time,
                        "members": sorted(member_set),
                        "server": server,
                        "trust_score": score,
                        "criteria": criteria
                    }
                    saved_parties.append(party)
                    # 認定イベントのみwindowから除去
                    if window is not None:
                        remove_events_from_window(window, party_candidate, time_threshold=500)
        # --- 2. サーバー混在グループは、残りイベントで通常スコア判定 ---
        # windowから既に除去されたイベントは対象外
        remaining_events = [e for e in events if window is None or id(e) in window_set]
        for i in range(len(remaining_events) - 3):
            party_candidate = remaining_events[i:i+4]
            member_names = [p["player"] for p in party_candidate]
            member_set = frozenset(member_names)
            first_time = min([p["clear_time"] for p in party_candidate])
            last_time = max([p["clear_time"] for p in party_candidate])
            if len(member_set) < 4:
                continue
            score, criteria, server = _score_party(party_candidate)
            logger.info(
                f"パーティ候補: レイド名: {raid} / メンバー: {member_names}, スコア: {score}, 詳細: {criteria}"
            )
            rounded_time = _round_time(first_time)
            key = (raid, rounded_time, member_set)
            if (last_time - first_time) <= timedelta(minutes=TIME_WINDOW_MINUTES) and score >= SCORE_THRESHOLD and key not in party_keys:
                party_keys.add(key)
                party = {
                    "raid_name": raid,
                    "clear_time": first_time,
                    "members": sorted(member_set),
                    "server": server,
                    "trust_score": score,
                    "criteria": criteria
                }
                saved_parties.append(party)
                if window is not None:
                    remove_events_from_window(window, party_candidate, time_threshold=500)
            # 認定されなかった場合もwindowから除外しない（イベントを残す）

    return saved_parties

def _score_party(party):
    servers = [p["server"] for p in party]
    criteria = {}
    score = 0
    unique_servers = set(servers)
    if len(unique_servers) == 1 and None not in unique_servers:
        score += SERVER_ALL_MATCH_SCORE
        criteria['server_match'] = f"全員同じサーバー({servers[0]})"
    else:
        score += SERVER_PARTIAL_SCORE
        criteria['server_match'] = f"サーバーが一致しない: {servers}"

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
    elif time_diff <= 300:
        score += TIME_300_SEC_SCORE
        criteria['time_proximity'] = f"{int(time_diff)}秒差（5分以内）"
    else:
        score += TIME_OTHER_SCORE
        criteria['time_proximity'] = f"{int(time_diff)}秒差（遠い）"

    server = servers[0] if servers and servers[0] is not None else None
    return score, criteria, server
