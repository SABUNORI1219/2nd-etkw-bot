import asyncio
import logging

from lib.wynncraft_api import WynncraftAPI
from lib.db import get_linked_members_page, add_member, remove_member
from lib.discord_notify import notify_member_removed
from config import GUILD_NAME

logger = logging.getLogger(__name__)

async def fetch_guild_members(api: WynncraftAPI) -> dict:
    """
    Wynncraft Guild APIから全メンバーを「MCID→Rank」のdictで返す
    """
    guild_data = await api.get_guild_by_prefix("ETKW")
    if not guild_data or 'members' not in guild_data:
        logger.warning("[MemberSync] ギルドAPI取得失敗")
        return {}
    members = {}
    for rank, rank_members in guild_data['members'].items():
        if rank == "total":
            continue
        for mcid in rank_members.keys():  # ←ここを修正
            members[mcid] = rank.capitalize()
    return members

async def member_rank_sync_task(api: WynncraftAPI):
    """
    APIのランク情報でDBのメンバーランクを自動同期（通知不要）
    """
    while True:
        try:
            logger.info("[MemberSync] ランク同期タスク開始")
            guild_members = await fetch_guild_members(api)
            page = 1
            while True:
                db_members, total_pages = get_linked_members_page(page=page, per_page=50)
                if not db_members:
                    break
                for dbm in db_members:
                    mcid = dbm['mcid']
                    db_rank = dbm['rank']
                    api_rank = guild_members.get(mcid)
                    if api_rank and api_rank != db_rank:
                        add_member(mcid, dbm['discord_id'], api_rank)
                        logger.info(f"[MemberSync] {mcid} ランク {db_rank}→{api_rank} で更新")
                if page >= total_pages:
                    break
                page += 1
        except Exception as e:
            logger.error(f"[MemberSync] ランク同期で例外: {e}", exc_info=True)
        await asyncio.sleep(120)

async def member_remove_sync_task(bot, api: WynncraftAPI):
    """
    APIのメンバーリストでDBから消すべき人を検知し、通知＆DB削除
    """
    while True:
        try:
            logger.info("[MemberSync] ギルド脱退検知タスク開始")
            guild_members = await fetch_guild_members(api)
            api_mcids = set(guild_members.keys())
            page = 1
            while True:
                db_members, total_pages = get_linked_members_page(page=page, per_page=50)
                if not db_members:
                    break
                for dbm in db_members:
                    mcid = dbm['mcid']
                    if mcid not in api_mcids:
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
    api = WynncraftAPI()
    bot.loop.create_task(member_rank_sync_task(api))
    bot.loop.create_task(member_remove_sync_task(bot, api))
