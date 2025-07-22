import json
from pathlib import Path
from datetime import datetime, timedelta

RAID_COUNT_PATH = Path("raid_counts.json")
GUILD_RAID_COUNT_PATH = Path("guild_raid_counts.json")
SERVER_LOG_PATH = Path("server_log.json")
CONFIG_PATH = Path("bot_config.json")
EXPIRE_MINUTES = 5

# --- 個人の全レイドクリアカウント(API比較用) ---
def load_counts():
    if RAID_COUNT_PATH.exists():
        with open(RAID_COUNT_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_counts(counts):
    with open(RAID_COUNT_PATH, "w", encoding="utf-8") as f:
        json.dump(counts, f, ensure_ascii=False, indent=2)

def set_player_count(player, raid, count):
    counts = load_counts()
    if player not in counts:
        counts[player] = {}
    counts[player][raid] = count
    save_counts(counts)

def get_player_count(player, raid):
    counts = load_counts()
    return counts.get(player, {}).get(raid, 0)

# --- ギルドレイドクリアカウント(推定成功時のみ加算) ---
def load_guild_counts():
    if GUILD_RAID_COUNT_PATH.exists():
        with open(GUILD_RAID_COUNT_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_guild_counts(counts):
    with open(GUILD_RAID_COUNT_PATH, "w", encoding="utf-8") as f:
        json.dump(counts, f, ensure_ascii=False, indent=2)

def add_guild_raid_clear(players, raid):
    counts = load_guild_counts()
    for player in players:
        if player not in counts:
            counts[player] = {}
        counts[player][raid] = counts[player].get(raid, 0) + 1
    save_guild_counts(counts)

def set_guild_player_count(player, raid, count):
    counts = load_guild_counts()
    if player not in counts:
        counts[player] = {}
    counts[player][raid] = count
    save_guild_counts(counts)

def get_guild_player_count(player, raid):
    counts = load_guild_counts()
    return counts.get(player, {}).get(raid, 0)

def get_all_guild_player_counts(raid=None):
    counts = load_guild_counts()
    result = {}
    for player, raids in counts.items():
        if raid:
            if raid in raids:
                result[player] = raids[raid]
        else:
            # 合計
            result[player] = sum(raids.values())
    return result

# --- サーバーログ管理 ---
def load_server_log():
    if SERVER_LOG_PATH.exists():
        with open(SERVER_LOG_PATH, "r", encoding="utf-8") as f:
            log = json.load(f)
        now = datetime.utcnow()
        expired = []
        for player, data in log.items():
            last_update = datetime.fromisoformat(data["last_update"])
            if now - last_update > timedelta(minutes=EXPIRE_MINUTES):
                expired.append(player)
        for player in expired:
            del log[player]
        if expired:
            with open(SERVER_LOG_PATH, "w", encoding="utf-8") as f:
                json.dump(log, f, ensure_ascii=False, indent=2)
        return log
    return {}

def save_server_log(log):
    with open(SERVER_LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)

def set_last_server(player, server):
    log = load_server_log()
    log[player] = {
        "last_server": server,
        "last_update": datetime.utcnow().isoformat()
    }
    save_server_log(log)

def get_last_server_before(player, event_time=None):
    log = load_server_log()
    entry = log.get(player)
    if entry:
        return entry["last_server"]
    return None

# --- 通知等の設定 ---
def load_config():
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_config(config):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

def set_config(key, value):
    config = load_config()
    config[key] = value
    save_config(config)

def get_config(key):
    config = load_config()
    return config.get(key)
