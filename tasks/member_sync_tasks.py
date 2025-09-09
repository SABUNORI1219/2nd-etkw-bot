import asyncio
import logging
import re
import discord
from datetime import datetime

from lib.api_stocker import WynncraftAPI
from lib.db import (
    get_linked_members_page, add_member, remove_member, get_member,
    get_all_pending_applications, delete_application_request, get_application_by_discord_id
)
from lib.discord_notify import notify_member_removed
from config import RANK_ROLE_ID_MAP, ETKW, ROLE_ID_TO_RANK, APPLICATION_LOG_CHANNEL_ID

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
            
            # 申請者の加入検知処理
            if bot:
                await check_application_joins(guild_members, bot)
            
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
                            await apply_member_roles_and_nick(bot, dbm['discord_id'], mcid, api_rank)
                if page >= total_pages:
                    break
                page += 1
        except Exception as e:
            logger.error(f"[MemberSync] ランク同期で例外: {e}", exc_info=True)
        await asyncio.sleep(120)


async def apply_member_roles_and_nick(bot, discord_id: int, mcid: str, rank: str):
    """メンバーにロールとニックネームを適用"""
    for guild in bot.guilds:
        member = guild.get_member(discord_id)
        if member:
            # 1. 旧ランクロール全削除（ROLE_ID_TO_RANKに含まれるもの全て）
            old_roles = [role for role in member.roles if role.id in ROLE_ID_TO_RANK]
            if old_roles:
                try:
                    await member.remove_roles(*old_roles, reason="ランク同期: 旧ランクロール削除")
                except Exception as e:
                    logger.error(f"[MemberSync] 旧ランクロール削除失敗: {e}")
            
            # 2. 新ランクロール付与
            new_role_id = RANK_ROLE_ID_MAP.get(rank)
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
            prefix = new_role.name if new_role else rank
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


async def check_application_joins(guild_members: dict, bot):
    """申請者の加入を検知し、処理を実行"""
    try:
        # 全ての申請中の情報を取得
        pending_applications = get_all_pending_applications()
        if not pending_applications:
            return
        
        logger.debug(f"[ApplicationJoin] {len(pending_applications)}件の申請をチェック中...")
        
        for app in pending_applications:
            mcid = app['mcid']
            discord_id = app['discord_id']
            channel_id = app['channel_id']
            
            # ギルドメンバーに含まれているかチェック
            if mcid in guild_members:
                rank = guild_members[mcid]
                logger.info(f"[ApplicationJoin] 申請者 {mcid} (Discord ID: {discord_id}) のギルド加入を検知")
                
                # Discord メンバー取得
                discord_member = None
                for guild in bot.guilds:
                    discord_member = guild.get_member(discord_id)
                    if discord_member:
                        break
                
                if discord_member:
                    # 1. linked_membersテーブルに追加
                    add_member(mcid, discord_id, rank)
                    logger.info(f"[ApplicationJoin] {mcid} をDBに追加（ランク: {rank}）")
                    
                    # 2. ロール付与・ニックネーム設定
                    await apply_member_roles_and_nick(bot, discord_id, mcid, rank)
                    logger.info(f"[ApplicationJoin] {mcid} にロールとニックネームを設定")
                    
                    # 3. 申請チャンネルの処理
                    await handle_application_completion(bot, app, discord_member)
                    
                    # 4. DB から申請情報削除
                    delete_application_request(discord_id)
                    logger.info(f"[ApplicationJoin] 申請情報をDBから削除: {mcid}")
                else:
                    logger.warning(f"[ApplicationJoin] Discord メンバーが見つかりません: ID {discord_id}")
            
    except Exception as e:
        logger.error(f"[ApplicationJoin] 申請加入検知処理でエラー: {e}", exc_info=True)


async def handle_application_completion(bot, application_data: dict, discord_member):
    """申請完了時の処理（トランスクリプト送信・チャンネル削除）"""
    try:
        channel_id = application_data['channel_id']
        channel = bot.get_channel(channel_id)
        
        if channel:
            # トランスクリプト用のEmbed作成
            transcript_embed = await create_application_transcript(application_data, discord_member, channel)
            
            # ログチャンネルに送信
            log_channel = bot.get_channel(APPLICATION_LOG_CHANNEL_ID)
            if log_channel:
                await log_channel.send(embed=transcript_embed)
                logger.info(f"[ApplicationJoin] トランスクリプトをログチャンネルに送信: {application_data['mcid']}")
            
            # 申請チャンネル削除
            await channel.delete(reason=f"申請完了: {application_data['mcid']} がギルドに加入")
            logger.info(f"[ApplicationJoin] 申請チャンネルを削除: {application_data['mcid']}")
        else:
            logger.warning(f"[ApplicationJoin] 申請チャンネルが見つかりません: {channel_id}")
        
    except Exception as e:
        logger.error(f"[ApplicationJoin] 申請完了処理でエラー: {e}", exc_info=True)


async def create_application_transcript(application_data: dict, discord_member, channel) -> discord.Embed:
    """申請のトランスクリプトEmbed作成"""
    try:
        embed = discord.Embed(
            title="✅ ギルド加入申請完了",
            description=f"**{application_data['mcid']}** の申請が正常に完了しました。",
            color=0x00FF00,
            timestamp=datetime.utcnow()
        )
        
        embed.add_field(name="MCID", value=application_data['mcid'], inline=True)
        embed.add_field(name="Discord", value=f"<@{application_data['discord_id']}>", inline=True)
        embed.add_field(name="申請日時", value=application_data['created_at'].strftime("%Y/%m/%d %H:%M"), inline=True)
        
        embed.add_field(name="加入理由", value=application_data['reason'], inline=False)
        
        if application_data.get('past_guild'):
            embed.add_field(name="過去所属ギルド", value=application_data['past_guild'], inline=True)
        
        if discord_member and discord_member.avatar:
            embed.set_thumbnail(url=discord_member.avatar.url)
        
        embed.set_footer(text=f"チャンネルID: {application_data['channel_id']}")
        
        return embed
        
    except Exception as e:
        logger.error(f"[ApplicationJoin] トランスクリプトEmbed作成エラー: {e}", exc_info=True)
        # エラー時の簡易版
        return discord.Embed(
            title="✅ ギルド加入申請完了",
            description=f"**{application_data['mcid']}** の申請が完了しました（詳細取得エラー）",
            color=0x00FF00,
            timestamp=datetime.utcnow()
        )

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
