import asyncio
import logging
import time
from datetime import datetime
from collections import deque
from lib.api_stocker import WynncraftAPI
from lib.db import insert_history, insert_server_log, cleanup_old_server_logs, upsert_last_join_cache
from lib.party_estimator import estimate_and_save_parties
from lib.discord_notify import send_guild_raid_embed

logger = logging.getLogger(__name__)

# メモリ型で前回分を保持（uuidベース）
previous_player_data = dict()  # {uuid: {"raids": {...}, "server": ..., "timestamp": ..., "name": ...}}

# 直近3ループ分のクリアイベントを保持（30人×3ループ＝90件程度。最大200件に余裕を持たせる）
clear_events_window = deque(maxlen=200)

def extract_online_members(guild_data):
    ranks = ["owner", "chief", "strategist", "captain", "recruiter", "recruit"]
    online_members = []
    for rank in ranks:
        for name, member_info in guild_data["members"].get(rank, {}).items():
            if member_info.get("online"):
                online_members.append({
                    "uuid": member_info["uuid"],
                    "name": name,
                    "server": member_info.get("server")
                })
    return online_members

def remove_party_events_from_window(window, party, time_threshold=2):
    to_remove = []
    for e in window:
        if (
            e["raid_name"] == party["raid_name"] and
            e["player"] in party["members"] and
            abs((e["clear_time"] - party["clear_time"]).total_seconds()) < time_threshold
        ):
            to_remove.append(e)
    for e in to_remove:
        try:
            window.remove(e)
        except ValueError:
            pass

async def get_player_data(api, uuid):
    return await api.get_official_player_data(uuid)

def is_duplicate_event(event, window, threshold_sec=2):
    for e in window:
        if (
            e["player"] == event["player"] and
            e["raid_name"] == event["raid_name"] and
            abs((e["clear_time"] - event["clear_time"]).total_seconds()) < threshold_sec
        ):
            return True
    return False

def cleanup_old_events(window, max_age_sec=500):
    now = datetime.utcnow()
    while window and (now - window[0]["clear_time"]).total_seconds() > max_age_sec:
        window.popleft()

async def get_all_mcid_and_uuid_from_guild(guild_data):
    mcid_uuid_list = []
    for rank, members in guild_data["members"].items():
        if not isinstance(members, dict):
            continue
        for mcid, info in members.items():
            uuid = info.get("uuid")
            if uuid:
                mcid_uuid_list.append((mcid, uuid))
            else:
                mcid_uuid_list.append((mcid, None))
    return mcid_uuid_list

async def get_all_players_lastjoin(api, mcid_uuid_list, batch_size=5, batch_sleep=1.5):
    async def get_lastjoin(mcid, uuid):
        try:
            player_data = await api.get_official_player_data(uuid or mcid)
            if player_data and "lastJoin" in player_data:
                return (mcid, player_data["lastJoin"])
            else:
                return None
        except Exception as e:
            logger.error(f"[get_lastjoin] {mcid}: {repr(e)}", exc_info=True)
            return None
    results = []
    for i in range(0, len(mcid_uuid_list), batch_size):
        batch = mcid_uuid_list[i:i+batch_size]
        batch_results = await asyncio.gather(*(get_lastjoin(mcid, uuid) for mcid, uuid in batch))
        results.extend(batch_results)
        await asyncio.sleep(batch_sleep)
    # Noneを除外
    return [r for r in results if r is not None]

async def track_guild_raids(bot=None, loop_interval=600):
    api = WynncraftAPI()
    while True:
        logger.info("ETKWメンバー情報取得開始...")
        start_time = time.time()
        guild_data = await api.get_guild_by_prefix("ETKW")
        if guild_data is None:
            logger.warning("guild_data取得失敗。10秒後に再試行します。")
            await asyncio.sleep(10)
            continue

        # --- 全メンバーのlastJoinを個別APIで取得しキャッシュDBへ ---
        mcid_uuid_list = await get_all_mcid_and_uuid_from_guild(guild_data)
        results = await get_all_players_lastjoin(api, mcid_uuid_list)
        await asyncio.to_thread(upsert_last_join_cache, results)
        # --- ここまで ---
        
        elapsed = time.time() - start_time
        sleep_time = max(loop_interval - elapsed, 0)
        logger.info(f"次回まで{sleep_time:.1f}秒待機（処理時間: {elapsed:.1f}秒）")
        await asyncio.sleep(sleep_time)

async def setup(bot):
    bot.loop.create_task(track_guild_raids(bot, loop_interval=600))
