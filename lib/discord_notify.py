import discord
import logging
from lib.db import get_config
import os
from datetime import timezone, timedelta

logger = logging.getLogger(__name__)

# レイド名ごとに対応する絵文字を登録
RAID_EMOJIS = {
    "The Nameless Anomaly": "<:anomaly:1272959194626134148>",
    "The Canyon Colossus": "<:canyon:1272959833011785838>",
    "Orphion's Nexus of Light": "<:orphion:1272959789043023893>",
    "Nest of the Grootslangs": "<:grootslang:1272959874455572604>"
}
DEFAULT_EMOJI = "🎲"  # 未登録レイド用

def get_emoji_for_raid(raid_name):
    return RAID_EMOJIS.get(raid_name, DEFAULT_EMOJI)

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
    emoji = get_emoji_for_raid(party['raid_name'])

    # clear_time整形
    clear_time = party['clear_time']
    # Discordのタイムスタンプとして出力（<t:unix:形式>）
    if isinstance(clear_time, str):
        # 文字列→datetime変換（万が一strで来た場合）
        from dateutil import parser
        clear_time_dt = parser.parse(clear_time)
    else:
        clear_time_dt = clear_time

    # UTC→JST変換
    JST = timezone(timedelta(hours=9))
    clear_time_jst = clear_time_dt.astimezone(JST)

    # Discordのタイムスタンプ書式（<t:unix:形式>）を利用
    unix_ts = int(clear_time_dt.replace(tzinfo=timezone.utc).timestamp())
    timestamp_str = f"<t:{unix_ts}:F>"  # 例: 2025年7月21日 20:06 (曜日や分単位まで表示)

    # マイクロ秒部分を除いたJST表記（Fallback用）
    simple_jst_str = clear_time_jst.strftime('%Y-%m-%d %H:%M:%S')
    
    embed.add_field(
        name=f"{emoji} **{party['raid_name']}** - {timestamp_str}",
        value=f"> **Members**: {members_str}\n"
              f"> **Server**: {party['server']}",
        inline=False
    )

    embed.set_footer(text="Guild Raid Tracker | Minister Chikuwa")
    
    await channel.send(embed=embed)
    logger.info(f"Embed通知: {party}")
