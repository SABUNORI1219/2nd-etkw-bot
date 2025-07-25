import asyncio
import logging
import time
from datetime import datetime
from collections import deque
from lib.wynncraft_api import WynncraftAPI
from lib.db import insert_history, insert_server_log, cleanup_old_server_logs
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
    """
    windowからpartyに該当するクリアイベントを除去
    - party: {"raid_name", "clear_time", "members"}
    - time_threshold: clear_time一致判定の許容秒数
    """
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
            pass  # 既に消えてた場合

async def get_player_data(api, uuid):
    # uuidでAPI取得、nameは後で紐づけ
    return await api.get_nori_player_data(uuid)

def is_duplicate_event(event, window, threshold_sec=2):
    """window内にほぼ同時刻・同じplayer・同じraidのイベントがあるか判定"""
    for e in window:
        if (
            e["player"] == event["player"] and
            e["raid_name"] == event["raid_name"] and
            abs((e["clear_time"] - event["clear_time"]).total_seconds()) < threshold_sec
        ):
            return True
    return False

def cleanup_old_events(window, max_age_sec=500):
    """windowからmax_age_secより前のイベントを除去"""
    now = datetime.utcnow()
    # dequeの先頭から古いイベントを削除
    while window and (now - window[0]["clear_time"]).total_seconds() > max_age_sec:
        window.popleft()

async def track_guild_raids(bot=None, loop_interval=120):
    api = WynncraftAPI()
    while True:
        logger.info("ETKWメンバー情報取得開始...")
        start_time = time.time()
        guild_data = await api.get_guild_by_prefix("ETKW")
        if guild_data is None:
            logger.warning("guild_data取得失敗。10秒後に再試行します。")
            await asyncio.sleep(10)
            continue

        # online_members抽出（uuid・name・serverセット）
        online_members = extract_online_members(guild_data)
        
        if not online_members:
            logger.info("オンラインメンバーがいません。")
            await asyncio.sleep(loop_interval)
            continue
        
        # uuidベースでAPI取得
        player_tasks = [get_player_data(api, member["uuid"]) for member in online_members]
        player_results = await asyncio.gather(*player_tasks)
        
        clear_events = []
        now = datetime.utcnow()

        # クリアイベント抽出
        for member, pdata in zip(online_members, player_results):
            uuid = member["uuid"]
            name = member["name"]
            server = pdata.get("server") or member.get("server")
            raids = pdata.get("globalData", {}).get("raids", {}).get("list", {})
            previous = previous_player_data.get(uuid)
            logger.info(f"API raids for {name}: {raids}")
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
                    # 重複排除（window＋同ループ内）
                    if not is_duplicate_event(event, clear_events_window) and not is_duplicate_event(event, clear_events):
                        clear_events.append(event)
                        logger.info(f"{name}が{raid}をクリア: {prev_count}->{current_count} サーバー:{previous.get('server', server)}")
            previous_player_data[uuid] = {
                "raids": dict(raids),
                "server": server,
                "timestamp": now,
                "name": name
            }
        logger.info(f"previous_player_data[{uuid}]: {previous_player_data.get(uuid)}")
        
        logger.info("ETKWメンバー情報取得完了！")

        # windowに今回のイベントを追加（重複排除）
        for event in clear_events:
            if not is_duplicate_event(event, clear_events_window):
                clear_events_window.append(event)

        # 100秒より前のイベントをwindowから除去
        cleanup_old_events(clear_events_window, max_age_sec=500)

        # パーティ推定＆DB保存・通知（window全体を渡す）
        parties = estimate_and_save_parties(list(clear_events_window))
        for party in parties:
            if party["trust_score"] < 70:
                logger.info(f"信頼スコア70未満のため履歴保存＆通知スキップ: {party}")
                continue
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

            # --- party通知後にwindowから該当イベント除去 ---
            remove_party_events_from_window(clear_events_window, party, time_threshold=2)

        # サーバーログのクリーンアップ（4分保持）
        await asyncio.to_thread(cleanup_old_server_logs, 5)
        elapsed = time.time() - start_time
        sleep_time = max(loop_interval - elapsed, 0)
        logger.info(f"次回まで{sleep_time:.1f}秒待機（処理時間: {elapsed:.1f}秒）")
        await asyncio.sleep(sleep_time)

async def setup(bot):
    bot.loop.create_task(track_guild_raids(bot, loop_interval=120))
