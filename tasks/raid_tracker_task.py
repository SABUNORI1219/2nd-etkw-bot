import asyncio
import logging
import time
from datetime import datetime
from collections import deque
from lib.api_stocker import WynncraftAPI
from lib.db import insert_history, insert_server_log, cleanup_old_server_logs, upsert_last_join_cache, upsert_playtime_cache, get_last_join_cache_for_members, get_playtime_cache_for_members, get_recently_active_members, update_multiple_member_uuids, cleanup_non_guild_members_raid_history, update_raid_history_member_names
from lib.party_estimator import estimate_and_save_parties
from lib.discord_notify import send_guild_raid_embed

logger = logging.getLogger(__name__)

# メモリ型で前回分を保持（uuidベース）
previous_player_data = dict()

# 直近3ループ分のクリアイベントを保持
clear_events_window = deque(maxlen=200)

# ループカウンター（パーティ推定で使用）
current_loop_number = 0

def extract_online_members(guild_data):
    """オンラインメンバーを取得"""
    ranks = ["owner", "chief", "strategist", "captain", "recruiter", "recruit"]
    online_members = []
    for rank in ranks:
        for name, member_info in guild_data["members"].get(rank, {}).items():
            if member_info.get("online"):
                online_members.append({
                    "uuid": member_info["uuid"],
                    "name": name,
                    "server": member_info.get("server"),
                    "source": "online"  # データソースを識別
                })
    return online_members

def get_tracking_members(guild_data, recently_active_threshold_minutes=20):
    """
    トラッキング対象メンバーを取得
    オンラインメンバー + 最近アクティブなメンバー（重複除去）
    """
    # オンラインメンバーを取得
    online_members = extract_online_members(guild_data)
    online_uuids = set(member["uuid"] for member in online_members)
    
    # 最近アクティブなメンバーを取得
    recently_active = get_recently_active_members(recently_active_threshold_minutes)
    
    # ギルドデータからUUID→メンバー情報のマッピングを作成
    uuid_to_member = {}
    for rank, members in guild_data["members"].items():
        if not isinstance(members, dict):
            continue
        for name, member_info in members.items():
            uuid = member_info.get("uuid")
            if uuid:
                uuid_to_member[uuid] = {
                    "uuid": uuid,
                    "name": name,
                    "server": member_info.get("server"),
                    "rank": rank
                }
    
    # 最近アクティブなメンバーでオンラインでない人を追加
    tracking_members = online_members.copy()
    added_count = 0
    
    for mcid, uuid in recently_active:
        if uuid and uuid not in online_uuids:
            member_info = uuid_to_member.get(uuid)
            if member_info:
                member_info["source"] = "recently_active"
                tracking_members.append(member_info)
                added_count += 1
    
    logger.info(f"トラッキング対象: オンライン {len(online_members)}人 + 最近アクティブ {added_count}人 = 合計 {len(tracking_members)}人")
    return tracking_members

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

async def get_player_data(api, uuid, member_name=None):
    # DEBUG: API検索対象をログ出力（デバッグ用）
    logger.info(f"[DEBUG-レイドトラック] {member_name or 'Unknown'} -> 検索対象: UUID({uuid})")
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

