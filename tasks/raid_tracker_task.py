import asyncio
import logging
import time
from datetime import datetime
from collections import deque
from lib.api_stocker import WynncraftAPI
from lib.db import insert_history, insert_server_log, cleanup_old_server_logs, upsert_last_join_cache, upsert_playtime_cache, get_last_join_cache_for_members, get_playtime_cache_for_members
from lib.party_estimator import estimate_and_save_parties
from lib.discord_notify import send_guild_raid_embed

logger = logging.getLogger(__name__)

# メモリ型で前回分を保持（uuidベース）
previous_player_data = dict()

# 直近3ループ分のクリアイベントを保持
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

async def get_all_players_lastjoin_and_playtime(api, mcid_uuid_list, batch_size=5, batch_sleep=1.5):
    """
    プレイヤーのlastJoinとplaytimeを取得し、条件に応じてlastJoinのみ更新
    """
    async def get_player_info(mcid, uuid):
        try:
            player_data = await api.get_official_player_data(uuid or mcid)
            if player_data:
                last_join = player_data.get("lastJoin")
                playtime = player_data.get("playtime", 0)
                return (mcid, last_join, playtime)
            else:
                return None
        except Exception as e:
            logger.error(f"[get_player_info] {mcid}: {repr(e)}", exc_info=True)
            return None
    
    # データ取得
    results = []
    for i in range(0, len(mcid_uuid_list), batch_size):
        batch = mcid_uuid_list[i:i+batch_size]
        batch_results = await asyncio.gather(*(get_player_info(mcid, uuid) for mcid, uuid in batch))
        results.extend(batch_results)
        await asyncio.sleep(batch_sleep)
    
    # フィルタリング
    valid_results = [r for r in results if r is not None and r[1] is not None]
    if not valid_results:
        return
    
    # 現在のキャッシュデータを取得
    mcid_list = [r[0] for r in valid_results]
    previous_lastjoin = get_last_join_cache_for_members(mcid_list)
    previous_playtime = get_playtime_cache_for_members(mcid_list)
    
    # 更新対象を決定
    lastjoin_updates = []
    playtime_updates = []
    
    for mcid, last_join, playtime in valid_results:
        # playtimeは常に更新
        playtime_updates.append((mcid, playtime))
        
        # lastJoinの更新判定
        prev_lastjoin = previous_lastjoin.get(mcid)
        prev_playtime = previous_playtime.get(mcid, 0)
        
        # 前回のlastJoinと異なる場合のみチェック
        if prev_lastjoin != last_join:
            playtime_diff = playtime - prev_playtime
            
            # playtimeが0.16以上増加している場合、または初回記録の場合にlastJoinを更新
            if prev_lastjoin is None or playtime_diff >= 0.16:
                lastjoin_updates.append((mcid, last_join))
                logger.info(f"[LastJoin更新] {mcid}: playtime差={playtime_diff:.2f}時間")
            else:
                logger.debug(f"[LastJoin更新スキップ] {mcid}: playtime差={playtime_diff:.2f}時間 (0.16未満)")
        else:
            # lastJoinが同じ場合は更新しない
            logger.debug(f"[LastJoin変更なし] {mcid}")
    
    # データベース更新
    if playtime_updates:
        upsert_playtime_cache(playtime_updates)
        logger.info(f"playtime更新: {len(playtime_updates)}件")
    
    if lastjoin_updates:
        upsert_last_join_cache(lastjoin_updates)
        logger.info(f"lastJoin更新: {len(lastjoin_updates)}件")
    else:
        logger.info("lastJoin更新対象なし")

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
        await get_all_players_lastjoin_and_playtime(api, mcid_uuid_list, batch_size=3, batch_sleep=4)

        elapsed = time.time() - start_time
        logger.info(f"Last Seen Trackerタスク完了（処理時間: {elapsed:.1f}秒）")

        MAX_PLAYER_DATA_AGE = 12 * 60 * 60  # 12時間
        now = datetime.utcnow()
        for uuid, pdata in list(previous_player_data.items()):
            ts = pdata.get("timestamp")
            if ts and (now - ts).total_seconds() > MAX_PLAYER_DATA_AGE:
                del previous_player_data[uuid]
        
        await asyncio.sleep(loop_interval)

async def setup(bot):
    api = WynncraftAPI()
    bot.loop.create_task(guild_raid_tracker(api, bot, loop_interval=120))
    bot.loop.create_task(last_seen_tracker(api, loop_interval=120))
