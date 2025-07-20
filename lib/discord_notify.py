import discord
import logging
from lib.db import get_config
import os

logger = logging.getLogger(__name__)

NOTIFY_CHANNEL_ID = int(get_config("NOTIFY_CHANNEL_ID") or "0")

async def send_guild_raid_embed(bot, party):
    channel = bot.get_channel(NOTIFY_CHANNEL_ID)
    if not channel:
        logger.warning("通知チャンネルが見つかりません")
        return
    embed = discord.Embed(
        title="Guild Raid Clear",
        color=discord.Color.blue()
    )
    embed.add_field(
        name=f"**{party['raid_name']}** - `{party['clear_time']}`",
        value=f"**Members**: {', '.join(party['members'])}\n"
              f"**Server**: {party['server']}",
        inline=False
    )
    await channel.send(embed=embed)
    logger.info(f"Embed通知: {party}")
