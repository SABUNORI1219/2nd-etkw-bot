import asyncio
import logging
import re
import os

from lib.api_stocker import WynncraftAPI
from lib.db import get_linked_members_page, add_member, remove_member, get_member, get_all_applications, remove_application
from lib.discord_notify import notify_member_removed
from lib.ticket_embeds import make_application_transcript_embed
from config import RANK_ROLE_ID_MAP, ETKW, ROLE_ID_TO_RANK

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

async def application_join_detection_task(api: WynncraftAPI, bot=None):
    """ギルド加入検知・申請完了処理タスク"""
    while True:
        try:
            logger.info("[ApplicationSync] ギルド加入検知タスク開始")
            
            # 現在のギルドメンバーを取得
            guild_members = await fetch_guild_members(api)
            if not guild_members:
                logger.warning("[ApplicationSync] APIからのギルドデータ取得失敗、処理をスキップ")
                await asyncio.sleep(180)
                continue
            
            # 申請中のメンバーをチェック
            applications = get_all_applications()
            
            for app in applications:
                mcid = app['mcid']
                discord_id = app['discord_id']
                
                # ギルドに加入しているかチェック
                if mcid in guild_members:
                    rank = guild_members[mcid]
                    logger.info(f"[ApplicationSync] {mcid} のギルド加入を検知")
                    
                    # DBにメンバーとして追加
                    add_member(mcid, discord_id, rank)
                    
                    # Discordでロール付与・ニックネーム設定
                    if bot:
                        await assign_member_roles_and_nickname(bot, discord_id, mcid, rank)
                    
                    # 申請チャンネルを削除・トランスクリプト送信
                    await complete_application(bot, app)
                    
                    # DBから申請情報を削除
                    remove_application(discord_id)
                    
        except Exception as e:
            logger.error(f"[ApplicationSync] ギルド加入検知で例外: {e}", exc_info=True)
        
        await asyncio.sleep(180)  # 3分ごとにチェック

async def assign_member_roles_and_nickname(bot, discord_id: int, mcid: str, rank: str):
    """新規メンバーにロール付与・ニックネーム設定"""
    try:
        for guild in bot.guilds:
            member = guild.get_member(discord_id)
            if member:
                # 1. ランクロール付与
                role_id = RANK_ROLE_ID_MAP.get(rank)
                if role_id:
                    role = guild.get_role(role_id)
                    if role:
                        try:
                            await member.add_roles(role, reason="ギルド加入による自動ロール付与")
                            logger.info(f"[ApplicationSync] {mcid} に {role.name} ロールを付与")
                        except Exception as e:
                            logger.error(f"[ApplicationSync] ロール付与失敗: {e}")
                
                # 2. ETKWロール付与
                if ETKW:
                    etkw_role = guild.get_role(ETKW)
                    if etkw_role:
                        try:
                            await member.add_roles(etkw_role, reason="ギルド加入によるETKWロール付与")
                            logger.info(f"[ApplicationSync] {mcid} に ETKWロールを付与")
                        except Exception as e:
                            logger.error(f"[ApplicationSync] ETKWロール付与失敗: {e}")
                
                # 3. ニックネーム設定
                role_name = role.name if 'role' in locals() and role else rank
                prefix = re.sub(r"\s*\[.*?]\s*", " ", role_name).strip()
                new_nick = f"{prefix} {mcid}"
                if len(new_nick) > 32:
                    new_nick = new_nick[:32]
                
                try:
                    if not member.guild_permissions.administrator:
                        await member.edit(nick=new_nick, reason="ギルド加入による自動ニックネーム設定")
                        logger.info(f"[ApplicationSync] {mcid} のニックネームを '{new_nick}' に設定")
                except Exception as e:
                    logger.error(f"[ApplicationSync] ニックネーム設定失敗: {e}")
                
                break  # 該当guildで見つかったら終わり
                
    except Exception as e:
        logger.error(f"[ApplicationSync] ロール・ニックネーム設定で例外: {e}", exc_info=True)

async def complete_application(bot, application: dict):
    """申請完了処理：チャンネル削除・トランスクリプト送信"""
    try:
        channel_id = application['channel_id']
        mcid = application['mcid']
        discord_id = application['discord_id']
        reason = application['reason']
        past_guild = application.get('past_guild')
        
        # 申請チャンネルを取得
        channel = bot.get_channel(channel_id)
        if channel:
            # トランスクリプトEmbedを作成
            transcript_embed = make_application_transcript_embed(mcid, discord_id, reason, past_guild)
            
            # ログチャンネルに送信（ログチャンネルIDは環境変数から取得）
            log_channel_id = int(os.getenv('APPLICATION_LOG_CHANNEL_ID', 0))
            if log_channel_id:
                log_channel = bot.get_channel(log_channel_id)
                if log_channel:
                    await log_channel.send(embed=transcript_embed)
                    logger.info(f"[ApplicationSync] {mcid} の申請トランスクリプトをログチャンネルに送信")
            
            # 申請チャンネルを削除
            await channel.delete(reason=f"ギルド加入完了 - {mcid}")
            logger.info(f"[ApplicationSync] {mcid} の申請チャンネルを削除")
        
    except Exception as e:
        logger.error(f"[ApplicationSync] 申請完了処理で例外: {e}", exc_info=True)

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

async def setup(bot):
    api = WynncraftAPI()
    bot.loop.create_task(member_rank_sync_task(api, bot))
    bot.loop.create_task(member_remove_sync_task(bot, api))
    bot.loop.create_task(application_join_detection_task(api, bot))
