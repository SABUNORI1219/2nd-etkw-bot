import asyncio
import logging
from datetime import datetime
from lib.wynncraft_api import WynncraftAPI
from lib.db import insert_history, get_prev_count, set_prev_count
from lib.party_estimator import estimate_party

logger = logging.getLogger(__name__)

# メモリ上に前回値を保持
prev_raid_counts = {}

async def track_guild_raids():
    api = WynncraftAPI()
    while True:
        logger.info("ETKWメンバー情報取得開始")
        guild_data = await api.get_nori_guild_data("ETKW")
        members = []
        # 各ランクごと走査
        for section in guild_data["members"].values():
            if isinstance(section, dict):
                for name, info in section.items():
                    members.append(name)
        # 各メンバーのレイドクリア数取得
        clear_events = []
        for name in members:
            pdata = await api.get_nori_player_data(name)
            # 主要レイドのみ
            raids = pdata.get("globalData", {}).get("raids", {}).get("list", {})
            raid_types = ["The Canyon Colossus", "Orphion's Nexus of Light", "The Nameless Anomaly", "Nest of the Grootslangs"]
            for raid in raid_types:
                current_count = raids.get(raid, 0)
                prev_count = get_prev_count(name, raid)
                if prev_count is None:
                    set_prev_count(name, raid, current_count)
                    continue
                # 異常な増加は無視（例：減った/0から大ジャンプ/+10以上）
                delta = current_count - prev_count
                if delta <= 0 or delta > 4:
                    set_prev_count(name, raid, current_count)
                    continue
                if current_count > prev_count:
                    # クリア増加イベント
                    clear_time = datetime.utcnow()
                    server = pdata.get("server")
                    clear_events.append({
                        "player": name,
                        "raid_name": raid,
                        "clear_time": clear_time,
                        "server": server
                    })
                    logger.info(f"{name}が{raid}をクリア: {prev_count}->{current_count} サーバー:{server}")
                prev_raid_counts[(name, raid)] = current_count
                set_prev_count(name, raid, current_count)
        # パーティ推定＆保存
        parties = estimate_party(clear_events)
        for party in parties:
            insert_history(
                party["raid_name"],
                party["clear_time"],
                party["members"],
                party["server"],
                party["trust_score"]
            )
            # 通知タスクに渡す（後述）
        await asyncio.sleep(120)

async def setup(bot):
    bot.loop.create_task(track_guild_raids())
