import discord
import logging
import os

logger = logging.getLogger(__name__)

# 通知チャンネルIDは外部設定ファイル/DBから取得（ここでは仮に環境変数）
NOTIFY_CHANNEL_ID = int(os.environ.get("NOTIFY_CHANNEL_ID", "0"))

async def send_guild_raid_embed(bot, party):
    channel = bot.get_channel(NOTIFY_CHANNEL_ID)
    if not channel:
        logger.warning("通知チャンネルが見つかりません")
        return
    embed = discord.Embed(title=f"{party['raid_name']} - {party['clear_time']}")
    embed.add_field(name="Members", value="\n".join(party["members"]))
    embed.add_field(name="Server", value=party["server"])
    await channel.send(embed=embed)
    logger.info(f"Embed通知: {party}")
