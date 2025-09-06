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

async def on_guild_channel_create(channel: discord.TextChannel):
    if channel.category_id != TICKET_CATEGORY_ID:
        return

    await asyncio.sleep(2)

    history = [m async for m in channel.history(limit=5)]
    ticket_bot_msg = None
    user_id = None

    for msg in reversed(history):
        # Embedが2つあるTicket Toolメッセージだけを対象
        if msg.author.id == TICKET_TOOL_BOT_ID and len(msg.embeds) == 2:
            ticket_bot_msg = msg
            # contentからuser_idを抽出
            if msg.content.startswith("<@"):
                extracted = extract_applicant_user_id_from_content(msg.content)
                if extracted:
                    user_id = extracted
            break

    if not ticket_bot_msg:
        return  # 条件に当てはまらなければ何もしない

    # Fallback: Bot以外のメンバーが1人だけならその人
    if user_id is None:
        members = [m for m in channel.members if not m.bot]
        if len(members) == 1:
            user_id = members[0].id

    # 申請内容Embed(通常1つ目)からMCID（IGN）を適当にパース
    embed = ticket_bot_msg.embeds[0]
    mcid = None

    # descriptionをすべて文字列として検索
    if embed.description:
        text = embed.description
        # 「MCID」「IGN」などが含まれる行を探す
        for line in text.splitlines():
            if "MCID" in line or "IGN" in line:
                # 次の行が ```xxx``` の場合それを使う
                idx = text.splitlines().index(line)
                if idx+1 < len(text.splitlines()):
                    next_line = text.splitlines()[idx+1].strip()
                    if next_line.startswith("```") and next_line.endswith("```"):
                        mcid = next_line.strip("` \n")
                        break

    # ここでmcidが抽出できなければ何もしない
    if not mcid:
        return

    applicant_name = mcid

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
