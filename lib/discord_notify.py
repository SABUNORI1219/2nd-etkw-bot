import discord
import logging
from lib.db import get_config
import os

logger = logging.getLogger(__name__)

async def send_guild_raid_embed(bot, party):
    NOTIFY_CHANNEL_ID = int(get_config("NOTIFY_CHANNEL_ID") or "0")
    channel = bot.get_channel(NOTIFY_CHANNEL_ID)
    if not channel:
        logger.warning("通知チャンネルが見つかりません")
        return
    logger.info(f"通知先チャンネルID: {NOTIFY_CHANNEL_ID}, channel={channel}")
    embed = discord.Embed(
        title="Guild Raid Clear",
        color=discord.Color.blue()
    )
    
    members_str = ', '.join([discord.utils.escape_markdown(m) for m in party['members']])
    embed.add_field(
        name=f"**{party['raid_name']}** - `{party['clear_time']}`",
        value=f"**Members**: {members_str}\n"
              f"**Server**: {party['server']}",
        inline=False
    )
    await channel.send(embed=embed)
    logger.info(f"Embed通知: {party}")