def cleanup_old_events(window, max_loop_age=6):
    """古いループのイベントを削除（現在のループから6ループ以上古いものを削除）"""
    global current_loop_number
    while window and (current_loop_number - window[0].get("loop_number", 0)) > max_loop_age:
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
            logger.error(f"[get_player_info] {mcid}: {repr(e)}")
            return None
    
    # データ取得
    results = []
    for i in range(0, len(mcid_uuid_list), batch_size):
        batch = mcid_uuid_list[i:i+batch_size]
        batch_results = await asyncio.gather(*(get_player_info(mcid, uuid) for mcid, uuid in batch))
        results.extend(batch_results)
        
        # 最後のバッチでない場合はスリープ
        if i + batch_size < len(mcid_uuid_list):
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
            
            # DEBUG: playtime差分をログ出力
            if mcid == "sabunori1219":  # 特定のユーザーのみデバッグ
                logger.info(f"[DEBUG-lastJoin] {mcid}: lastJoin変更 {prev_lastjoin} -> {last_join}, playtime差分: {playtime_diff}")
            
            # playtimeが0.15以上増加している場合、または初回記録の場合にlastJoinを更新
            if prev_lastjoin is None or playtime_diff >= 0.15:
                lastjoin_updates.append((mcid, last_join))
                if mcid == "sabunori1219":  # 特定のユーザーのみデバッグ
                    logger.info(f"[DEBUG-lastJoin] {mcid}: lastJoin更新対象に追加")
        else:
            # lastJoinが同じ場合は更新しない
            if mcid == "sabunori1219":  # 特定のユーザーのみデバッグ
                logger.info(f"[DEBUG-lastJoin] {mcid}: lastJoin変更なし ({last_join})")
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
    global current_loop_number
    
    while True:
        current_loop_number += 1
        start_time = time.time()
        try:
            logger.debug("ETKWメンバー情報取得開始...")
            guild_data = await api.get_guild_by_prefix(guild_prefix)
            if guild_data is None:
                logger.warning("guild_data取得失敗。10秒後に再試行します。")
                await asyncio.sleep(10)
                continue
    
            # オンラインメンバー + 最近アクティブなメンバーを取得（15分以内に調整）
            logger.info(f"[DEBUG-トラッキング] 最近アクティブ判定しきい値: 15分前")
            tracking_members = await asyncio.to_thread(get_tracking_members, guild_data, 15)
            if not tracking_members:
                logger.info("トラッキング対象メンバーがいません。")
                elapsed = time.time() - start_time
                logger.info(f"Guild Raid Trackerタスク完了（処理時間: {elapsed:.1f}秒）")
                await asyncio.sleep(loop_interval)
                continue
    
            player_tasks = [get_player_data(api, member["uuid"], member["name"]) for member in tracking_members]
            player_results = await asyncio.gather(*player_tasks)
    
            clear_events = []
            now = datetime.utcnow()
    
            for member, pdata in zip(tracking_members, player_results):
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
                            "server": previous.get("server", server),
                            "loop_number": current_loop_number  # ループ番号を追加
                        }
                        if not is_duplicate_event(event, clear_events_window) and not is_duplicate_event(event, clear_events):
                            clear_events.append(event)
                            source_info = f"({member.get('source', 'unknown')})"
                            logger.info(f"{name}が{raid}をクリア: {prev_count}->{current_count} サーバー:{previous.get('server', server)} {source_info}")
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
    
            cleanup_old_events(clear_events_window, max_loop_age=6)
    
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
        
        # UUIDをlinked_membersテーブルに更新
        uuid_updates = [(mcid, uuid) for mcid, uuid in mcid_uuid_list if uuid is not None]
        if uuid_updates:
            await asyncio.to_thread(update_multiple_member_uuids, uuid_updates)
        
        await get_all_players_lastjoin_and_playtime(api, mcid_uuid_list, batch_size=3, batch_sleep=2.0)

        # ギルドレイド履歴のクリーンアップ処理
        try:
            # 現在のギルドメンバーのUUIDリストを作成
            current_guild_uuids = [uuid for mcid, uuid in mcid_uuid_list if uuid is not None]
            
            # UUID→現在の名前のマッピングを作成
            uuid_to_name_mapping = {}
            for rank, members in guild_data["members"].items():
                if isinstance(members, dict):
                    for current_name, member_info in members.items():
                        uuid = member_info.get("uuid")
                        if uuid:
                            uuid_to_name_mapping[uuid] = current_name
            
            # 1. 名前変更されたメンバーのレイド履歴更新（先にやる）
            updated_count = await asyncio.to_thread(update_raid_history_member_names, uuid_to_name_mapping)
            
            # 2. ギルド外メンバーのレイド履歴削除（後にやる）
            deleted_count = await asyncio.to_thread(cleanup_non_guild_members_raid_history, current_guild_uuids)
            
            if deleted_count > 0 or updated_count > 0:
                logger.info(f"[レイド履歴クリーンアップ] 削除: {deleted_count}件, 名前更新: {updated_count}件")
        except Exception as e:
            logger.error(f"[レイド履歴クリーンアップ] 処理中にエラー: {e}")

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
