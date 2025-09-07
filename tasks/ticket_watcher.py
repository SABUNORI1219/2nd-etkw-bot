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

from config import TICKET_TOOL_BOT_ID
from lib.profile_renderer import generate_profile_card
from lib.api_stocker import WynncraftAPI, OtherAPI
from lib.banner_renderer import BannerRenderer
from PIL import Image
from io import BytesIO

from cogs.player_cog import build_profile_info

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
            profile_info = await build_profile_info(player_data, api, banner_renderer)
            uuid = profile_info.get("uuid")
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
