import logging
from datetime import timedelta

logger = logging.getLogger(__name__)

TRUST_SCORE_CONFIG = {
    "raid_match": 5,
    "server_match": 3,
    "time_window": 2,  # ±3分
    "threshold": 7
}

def estimate_party(clear_events):
    """
    clear_events: List of dicts
        [{ "player": "name", "raid_name": "...", "clear_time": datetime, "server": "AS4" }, ...]
    Returns: List of party dicts
    """
    parties = []
    checked = set()
    for i, a in enumerate(clear_events):
        if i in checked:
            continue
        party = [a]
        scores = [TRUST_SCORE_CONFIG["raid_match"]]  # a自身（raid一致は必須）
        for j, b in enumerate(clear_events):
            if i == j or j in checked:
                continue
            score = 0
            if a["raid_name"] != b["raid_name"]:
                score = 0
            else:
                score += TRUST_SCORE_CONFIG["raid_match"]
                if a["server"] == b["server"]:
                    score += TRUST_SCORE_CONFIG["server_match"]
                if abs((a["clear_time"] - b["clear_time"]).total_seconds()) <= 180:
                    score += TRUST_SCORE_CONFIG["time_window"]
            if score >= TRUST_SCORE_CONFIG["threshold"]:
                party.append(b)
                scores.append(score)
                checked.add(j)
        checked.add(i)
        if len(party) == 4:
            parties.append({
                "raid_name": a["raid_name"],
                "clear_time": min(x["clear_time"] for x in party),
                "members": [x["player"] for x in party],
                "server": a["server"],
                "trust_score": min(scores)  # 最低スコア
            })
            logger.info(f"【パーティ推定/4人】raid={a['raid_name']} server={a['server']} time={a['clear_time']} members={[x['player'] for x in party]}")
    return parties
