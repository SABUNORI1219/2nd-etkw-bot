import asyncio
import logging
from datetime import datetime, timedelta, timezone
from collections import defaultdict

from lib.wynncraft_api import WynncraftAPI
from lib.db import upsert_guild_territory_state, get_guild_territory_state

logger = logging.getLogger(__name__)

# この変数はプロセス内キャッシュとして利用し、DBに永続化する
# {guild_prefix: {territory_name: {"acquired": datetime, "lost": datetime | None}}}
guild_territory_history = defaultdict(dict)

def _dt_to_str(dt):
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()

def _str_to_dt(dtstr):
    if dtstr is None:
        return None
    if isinstance(dtstr, datetime):
        return dtstr
    # 末尾Zあり/なし両対応
    return datetime.fromisoformat(dtstr.replace("Z", "+00:00"))

def get_effective_owned_territories(guild_prefix, current_time=None):
    """
    指定ギルドの「現在所有＋直近1時間以内に奪われた」領地名セットを返す
    """
    if current_time is None:
        current_time = datetime.now(timezone.utc)
    result = set()
    for tname, info in guild_territory_history[guild_prefix].items():
        lost_time = info.get("lost")
        if lost_time is None:
            result.add(tname)
        elif (current_time - lost_time) <= timedelta(hours=1):
            result.add(tname)
    return result

def get_current_owned_territories(guild_prefix):
    """
    指定ギルドの現時点で所有している領地名セットを返す
    """
    return {tname for tname, info in guild_territory_history[guild_prefix].items() if info.get("lost") is None}

def get_territory_held_time(guild_prefix, territory_name, now=None):
    """
    領地取得日時からの保持期間（秒）を返す
    """
    info = guild_territory_history[guild_prefix].get(territory_name)
    if not info or not info.get("acquired"):
        return 0
    if info.get("lost"):
        return int((info["lost"] - info["acquired"]).total_seconds())
    if not now:
        now = datetime.now(timezone.utc)
    return int((now - info["acquired"]).total_seconds())

def sync_history_from_db():
    """
    DBの永続データをguild_territory_historyにロード
    """
    global guild_territory_history
    db_state = get_guild_territory_state()
    guild_territory_history.clear()
    for g, tdict in db_state.items():
        for t, info in tdict.items():
            acquired = _str_to_dt(info.get("acquired"))
            lost = _str_to_dt(info.get("lost"))
            guild_territory_history[g][t] = {"acquired": acquired, "lost": lost}

async def track_guild_territories(loop_interval=60):
    """
    1分ごとに全領地データを取得し、guild_territory_historyとDBに履歴を反映し続ける
    """
    api = WynncraftAPI()
    # 起動時にDBから復元
    sync_history_from_db()
    while True:
        now = datetime.now(timezone.utc)
        logger.info("[GuildTerritoryTracker] 領地データの取得を開始します...")
        territory_data = await api.get_territory_list()
        if not territory_data:
            logger.warning("[GuildTerritoryTracker] 領地データ取得失敗。10秒後に再試行します。")
            await asyncio.sleep(10)
            continue

        # guildごとに現在所有を整理
        current_guild_territories = defaultdict(set)
        for tname, tinfo in territory_data.items():
            prefix = tinfo["guild"]["prefix"]
            if prefix:
                current_guild_territories[prefix].add(tname)

        # 履歴更新処理
        for guild_prefix, curr_territories in current_guild_territories.items():
            hist = guild_territory_history[guild_prefix]
            # 消失判定
            for tname in list(hist.keys()):
                if tname not in curr_territories and hist[tname].get("lost") is None:
                    hist[tname]["lost"] = now
            # 新規取得 or 継続所有
            for tname in curr_territories:
                if tname in hist:
                    # 継続所有
                    if hist[tname].get("lost"):
                        # 1時間以内に奪われていた→再取得扱い
                        if (now - hist[tname]["lost"]) <= timedelta(hours=1):
                            hist[tname]["lost"] = None
                        else:
                            hist[tname] = {"acquired": now, "lost": None}
                else:
                    # 新規取得
                    hist[tname] = {"acquired": now, "lost": None}

        # 1時間以上前に失領したものは履歴から削除
        for guild_prefix in list(guild_territory_history.keys()):
            hist = guild_territory_history[guild_prefix]
            for tname in list(hist.keys()):
                lost_at = hist[tname].get("lost")
                if lost_at and (now - lost_at) > timedelta(hours=1):
                    del hist[tname]
            if not hist:
                del guild_territory_history[guild_prefix]

        # DBへ永続化
        upsert_guild_territory_state(guild_territory_history)
        logger.info(f"[GuildTerritoryTracker] 領地履歴キャッシュ＆DB永続化: {len(guild_territory_history)} ギルド")
        await asyncio.sleep(loop_interval)

async def setup(bot):
    bot.loop.create_task(track_guild_territories(loop_interval=60))
