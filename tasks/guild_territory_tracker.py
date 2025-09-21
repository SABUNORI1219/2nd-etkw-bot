import asyncio
import logging
from datetime import datetime, timedelta, timezone
from collections import defaultdict

from lib.api_stocker import WynncraftAPI
from lib.db import upsert_guild_territory_state, get_guild_territory_state

logger = logging.getLogger(__name__)

guild_territory_history = defaultdict(dict)

latest_territory_data = {}

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
        if dtstr.tzinfo is None:
            return dtstr.replace(tzinfo=timezone.utc)
        return dtstr
    dt = datetime.fromisoformat(dtstr.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt

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
        else:
            if lost_time.tzinfo is None:
                lost_time = lost_time.replace(tzinfo=timezone.utc)
            if (current_time - lost_time) <= timedelta(hours=1):
                result.add(tname)
    return result

def get_current_owned_territories(guild_prefix):
    return {tname for tname, info in guild_territory_history[guild_prefix].items() if info.get("lost") is None}

def get_territory_held_time(guild_prefix, territory_name, now=None):
    info = guild_territory_history[guild_prefix].get(territory_name)
    if not info or not info.get("acquired"):
        return 0
    acquired = info.get("acquired")
    if acquired and acquired.tzinfo is None:
        acquired = acquired.replace(tzinfo=timezone.utc)
    if info.get("lost"):
        lost = info.get("lost")
        if lost and lost.tzinfo is None:
            lost = lost.replace(tzinfo=timezone.utc)
        return int((lost - acquired).total_seconds())
    if not now:
        now = datetime.now(timezone.utc)
    return int((now - acquired).total_seconds())

def sync_history_from_db():
    global guild_territory_history
    db_state = get_guild_territory_state()
    guild_territory_history.clear()
    for g, tdict in db_state.items():
        for t, info in tdict.items():
            acquired = _str_to_dt(info.get("acquired"))
            lost = _str_to_dt(info.get("lost"))
            guild_territory_history[g][t] = {"acquired": acquired, "lost": lost}

async def track_guild_territories(loop_interval=60):
    api = WynncraftAPI()
    sync_history_from_db()
    while True:
        now = datetime.now(timezone.utc)
        logger.info("[GuildTerritoryTracker] 領地データの取得を開始します...")
        territory_data = await api.get_territory_list()
        if not territory_data:
            logger.warning("[GuildTerritoryTracker] 領地データ取得失敗。10秒後に再試行します。")
            await asyncio.sleep(10)
        else:
            global latest_territory_data
            latest_territory_data = territory_data

        current_guild_territories = defaultdict(set)
        for tname, tinfo in territory_data.items():
            prefix = tinfo["guild"]["prefix"]
            if prefix:
                current_guild_territories[prefix].add(tname)

        all_territory_names = set(territory_data.keys())
        territory_to_current_guild = {}
        for guild_prefix, terrs in current_guild_territories.items():
            for t in terrs:
                if t in territory_to_current_guild:
                    logger.warning(f"[GuildTerritoryTracker] 領地 {t} が複数ギルド({territory_to_current_guild[t]}, {guild_prefix})で同時所有状態")
                territory_to_current_guild[t] = guild_prefix

        # 修正: APIから消えた領地もlost付与して履歴に残す（1時間以内はDBにも残す）
        for g in list(guild_territory_history.keys()):
            hist = guild_territory_history[g]
            for tname in list(hist.keys()):
                current_owner = territory_to_current_guild.get(tname)
                if current_owner:
                    if current_owner != g:
                        if hist[tname].get("lost") is None:
                            hist[tname]["lost"] = now
                            hist[tname]["from_guild"] = g
                            hist[tname]["to_guild"] = current_owner
                else:
                    # APIから消えている場合もlost付与
                    if hist[tname].get("lost") is None:
                        hist[tname]["lost"] = now
                        hist[tname]["from_guild"] = g
                        hist[tname]["to_guild"] = None
                    # 履歴自体は1時間以内は残す（1時間超で消す）

        # 履歴更新処理（新規取得 or 継続所有）
        for guild_prefix, curr_territories in current_guild_territories.items():
            hist = guild_territory_history[guild_prefix]
            for tname in curr_territories:
                if tname in hist:
                    if hist[tname].get("lost"):
                        lost_time = hist[tname]["lost"]
                        if lost_time and lost_time.tzinfo is None:
                            lost_time = lost_time.replace(tzinfo=timezone.utc)
                        if (now - lost_time) <= timedelta(hours=1):
                            hist[tname]["lost"] = None
                        else:
                            hist[tname] = {"acquired": now, "lost": None}
                else:
                    hist[tname] = {"acquired": now, "lost": None}

        # 1時間以上前に失領したものだけ履歴から削除する
        for guild_prefix in list(guild_territory_history.keys()):
            hist = guild_territory_history[guild_prefix]
            for tname in list(hist.keys()):
                lost_at = hist[tname].get("lost")
                if lost_at:
                    if lost_at.tzinfo is None:
                        lost_at = lost_at.replace(tzinfo=timezone.utc)
                    if (now - lost_at) > timedelta(hours=1):
                        del hist[tname]
            if not hist:
                del guild_territory_history[guild_prefix]

        upsert_guild_territory_state(guild_territory_history)
        logger.info(f"[GuildTerritoryTracker] 領地履歴キャッシュ＆DB永続化: {len(guild_territory_history)} ギルド")
        await asyncio.sleep(loop_interval)

async def setup(bot):
    bot.loop.create_task(track_guild_territories(loop_interval=60))
