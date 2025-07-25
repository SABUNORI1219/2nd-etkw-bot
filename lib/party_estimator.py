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

def remove_events_from_window(window, party_candidate, time_threshold=300):
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
    to_exclude_events = []

    for raid, events in events_by_raid.items():
        events.sort(key=lambda x: x["clear_time"])
        for i in range(len(events) - 3):
            party_candidate = events[i:i+4]
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
            # --- 条件1: 5分以内＆全員同じサーバーは必ず認定 ---
            if (
                (last_time - first_time) <= timedelta(minutes=TIME_WINDOW_MINUTES)
                and len(set([p["server"] for p in party_candidate])) == 1
                and None not in set([p["server"] for p in party_candidate])
            ):
                if key not in party_keys:
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
                    continue  # 認定したら次へ
            # --- 条件2: 通常スコア判定 ---
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
            else:
                # スコア不足で認定できなかった場合はwindow除去対象に
                to_exclude_events.append((raid, party_candidate, first_time, last_time))

    # 認定できなかったパーティ候補のイベントをwindowから除去
    if window is not None:
        for raid, party_candidate, first_time, last_time in to_exclude_events:
            remove_events_from_window(window, party_candidate, time_threshold=300)

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
