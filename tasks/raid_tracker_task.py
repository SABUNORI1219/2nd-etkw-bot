import asyncio
import logging
import time
from datetime import datetime
from lib.wynncraft_api import WynncraftAPI
from lib.db import insert_history, insert_server_log, cleanup_old_server_logs
from lib.party_estimator import estimate_and_save_parties
from lib.discord_notify import send_guild_raid_embed

logger = logging.getLogger(__name__)

# メモリ型で前回分を保持（uuidベース）
previous_player_data = dict()  # {uuid: {"raids": {...}, "server": ..., "timestamp": ..., "name": ...}}

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

async def get_player_data(api, uuid):
    # uuidでAPI取得、nameは後で紐づけ
    return await api.get_nori_player_data(uuid)  # 実装によっては引数調整

async def track_guild_raids(bot=None):
    api = WynncraftAPI()
    while True:
        logger.info("ETKWメンバー情報取得開始...")
        start_time = time.time()
        guild_data = await api.get_nori_guild_data("ETKW")
        if guild_data is None:
            logger.warning("guild_data取得失敗。10秒後に再試行します。")
            await asyncio.sleep(10)
            continue

        # online_members抽出（uuid・name・serverセット）
        online_members = extract_online_members(guild_data)
        
        if not online_members:
            logger.info("オンラインメンバーがいません。")
            await asyncio.sleep(60)
            continue
        
        # uuidベースでAPI取得
        player_tasks = [get_player_data(api, member["uuid"]) for member in online_members]
        player_results = await asyncio.gather(*player_tasks)
        
        clear_events = []
        now = datetime.utcnow()
        
        for member, pdata in zip(online_members, player_results):
            uuid = member["uuid"]
            name = member["name"]
            server = pdata.get("server") or member.get("server")
            raids = pdata.get("globalData", {}).get("raids", {}).get("list", {})
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
                if previous and delta > 0 and delta <= 4:
                    clear_events.append({
                        "player": name,
                        "raid_name": raid,
                        "clear_time": now,
                        "server": previous.get("server", server)
                    })
                    logger.info(f"{name}が{raid}をクリア: {prev_count}->{current_count} サーバー:{previous.get('server', server)}")
            previous_player_data[uuid] = {
                "raids": dict(raids),
                "server": server,
                "timestamp": now,
                "name": name
            }
        
        logger.info("ETKWメンバー情報取得完了！")
        # パーティ推定＆DB保存・通知
        parties = estimate_and_save_parties(clear_events)
        for party in parties:
            if party["trust_score"] < 85:
                logger.info(f"信頼スコア85未満のため履歴保存＆通知スキップ: {party}")
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

        await asyncio.to_thread(cleanup_old_server_logs, 5)        
        elapsed = time.time() - start_time
        sleep_time = max(60 - elapsed, 0)
        logger.info(f"次回まで{sleep_time:.1f}秒待機（処理時間: {elapsed:.1f}秒）")
        await asyncio.sleep(sleep_time)

async def setup(bot):
    bot.loop.create_task(track_guild_raids(bot))
