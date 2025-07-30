import asyncio
import logging
from datetime import datetime, timezone

from lib.wynncraft_api import WynncraftAPI
from lib.db import get_linked_members_page, get_member, add_member, remove_member
from lib.discord_notify import notify_member_removed  # 実装予定: ギルド脱退時の通知用

from config import GUILD_NAME

logger = logging.getLogger(__name__)

# ギルドAPIから全メンバー情報を取得
async def fetch_guild_members():
    api = WynncraftAPI()
    guild_data = await api.get_guild_by_prefix(GUILD_NAME.split()[-1])
    if not guild_data or 'members' not in guild_data:
        logger.warning("[MemberSync] ギルドAPI取得失敗")
        return {}
    # {mcid: rank}
    members = {}
    for rank, mcids in guild_data['members'].items():
        if rank == "total": continue
        for mcid in mcids:
            members[mcid] = rank.capitalize()
    return members

async def member_rank_sync_task():
    """ギルドAPIのランク情報でDBのメンバーランクを自動同期（通知不要）"""
    while True:
        try:
            logger.info("[MemberSync] ランク同期タスク開始")
            guild_members = await fetch_guild_members()
            # DB全メンバーをページ順で取得
            page = 1
            while True:
                db_members, total_pages = get_linked_members_page(page=page, per_page=50)
                if not db_members:
                    break
                for dbm in db_members:
                    mcid = dbm['mcid']
                    db_rank = dbm['rank']
                    api_rank = guild_members.get(mcid)
                    # ランクがAPI側と異なれば更新
                    if api_rank and api_rank != db_rank:
                        # Discord IDは変えない
                        add_member(mcid, dbm['discord_id'], api_rank)
                        logger.info(f"[MemberSync] {mcid} ランク {db_rank}→{api_rank} で更新")
                if page >= total_pages:
                    break
                page += 1
        except Exception as e:
            logger.error(f"[MemberSync] ランク同期で例外: {e}", exc_info=True)
        await asyncio.sleep(120)

async def member_remove_sync_task(bot):
    """ギルドAPIのメンバーリストでDBから消すべき人を検知し、通知＆DB削除"""
    while True:
        try:
            logger.info("[MemberSync] ギルド脱退検知タスク開始")
            guild_members = await fetch_guild_members()
            api_mcids = set(guild_members.keys())
            # DB全メンバーをページ順で取得
            page = 1
            while True:
                db_members, total_pages = get_linked_members_page(page=page, per_page=50)
                if not db_members:
                    break
                for dbm in db_members:
                    mcid = dbm['mcid']
                    if mcid not in api_mcids:
                        # ギルドから抜けている
                        # 通知（lib.discord_notify.notify_member_removedを呼ぶ設計）
                        await notify_member_removed(bot, dbm)
                        logger.info(f"[MemberSync] {mcid} がギルドから脱退→DBから削除")
                        remove_member(mcid=mcid)
                if page >= total_pages:
                    break
                page += 1
        except Exception as e:
            logger.error(f"[MemberSync] ギルド脱退検知で例外: {e}", exc_info=True)
        await asyncio.sleep(120)

async def setup(bot):
    bot.loop.create_task(member_rank_sync_task())
    bot.loop.create_task(member_remove_sync_task(bot, loop_interval=120))
