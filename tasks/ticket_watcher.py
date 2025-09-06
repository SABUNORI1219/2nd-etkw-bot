import discord
from discord.ext import tasks
from discord.utils import get
import asyncio
import re
import logging

from lib.ticket_embeds import (
    send_ticket_user_embed, send_ticket_staff_embed,
    TICKET_CATEGORY_ID, TICKET_STAFF_ROLE_ID,
    extract_applicant_user_id_from_content
)

# チケットBotのuser_id
TICKET_TOOL_BOT_ID = 557628352828014614

from lib.profile_renderer import generate_profile_card
from lib.api_stocker import WynncraftAPI, OtherAPI
from lib.banner_renderer import BannerRenderer
from PIL import Image
from io import BytesIO

logger = logging.getLogger(__name__)

intents = discord.Intents.default()
intents.guilds = True
intents.messages = True
intents.message_content = True

def extract_mcid_from_description(description: str) -> str | None:
    # MCID/IGN/in game nameの質問文の直後に```で囲まれた回答が来る形式
    pattern = (
        r"("
        r"MCID|IGN|in[\s-]?game[\s-]?name"
        r")[^\n`]*\n```([^\n`]+)```"
    )
    m = re.search(pattern, description, re.IGNORECASE)
    if m:
        return m.group(2).strip()
    # fallback: "**MCID** ```\nxxxx```" のようなパターン（改行や**対応）
    pattern2 = (
        r"("
        r"MCID|IGN|in[\s-]?game[\s-]?name"
        r")[^`]*```[ \n]*([^\n`]+)[ \n]*```"
    )
    m2 = re.search(pattern2, description, re.IGNORECASE)
    if m2:
        return m2.group(2).strip()
    return None

