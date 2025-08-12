import asyncio
import logging

from lib.wynncraft_api import WynncraftAPI
from lib.db import get_linked_members_page, add_member, remove_member, get_member
from lib.discord_notify import notify_member_removed
from config import GUILD_NAME, RANK_ROLE_ID_MAP, ETKW, ROLE_ID_TO_RANK

logger = logging.getLogger(__name__)

async def fetch_guild_members(api: WynncraftAPI) -> dict:
    guild_data = await api.get_guild_by_prefix("ETKW")
    if not guild_data or 'members' not in guild_data:
        logger.warning("[MemberSync] ギルドAPI取得失敗")
        return {}
    members = {}
    for rank, rank_members in guild_data['members'].items():
        if rank == "total":
            continue
        for mcid in rank_members.keys():
            members[mcid] = rank.capitalize()
    return members

async def member_rank_sync_task(api: WynncraftAPI, bot=None):
    while True:
        try:
            logger.info("[MemberSync] ランク同期タスク開始")
            guild_members = await fetch_guild_members(api)
            if not guild_members:
                logger.warning("[MemberSync] APIからのギルドデータ取得失敗、同期処理をスキップ")
                await asyncio.sleep(120)
                continue
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
                        # ここからロール付与・ニックネーム変更
                        if bot and dbm.get('discord_id'):
                            for guild in bot.guilds:
                                member = guild.get_member(dbm['discord_id'])
                                if member:
                                    # 1. 旧ランクロール全削除（ROLE_ID_TO_RANKに含まれるもの全て）
                                    old_roles = [role for role in member.roles if role.id in ROLE_ID_TO_RANK]
                                    if old_roles:
                                        try:
                                            await member.remove_roles(*old_roles, reason="ランク同期: 旧ランクロール削除")
                                        except Exception as e:
                                            logger.error(f"[MemberSync] 旧ランクロール削除失敗: {e}")
                                    # 2. 新ランクロール付与
                                    new_role_id = RANK_ROLE_ID_MAP.get(api_rank)
                                    new_role = guild.get_role(new_role_id) if new_role_id else None
                                    if new_role:
                                        try:
                                            await member.add_roles(new_role, reason="ランク同期: 新ランクロール付与")
                                        except Exception as e:
                                            logger.error(f"[MemberSync] 新ランクロール付与失敗: {e}")
                                    # 3. ETKWロール付与（必要あれば）
                                    if ETKW:
                                        etkw_role = guild.get_role(ETKW)
                                        if etkw_role:
                                            try:
                                                await member.add_roles(etkw_role, reason="ランク同期: ETKWロール付与")
                                            except Exception as e:
                                                logger.error(f"[MemberSync] ETKWロール付与失敗: {e}")
                                    # 4. ニックネーム変更（ロール名から[]除去）
                                    # 新ランクロールのdisplay名をprefixに
                                    prefix = new_role.name if new_role else api_rank
                                    prefix = re.sub(r"\s*\[.*?]\s*", " ", prefix).strip()
                                    new_nick = f"{prefix} {mcid}"
                                    if len(new_nick) > 32:
                                        new_nick = new_nick[:32]
                                    try:
                                        if not member.guild_permissions.administrator:
                                            await member.edit(nick=new_nick, reason="ランク同期: ニックネーム更新")
                                    except Exception as e:
                                        logger.error(f"[MemberSync] ニックネーム更新失敗: {e}")
                                    break  # 該当guildで見つかったら終わり
                if page >= total_pages:
                    break
                page += 1
        except Exception as e:
            logger.error(f"[MemberSync] ランク同期で例外: {e}", exc_info=True)
        await asyncio.sleep(120)

async def member_remove_sync_task(bot, api: WynncraftAPI):
    while True:
        try:
            logger.info("[MemberSync] ギルド脱退検知タスク開始")
            guild_members = await fetch_guild_members(api)
            if not guild_members:
                logger.warning("[MemberSync] APIからのギルドデータ取得失敗、削除検知処理をスキップ")
                await asyncio.sleep(120)
                continue
            api_mcids = set(guild_members.keys())
            page = 1
            while True:
                db_members, total_pages = get_linked_members_page(page=page, per_page=50)
                if not db_members:
                    break
                for dbm in db_members:
                    mcid = dbm['mcid']
                    if mcid not in api_mcids:
                        # --- ゲーム脱退時のみロール削除 ---
                        if dbm.get('discord_id'):
                            for guild in bot.guilds:
                                member = guild.get_member(dbm['discord_id'])
                                if member:
                                    role_id = RANK_ROLE_ID_MAP.get(dbm.get('rank'))
                                    if role_id:
                                        role = guild.get_role(role_id)
                                        if role:
                                            try:
                                                await member.remove_roles(ETKW, reason="ゲーム脱退時連携ロール解除-デフォルト")
                                                await member.remove_roles(role, reason="ゲーム脱退時連携ロール解除‐ランク")
                                            except Exception as e:
                                                logger.error(f"ロール削除エラー: {e}")
                                    break
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
    bot.loop.create_task(member_rank_sync_task(api, bot))
    bot.loop.create_task(member_remove_sync_task(bot, api))
