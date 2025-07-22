import asyncio
import logging
import time
from datetime import datetime
from lib.wynncraft_api import WynncraftAPI
from lib.json_store import (
    set_player_count, get_player_count,
    set_last_server, get_last_server_before,
    add_guild_raid_clear
)
from lib.party_estimator import estimate_and_save_parties
from lib.discord_notify import send_guild_raid_embed

logger = logging.getLogger(__name__)

async def get_player_data(api, name):
    return name, await api.get_nori_player_data(name)

async def track_guild_raids(bot=None):
    api = WynncraftAPI()
    while True:
        logger.info("ETKWメンバー情報取得開始...")
        start_time = time.time()
        guild_data = await api.get_nori_guild_data("ETKW")
        members = []
        for section in guild_data["members"].values():
            if isinstance(section, dict):
                for name, info in section.items():
                    members.append(name)
        player_tasks = [get_player_data(api, name) for name in members]
        player_results = await asyncio.gather(*player_tasks)
        clear_events = []
        now = datetime.utcnow()
        for name, pdata in player_results:
            server = pdata.get("server")
            set_last_server(name, server)
            raids = pdata.get("globalData", {}).get("raids", {}).get("list", {})
            for raid in [
                "The Canyon Colossus",
                "Orphion's Nexus of Light",
                "The Nameless Anomaly",
                "Nest of the Grootslangs"
            ]:
                current_count = raids.get(raid, 0)
                prev_count = get_player_count(name, raid)
                if current_count > prev_count:
                    prev_server = get_last_server_before(name)
                    for _ in range(current_count - prev_count):
                        clear_events.append({
                            "player": name,
                            "raid_name": raid,
                            "clear_time": now,
                            "server": prev_server
                        })
                    logger.info(f"{name}が{raid}をクリア: {prev_count}->{current_count} サーバー:{prev_server}")
                set_player_count(name, raid, current_count)
        logger.info("ETKWメンバー情報取得完了！")
        # パーティ推定＆ギルドレイド記録
        parties = estimate_and_save_parties(clear_events)
        for party in parties:
            if party["trust_score"] < 85:
                logger.info(f"信頼スコア85未満のため通知スキップ: {party}")
                continue
            # ギルドレイド認定前
            if len(set(party['members'])) == 4:
                # 4人全員異なる場合のみギルドレイド成立
                add_guild_raid_clear(party['members'], party['raid_name'])
                logger.info(f"send_guild_raid_embed呼び出し: {party}")
            else:
                # 同一名が含まれている場合はスキップ（無視）
                continue
            if bot is not None:
                try:
                    await send_guild_raid_embed(bot, party)
                except Exception as e:
                    logger.error(f"通知Embed送信失敗: {e}")

        elapsed = time.time() - start_time
        sleep_time = max(60 - elapsed, 0)
        logger.info(f"次回まで{sleep_time:.1f}秒待機（処理時間: {elapsed:.1f}秒）")
        await asyncio.sleep(sleep_time)

async def setup(bot):
    bot.loop.create_task(track_guild_raids(bot))
