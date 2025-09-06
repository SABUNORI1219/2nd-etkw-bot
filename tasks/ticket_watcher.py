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
from lib.api_stocker import WynncraftAPI

logger = logging.getLogger(__name__)

intents = discord.Intents.default()
intents.guilds = True
intents.messages = True
intents.message_content = True

def extract_mcid_from_description(description: str) -> str | None:
    # MCID/IGNの質問文の直後に```で囲まれた回答が来る形式
    m = re.search(r"(MCID|IGN)[^\n]*\n```([^\n`]+)```", description, re.IGNORECASE)
    if m:
        return m.group(2).strip()
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

    for idx, embed in enumerate(ticket_bot_msg.embeds):
        logger.info(f"[Embed DEBUG] embed[{idx}].title: {repr(getattr(embed, 'title', None))}")
        logger.info(f"[Embed DEBUG] embed[{idx}].description: {repr(embed.description)}")
        logger.info(f"[Embed DEBUG] embed[{idx}].fields: {[{'name': f.name, 'value': f.value} for f in embed.fields]}")
    
    embed = ticket_bot_msg.embeds[0]
    mcid = None

    # --- 新方式: descriptionから正規表現でMCID抽出 ---
    if embed.description:
        mcid = extract_mcid_from_description(embed.description)

    # --- fallback: splitlines方式 ---
    if not mcid and embed.description:
        lines = embed.description.splitlines()
        for i, line in enumerate(lines):
            if "MCID" in line or "IGN" in line:
                if i+1 < len(lines):
                    next_line = lines[i+1].strip()
                    if next_line.startswith("```") and next_line.endswith("```"):
                        mcid = next_line.strip("` \n")
                        break

    if not mcid:
        logger.warning(f"[MCID抽出失敗] embed.description={repr(embed.description)}")
        return

    applicant_name = mcid
    profile_path = None
    try:
        api = WynncraftAPI()
        player_data = await api.get_official_player_data(mcid)
        if player_data:
            profile_path = f"profile_card_{mcid}.png"
            generate_profile_card(player_data, profile_path)
    except Exception:
        profile_path = None

    await send_ticket_user_embed(channel, user_id, TICKET_STAFF_ROLE_ID)
    await asyncio.sleep(1)
    await send_ticket_staff_embed(channel, profile_path, applicant_name, user_id, TICKET_STAFF_ROLE_ID)

async def setup(bot):
    async def _on_guild_channel_create(channel):
        await on_guild_channel_create(channel)
    bot.add_listener(_on_guild_channel_create, "on_guild_channel_create")
