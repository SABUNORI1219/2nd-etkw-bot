import discord
import asyncio
import logging
import re
from discord.ext import tasks

from lib.api_stocker import WynncraftAPI
from lib.db import get_linked_members_page, add_member, remove_member, get_member, get_pending_applications, delete_application_by_discord_id
from lib.discord_notify import notify_member_removed
from config import RANK_ROLE_ID_MAP, ETKW, ROLE_ID_TO_RANK

logger = logging.getLogger(__name__)

GUILD_ID = 1158535340110381157
ROLE_ID = 1415107839076335616
LOG_CHANNEL_ID = 1249352336401236011

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
                        # ロール付与・ニックネーム変更
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
                        # --- ゲーム脱退時のみロール削除・ニックネームリセット ---
                        if dbm.get('discord_id'):
                            for guild in bot.guilds:
                                member = guild.get_member(dbm['discord_id'])
                                if member:
                                    # ランクロール削除
                                    roles_to_remove = [role for role in member.roles if role.id in ROLE_ID_TO_RANK]
                                    if roles_to_remove:
                                        try:
                                            await member.remove_roles(*roles_to_remove, reason="ゲーム脱退時ランクロール削除")
                                        except Exception as e:
                                            logger.error(f"ゲーム脱退時ランクロール削除エラー: {e}")
                                    # ETKWロール削除
                                    if ETKW:
                                        etkw_role = guild.get_role(ETKW)
                                        if etkw_role:
                                            try:
                                                await member.remove_roles(etkw_role, reason="ゲーム脱退時ETKWロール削除")
                                            except Exception as e:
                                                logger.error(f"ゲーム脱退時ETKWロール削除エラー: {e}")
                                    # ニックネームリセット
                                    try:
                                        if not member.guild_permissions.administrator:
                                            await member.edit(nick=None, reason="ゲーム脱退時ニックネームリセット")
                                    except Exception as e:
                                        logger.error(f"ゲーム脱退時ニックネームリセット失敗: {e}")
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

async def member_application_sync_task(bot, api: WynncraftAPI):
    while True:
        try:
            logger.info("[ApplicationSync] 申請者のギルド加入チェック開始")
            ingame_members = await fetch_guild_members(api)
            if not ingame_members:
                logger.warning("[ApplicationSync] APIからのギルドデータ取得失敗、同期処理をスキップ")
                await asyncio.sleep(60) # 2分
                continue

            guild = bot.get_guild(GUILD_ID)
            log_channel = bot.get_channel(LOG_CHANNEL_ID)

            for mcid, discord_id, channel_id in get_pending_applications():
                if mcid in ingame_members:
                    api_rank = ingame_members.get(mcid)
                    member = guild.get_member(discord_id)
                    if member is not None:
                        # データベース登録
                        success = add_member(mcid, discord_id, api_rank)
                        if not success:
                            logger.error(f"[member_sync_core_logic] add_member failed: {mcid}, {discord_id}, {api_rank}")
                            return False
                    
                        # 2. 新ランクロール付与
                        new_role_id = RANK_ROLE_ID_MAP.get(api_rank)
                        new_role = guild.get_role(new_role_id) if new_role_id else None
                        if new_role:
                            try:
                                await member.add_roles(new_role, reason="ランク同期: ランクロール付与")
                            except Exception as e:
                                logger.error(f"[ApplicationSync] ランクロール付与失敗: {e}")
                    
                        # 3. ETKWロール付与
                        if ETKW:
                            etkw_role = guild.get_role(ETKW)
                            if etkw_role:
                                try:
                                    await member.add_roles(etkw_role, reason="ランク同期: ETKWロール付与")
                                except Exception as e:
                                    logger.error(f"[ApplicationSync] ETKWロール付与失敗: {e}")
                    
                        # 4. ニックネーム変更
                        prefix = new_role.name if new_role else api_rank
                        prefix = re.sub(r"\s*\[.*?]\s*", " ", prefix).strip()
                        new_nick = f"{prefix} {mcid}"
                        if len(new_nick) > 32:
                            new_nick = new_nick[:32]
                        try:
                            if not member.guild_permissions.administrator:
                                await member.edit(nick=new_nick, reason="ランク同期: ニックネーム更新")
                        except Exception as e:
                            logger.error(f"[ApplicationSync] ニックネーム更新失敗: {e}")
                    
                    app_channel = bot.get_channel(channel_id)
                    if app_channel:
                        try:
                            # --- 申請Embedから内容を抽出 ---
                            embed_data = {
                                "reason": None,
                                "prev_guild": None,
                                "profile": None,
                                "user_guide": None,
                            }
                            async for msg in app_channel.history(limit=20, oldest_first=True):
                                for embed in msg.embeds:
                                    t = embed.title or ""
                                    if "理由" in t:
                                        embed_data["reason"] = embed.description
                                    elif "過去ギルド" in t or "Previous Guild" in t:
                                        embed_data["prev_guild"] = embed.description
                                    elif "プレイヤー情報" in t or "Player Info" in t:
                                        embed_data["profile"] = embed
                                    elif "ご案内" in t or "Welcome" in t:
                                        embed_data["user_guide"] = embed
                            # ログ用Embedを生成
                            log_embed = discord.Embed(
                                title="Guild 加入申請ログ/Application Log",
                                color=discord.Color.blue(),
                                description=f"**申請者:** <@{discord_id}>\n**MCID:** `{mcid}`"
                            )
                            if embed_data["reason"]:
                                log_embed.add_field(name="加入理由/Reason", value=embed_data["reason"], inline=False)
                            if embed_data["prev_guild"]:
                                log_embed.add_field(name="過去ギルド/Previous Guild", value=embed_data["prev_guild"], inline=False)
                            log_embed.set_footer(text="申請ログ | Minister Chikuwa")
                            await log_channel.send(embed=log_embed)
                            await app_channel.delete(reason="Wynncraftギルド加入検知→申請チャンネル削除")
                        except Exception as e:
                            logger.error(f"申請チャンネル削除・ログ転送失敗: {e}")
                    delete_application_by_discord_id(discord_id)
                    logger.info(f"[ApplicationSync] {mcid} の申請を処理し、チャンネル削除とDB削除を実施しました")
        except Exception as e:
            logger.error(f"[ApplicationSync] 申請加入同期で例外: {e}", exc_info=True)
        await asyncio.sleep(60) # 5分

async def setup(bot):
    api = WynncraftAPI()
    bot.loop.create_task(member_rank_sync_task(api, bot))
    bot.loop.create_task(member_remove_sync_task(bot, api))
    bot.loop.create_task(member_application_sync_task(bot, api))
