import logging
from collections import defaultdict

logger = logging.getLogger(__name__)

SCORE_THRESHOLD = 50  # 時間条件を削除したので閾値を下げる
MAX_LOOP_DIFFERENCE = 3  # 3ループ以内

SERVER_ALL_MATCH_SCORE = 50
SERVER_PARTIAL_SCORE = 0

# 時間関連のスコアは削除（ループベースに変更）

def _round_time(dt):
    return dt.replace(microsecond=0)

def remove_events_from_window(window, party_candidate, time_threshold=500):
    # party_candidateに含まれるイベントをwindowから除去
    to_remove = []
    candidate_names = set(p["player"] for p in party_candidate)
    raid_name = party_candidate[0]["raid_name"]
    candidate_loops = [p.get("loop_number", 0) for p in party_candidate]
    
    for e in window:
        if (
            e["raid_name"] == raid_name
            and e["player"] in candidate_names
            and e.get("loop_number", 0) in candidate_loops
        ):
            to_remove.append(e)
    for e in to_remove:
        try:
            window.remove(e)
        except ValueError:
            pass

def is_valid_party_by_loops(party_candidate):
    """ループ番号で3ループ以内かどうか判定"""
    loop_numbers = [event.get("loop_number", 0) for event in party_candidate]
    if not loop_numbers:
        return False
    
    min_loop = min(loop_numbers)
    max_loop = max(loop_numbers)
    loop_difference = max_loop - min_loop
    
    return loop_difference <= MAX_LOOP_DIFFERENCE

def estimate_and_save_parties(clear_events, window=None):
    events_by_raid = defaultdict(list)
    for event in clear_events:
        events_by_raid[event["raid_name"]].append(event)

    saved_parties = []
    party_keys = set()
    window_set = set(id(e) for e in window) if window is not None else set()

    for raid, events in events_by_raid.items():
        events.sort(key=lambda x: x["clear_time"])

        # 1. サーバー単位でグループ化してパーティ認定を優先
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
                
                if len(member_set) < 4:
                    continue
                
                # ループ番号による判定
                if not is_valid_party_by_loops(party_candidate):
                    continue
                    
                score, criteria, _ = _score_party(party_candidate)
                rounded_time = _round_time(first_time)
                key = (raid, rounded_time, member_set)
                
                if key not in party_keys:
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
        
        # 2. サーバー混在グループは、残りイベントで通常スコア判定
        # windowから既に除去されたイベントは対象外
        remaining_events = [e for e in events if window is None or id(e) in window_set]
        for i in range(len(remaining_events) - 3):
            party_candidate = remaining_events[i:i+4]
            member_names = [p["player"] for p in party_candidate]
            member_set = frozenset(member_names)
            first_time = min([p["clear_time"] for p in party_candidate])
            
            if len(member_set) < 4:
                continue
            
            # ループ番号による判定
            if not is_valid_party_by_loops(party_candidate):
                continue
                
            score, criteria, server = _score_party(party_candidate)
            loop_info = f"ループ差: {max([p.get('loop_number', 0) for p in party_candidate]) - min([p.get('loop_number', 0) for p in party_candidate])}"
            logger.info(
                f"パーティ候補: レイド名: {raid} / メンバー: {member_names}, スコア: {score}, 詳細: {criteria}, {loop_info}"
            )
            rounded_time = _round_time(first_time)
            key = (raid, rounded_time, member_set)
            
            if score >= SCORE_THRESHOLD and key not in party_keys:
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

    return saved_parties

def _score_party(party):
    servers = [p["server"] for p in party]
    criteria = {}
    score = 0
    unique_servers = set(servers)
    
    # サーバー一致スコア
    if len(unique_servers) == 1 and None not in unique_servers:
        score += SERVER_ALL_MATCH_SCORE
        criteria['server_match'] = f"全員同じサーバー({servers[0]})"
    else:
        score += SERVER_PARTIAL_SCORE
        criteria['server_match'] = f"サーバーが一致しない: {servers}"

    # ループ差による追加スコア（3ループ以内は既に確認済み）
    loop_numbers = [p.get("loop_number", 0) for p in party]
    min_loop = min(loop_numbers)
    max_loop = max(loop_numbers)
    loop_difference = max_loop - min_loop
    
    if loop_difference == 0:
        criteria['loop_proximity'] = "同一ループ"
    elif loop_difference == 1:
        criteria['loop_proximity'] = "1ループ差"
    elif loop_difference == 2:
        criteria['loop_proximity'] = "2ループ差"
    else:
        criteria['loop_proximity'] = f"{loop_difference}ループ差"

    server = servers[0] if servers and servers[0] is not None else None
    return score, criteria, server
