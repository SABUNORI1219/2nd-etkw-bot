import discord
from discord.ext import tasks
from discord.utils import get
import asyncio

from lib.ticket_embeds import (
    send_ticket_user_embed, send_ticket_staff_embed,
    TICKET_CATEGORY_ID, TICKET_STAFF_ROLE_ID,
    extract_applicant_user_id_from_content
)

# チケットBotのuser_id
TICKET_TOOL_BOT_ID = 557628352828014614

from lib.profile_renderer import generate_profile_card
from lib.api_stocker import WynncraftAPI

intents = discord.Intents.default()
intents.guilds = True
intents.messages = True
intents.message_content = True

def extract_ticket_form_data(embed: discord.Embed) -> dict:
    """Embed(fields形式)からform内容を抽出"""
    data = {}
    for field in embed.fields:
        key = field.name.strip()
        val = field.value.strip()
        if val.startswith("```") and val.endswith("```"):
            val = val[3:-3].strip()
        data[key] = val
    return data

async def on_guild_channel_create(channel: discord.TextChannel):
    if channel.category_id != TICKET_CATEGORY_ID:
        return

    await asyncio.sleep(2)
    history = [m async for m in channel.history(limit=10)]  # 多めに見る

    ticket_bot_msg = None
    user_id = None

    for msg in reversed(history):
        if msg.author.id == TICKET_TOOL_BOT_ID and msg.embeds:
            # "ユーザー入力" Embedか判定（fieldsに「MCID」や「IGN」などが含まれるか）
            for embed in msg.embeds:
                if any("MCID" in field.name or "IGN" in field.name for field in embed.fields):
                    ticket_bot_msg = msg
                    break
        if ticket_bot_msg is not None:
            # contentからuser_id抽出
            if msg.content.startswith("<@"):
                extracted = extract_applicant_user_id_from_content(msg.content)
                if extracted:
                    user_id = extracted
            break

    if not ticket_bot_msg:
        return  # ユーザー申請内容のEmbedがなければ何もしない

    # Fallback: Bot以外のメンバーが1人だけならその人
    if user_id is None:
        members = [m for m in channel.members if not m.bot]
        if len(members) == 1:
            user_id = members[0].id

    # ↓以降はいつも通り
    embed = [e for e in ticket_bot_msg.embeds if any("MCID" in f.name or "IGN" in f.name for f in e.fields)][0]
    form_data = extract_ticket_form_data(embed)
    mcid = None
    for key in form_data:
        if "MCID" in key or "IGN" in key:
            mcid = form_data[key]
            break
    applicant_name = mcid if mcid else "Applicant"

    # --- プロファイル画像生成 ---
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