async def on_guild_channel_create(channel: discord.TextChannel):
    if channel.category_id != TICKET_CATEGORY_ID:
        return

    await asyncio.sleep(2)

    history = [m async for m in channel.history(limit=5)]
    ticket_bot_msg = None
    user_id = None

    for msg in reversed(history):
        if msg.author.id == TICKET_TOOL_BOT_ID and len(msg.embeds) == 2:
            ticket_bot_msg = msg
            if msg.content.startswith("<@"):
                extracted = extract_applicant_user_id_from_content(msg.content)
                if extracted:
                    user_id = extracted
            break

    if not ticket_bot_msg:
        return

    if user_id is None:
        members = [m for m in channel.members if not m.bot]
        if len(members) == 1:
            user_id = members[0].id

    # --- embeds全体からMCIDを探す ---
    mcid = None
    applicant_embed = None
    for embed in ticket_bot_msg.embeds:
        if embed.description:
            mcid_candidate = extract_mcid_from_description(embed.description)
            if not mcid_candidate:
                # fallback: splitlines方式
                lines = embed.description.splitlines()
                for i, line in enumerate(lines):
                    if "MCID" in line or "IGN" in line:
                        # コードブロック含む次行を抽出
                        if i+1 < len(lines):
                            next_line = lines[i+1].strip("` \n")
                            if next_line:
                                mcid_candidate = next_line
                                break
            if mcid_candidate:
                mcid = mcid_candidate
                applicant_embed = embed
                break

    if not mcid:
        logger.warning(f"[MCID抽出失敗] 全Embed description: {[repr(e.description) for e in ticket_bot_msg.embeds]}")
        return

    applicant_name = mcid
    profile_path = None
    try:
        api = WynncraftAPI()
        other_api = OtherAPI()
        banner_renderer = BannerRenderer()
        player_data = await api.get_official_player_data(mcid)
        if player_data:
            # ここからprofile_info整形（player_cog.pyのhandle_player_dataの該当部分をコピペ・再現）
            def safe_get(d, keys, default="???"):
                v = d
                for k in keys:
                    if not isinstance(v, dict):
                        return default
                    v = v.get(k)
                    if v is None:
                        return default
                return v

            def fallback_stat(data, keys_global, default="???"):
                val = safe_get(data, keys_global, None)
                if val is not None:
                    return val
                return default

            def get_raid_stat(data, raid_key):
                global_data = data.get("globalData")
                if not global_data or not isinstance(global_data, dict):
                    return "???"
                raids = global_data.get("raids")
                if not raids or not isinstance(raids, dict):
                    return "???"
                raid_list = raids.get("list")
                if raid_list == {}:
                    return 0
                if not raid_list or not isinstance(raid_list, dict):
                    return "???"
                return raid_list.get(raid_key, 0)

            raw_support_rank = safe_get(player_data, ['supportRank'], "None")
            if raw_support_rank and raw_support_rank.lower() == "vipplus":
                support_rank_display = "Vip+"
            elif raw_support_rank and raw_support_rank.lower() == "heroplus":
                support_rank_display = "Hero+"
            else:
                support_rank_display = (raw_support_rank or 'None').capitalize()

            first_join_str = safe_get(player_data, ['firstJoin'], "???")
            first_join_date = first_join_str.split('T')[0] if first_join_str and 'T' in first_join_str else first_join_str

            last_join_str = safe_get(player_data, ['lastJoin'], "???")
            if last_join_str and isinstance(last_join_str, str) and 'T' in last_join_str:
                try:
                    last_join_dt = datetime.fromisoformat(last_join_str.replace('Z', '+00:00'))
                    last_join_date = last_join_dt.strftime('%Y-%m-%d')
                except Exception:
                    last_join_date = last_join_str.split('T')[0]
            else:
                last_join_date = last_join_str if last_join_str else "???"

            guild_prefix = safe_get(player_data, ['guild', 'prefix'], "")
            guild_name = safe_get(player_data, ['guild', 'name'], "")
            guild_rank = safe_get(player_data, ['guild', 'rank'], "")
            guild_data = await api.get_guild_by_prefix(guild_prefix)
            banner_bytes = banner_renderer.create_banner_image(guild_data.get('banner') if guild_data and isinstance(guild_data, dict) else None)

            is_online = safe_get(player_data, ['online'], False)
            server = safe_get(player_data, ['server'], "???")
            if is_online:
                server_display = f"Online on {server}"
            else:
                server_display = "Offline"

            active_char_uuid = safe_get(player_data, ['activeCharacter'])
            if active_char_uuid is None:
                active_char_info = "???"
            else:
                char_obj = safe_get(player_data, ['characters', active_char_uuid], {})
                char_type = safe_get(char_obj, ['type'], "???")
                reskin = safe_get(char_obj, ['reskin'], "N/A")
                if reskin != "N/A":
                    active_char_info = f"{reskin}"
                else:
                    active_char_info = f"{char_type}"

            mobs_killed = fallback_stat(player_data, ['globalData', 'mobsKilled'])
            playtime = player_data.get("playtime", "???") if player_data.get("playtime", None) is not None else "???"
            wars = fallback_stat(player_data, ['globalData', 'wars'])
            quests = fallback_stat(player_data, ['globalData', 'completedQuests'])
            world_events = fallback_stat(player_data, ['globalData', 'worldEvents'])
            total_level = fallback_stat(player_data, ['globalData', 'totalLevel'])
            chests = fallback_stat(player_data, ['globalData', 'chestsFound'])
            pvp_kill = str(safe_get(player_data, ['globalData', 'pvp', 'kills'], "???"))
            pvp_death = str(safe_get(player_data, ['globalData', 'pvp', 'deaths'], "???"))
            dungeons = fallback_stat(player_data, ['globalData', 'dungeons', 'total'])
            all_raids = fallback_stat(player_data, ['globalData', 'raids', 'total'])

            ranking_obj = safe_get(player_data, ['ranking'], None)
            if ranking_obj is None:
                war_rank_display = "非公開"
            else:
                war_rank_completion = ranking_obj.get('warsCompletion')
                if war_rank_completion is None:
                    war_rank_display = "N/A"
                else:
                    war_rank_display = str(war_rank_completion)

            notg = get_raid_stat(player_data, 'Nest of the Grootslangs')
            nol = get_raid_stat(player_data, "Orphion's Nexus of Light")
            tcc = get_raid_stat(player_data, 'The Canyon Colossus')
            tna = get_raid_stat(player_data, 'The Nameless Anomaly')

            uuid = player_data.get("uuid")

            profile_info = {
                "username": player_data.get("username"),
                "support_rank_display": support_rank_display,
                "guild_prefix": guild_prefix,
                "banner_bytes": banner_bytes,
                "guild_name": guild_name,
                "guild_rank": guild_rank,
                "server_display": server_display,
                "active_char_info": active_char_info,
                "first_join": first_join_date,
                "last_join": last_join_date,
                "mobs_killed": mobs_killed,
                "playtime": playtime,
                "wars": wars,
                "war_rank_display": war_rank_display,
                "quests": quests,
                "world_events": world_events,
                "total_level": total_level,
                "chests": chests,
                "pvp_kill": pvp_kill,
                "pvp_death": pvp_death,
                "notg": notg,
                "nol": nol,
                "tcc": tcc,
                "tna": tna,
                "dungeons": dungeons,
                "all_raids": all_raids,
                "uuid": uuid,
            }

            skin_image = None
            if uuid:
                try:
                    skin_bytes = await other_api.get_vzge_skin(uuid)
                    if skin_bytes:
                        skin_image = Image.open(BytesIO(skin_bytes)).convert("RGBA")
                except Exception as e:
                    logger.error(f"Skin image load failed: {e}")

            output_path = f"profile_card_{uuid}.png" if uuid else "profile_card.png"
            generate_profile_card(profile_info, output_path, skin_image=skin_image)
            profile_path = output_path
    except Exception as e:
        logger.error(f"Profile image generation error: {e}")
        profile_path = None

    await send_ticket_user_embed(channel, user_id, TICKET_STAFF_ROLE_ID)
    await asyncio.sleep(1)
    await send_ticket_staff_embed(channel, profile_path, applicant_name, user_id, TICKET_STAFF_ROLE_ID)

async def setup(bot):
    async def _on_guild_channel_create(channel):
        await on_guild_channel_create(channel)
    bot.add_listener(_on_guild_channel_create, "on_guild_channel_create")
