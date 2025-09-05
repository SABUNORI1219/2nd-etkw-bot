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

async def guild_raid_tracker(api, bot=None, guild_prefix="ETKW", loop_interval=120):
    logger.info("Guild Raid Trackerタスク開始")
    while True:
        start_time = time.time()
        try:
            logger.debug("ETKWメンバー情報取得開始...")
            guild_data = await api.get_guild_by_prefix(guild_prefix)
            if guild_data is None:
                logger.warning("guild_data取得失敗。10秒後に再試行します。")
                await asyncio.sleep(10)
                continue
    
            online_members = extract_online_members(guild_data)
            if not online_members:
                logger.info("オンラインメンバーがいません。")
                elapsed = time.time() - start_time
                logger.info(f"Guild Raid Trackerタスク完了（処理時間: {elapsed:.1f}秒）")
                await asyncio.sleep(loop_interval)
                continue
    
            player_tasks = [get_player_data(api, member["uuid"]) for member in online_members]
            player_results = await asyncio.gather(*player_tasks)
    
            clear_events = []
            now = datetime.utcnow()
    
            for member, pdata in zip(online_members, player_results):
                uuid = member["uuid"]
                name = member["name"]
                if pdata is None:
                    continue
                server = pdata.get("server") or member.get("server")
                raids = pdata.get("globalData", {}).get("raids", {}).get("list", {})
                if not raids or len(raids) == 0:
                    continue
                previous = previous_player_data.get(uuid)
                await asyncio.to_thread(insert_server_log, name, now, server)
                for raid in [
                    "The Canyon Colossus",
                    "Orphion's Nexus of Light",
                    "The Nameless Anomaly",
                    "Nest of the Grootslangs"
                ]:
                    current_count = raids.get(raid, 0)
                    prev_count = previous["raids"].get(raid, 0) if previous else 0
                    delta = current_count - prev_count
                    if previous and delta == 1:
                        event = {
                            "player": name,
                            "raid_name": raid,
                            "clear_time": now,
                            "server": previous.get("server", server)
                        }
                        if not is_duplicate_event(event, clear_events_window) and not is_duplicate_event(event, clear_events):
                            clear_events.append(event)
                            logger.info(f"{name}が{raid}をクリア: {prev_count}->{current_count} サーバー:{previous.get('server', server)}")
                previous_player_data[uuid] = {
                    "raids": dict(raids),
                    "server": server,
                    "timestamp": now,
                    "name": name
                }
            logger.debug("ETKWメンバー情報取得完了！")
    
            for event in clear_events:
                if not is_duplicate_event(event, clear_events_window):
                    clear_events_window.append(event)
    
            cleanup_old_events(clear_events_window, max_age_sec=500)
    
            parties = estimate_and_save_parties(list(clear_events_window), window=clear_events_window)
            for party in parties:
                for member in party["members"]:
                    logger.info(f"insert_history呼び出し: {party['raid_name']} {party['clear_time']} {member}")
                    await asyncio.to_thread(
                        insert_history,
                        party["raid_name"],
                        party["clear_time"],
                        member
                    )
                logger.info(f"send_guild_raid_embed呼び出し: {party}")
                if bot is not None:
                    try:
                        await send_guild_raid_embed(bot, party)
                    except Exception as e:
                        logger.error(f"通知Embed送信失敗: {e}")
                remove_party_events_from_window(clear_events_window, party, time_threshold=2)
            await asyncio.to_thread(cleanup_old_server_logs, 5)
    
            elapsed = time.time() - start_time
            logger.info(f"Guild Raid Trackerタスク完了（処理時間: {elapsed:.1f}秒）")
        except Exception as e:
            logger.error(f"Guild Raid Trackerで例外発生: {repr(e)}", exc_info=True)
        await asyncio.sleep(loop_interval)

async def last_seen_tracker(api, guild_prefix="ETKW", loop_interval=120):
    logger.info("Last Seen Trackerタスク開始")
    while True:
        start_time = time.time()
        guild_data = await api.get_guild_by_prefix(guild_prefix)
        if guild_data is None:
            logger.warning("guild_data取得失敗。10秒後に再試行します。")
            await asyncio.sleep(10)
            continue

        mcid_uuid_list = await get_all_mcid_and_uuid_from_guild(guild_data)
        results = await get_all_players_lastjoin(api, mcid_uuid_list)
        await asyncio.to_thread(upsert_last_join_cache, results)

        elapsed = time.time() - start_time
        logger.info(f"Last Seen Trackerタスク完了（処理時間: {elapsed:.1f}秒）")
        await asyncio.sleep(loop_interval)

async def setup(bot):
    api = WynncraftAPI()
    bot.loop.create_task(guild_raid_tracker(api, bot, loop_interval=120))
    bot.loop.create_task(last_seen_tracker(api, loop_interval=120))
