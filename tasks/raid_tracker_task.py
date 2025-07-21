import asyncio
import logging
import time
from datetime import datetime
from lib.wynncraft_api import WynncraftAPI
from lib.db import insert_history, get_prev_count, set_prev_count, insert_server_log, get_last_server_before, cleanup_old_server_logs
from lib.party_estimator import estimate_and_save_parties
from lib.discord_notify import send_guild_raid_embed

logger = logging.getLogger(__name__)

# 同時実行数40に制限
semaphore = asyncio.Semaphore(120)

async def get_player_data(api, name):
    async with semaphore:
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
        # 同時実行数制限付き並列で各メンバーのデータ取得
        player_tasks = [get_player_data(api, name) for name in members]
        player_results = await asyncio.gather(*player_tasks)
        # 各メンバーのレイドクリア数取得
        clear_events = []
        now = datetime.utcnow()
        # 事前に全員分DBから前回クリア数をまとめて取得
        prev_counts = {}  # {(name, raid): prev_count}
        for name in members:
            # レイドごとに
            for raid in [
                "The Canyon Colossus",
                "Orphion's Nexus of Light",
                "The Nameless Anomaly",
                "Nest of the Grootslangs"
            ]:
                prev_counts[(name, raid)] = await asyncio.to_thread(get_prev_count, name, raid)
        # クリアイベント判定・DBバルク書き込みリスト
        set_prev_count_calls = []
        for name, pdata in player_results:
            server = pdata.get("server")
            await asyncio.to_thread(insert_server_log, name, now, server)
            raids = pdata.get("globalData", {}).get("raids", {}).get("list", {})
            for raid in [
                "The Canyon Colossus",
                "Orphion's Nexus of Light",
                "The Nameless Anomaly",
                "Nest of the Grootslangs"
            ]:
                current_count = raids.get(raid, 0)
                prev_count = prev_counts[(name, raid)]
                # 未挑戦または0クリアはスキップ
                if prev_count is None or prev_count == 0:
                    if raid not in raids or current_count == 0:
                        continue
                    set_prev_count_calls.append((name, raid, current_count))
                    logger.info(f"初回DB保存: {name} {raid} -> {current_count}")
                    continue
                # 異常な増加は無視
                delta = current_count - prev_count
                if delta <= 0 or delta > 4:
                    set_prev_count_calls.append((name, raid, current_count))
                    continue
                if current_count > prev_count:
                    # クリア増加イベント（全員now基準で統一）
                    prev_server = await asyncio.to_thread(get_last_server_before, name, now)
                    clear_events.append({
                        "player": name,
                        "raid_name": raid,
                        "clear_time": now,
                        "server": prev_server
                    })
                    logger.info(f"{name}が{raid}をクリア: {prev_count}->{current_count} サーバー:{prev_server}")
                set_prev_count_calls.append((name, raid, current_count))
        # 増加分のみまとめてDB保存
        for name, raid, count in set_prev_count_calls:
            await asyncio.to_thread(set_prev_count, name, raid, count)
        logger.info("ETKWメンバー情報取得完了！")
        # パーティ推定＆保存
        parties = estimate_and_save_parties(clear_events)
        for party in parties:
            if party["trust_score"] < 85:
                logger.info(f"信頼スコア85の未満のため履歴保存＆通知スキップ: {party}")
                continue
            await asyncio.to_thread(
                insert_history,
                party["raid_name"],
                party["clear_time"],
                party["members"],
                party["server"],
                party["trust_score"]
            )
            # Discord通知（パーティ推定ごとに即送信）
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
