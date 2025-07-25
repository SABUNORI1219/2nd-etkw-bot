import logging
from datetime import timedelta
from collections import defaultdict

logger = logging.getLogger(__name__)

SCORE_THRESHOLD = 85
TIME_WINDOW_MINUTES = 3
SERVER_MATCH_SCORE = 50
SERVER_PARTIAL_SCORE = 20
TIME_SCORE_60 = 50
TIME_SCORE_120 = 30
TIME_SCORE_OTHER = 10

def estimate_and_save_parties(clear_events):
    """
    個人クリアイベントリストからパーティ推定
    clear_events: [
        {
            "player": str,
            "raid_name": str,
            "clear_time": datetime,
            "server": Optional[str]
        }, ...
    ]
    Returns: List of party dicts
    """
    # レイドごとで分割
    events_by_raid = defaultdict(list)
    for event in clear_events:
        events_by_raid[event["raid_name"]].append(event)

    saved_parties = []
    for raid, events in events_by_raid.items():
        # 時刻順にソート
        events.sort(key=lambda x: x["clear_time"])
        # スライディングウィンドウで4人組を抽出
        for i in range(len(events) - 3):
            party_candidate = events[i:i+4]
            first_time = party_candidate[0]["clear_time"]
            last_time = party_candidate[-1]["clear_time"]
            # 追加: 同じplayerが複数名いる候補は除外
            member_names = [p["player"] for p in party_candidate]
            if len(set(member_names)) < 4:
                continue
            if (last_time - first_time) <= timedelta(minutes=TIME_WINDOW_MINUTES):
                score, criteria, server = _score_party(party_candidate)
                logger.info(
                    f"パーティ候補: レイド名: {raid} / メンバー: {member_names}, スコア: {score}, 詳細: {criteria}"
                )
                if score >= SCORE_THRESHOLD:
                    party = {
                        "raid_name": raid,
                        "clear_time": first_time,
                        "members": member_names,
                        "server": server,
                        "trust_score": score,
                        "criteria": criteria
                    }
                    saved_parties.append(party)
    return saved_parties

def _score_party(party):
    """
    party: [{player, raid_name, clear_time, server}, ...]の4人dictリスト
    サーバー一致度・時間差でスコアリング
    """
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
    # 時間差スコア
    first_time = party[0]["clear_time"]
    last_time = party[-1]["clear_time"]
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
