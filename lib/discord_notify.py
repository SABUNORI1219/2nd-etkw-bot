import discord
import logging
from lib.db import get_config
import os
from datetime import timezone, timedelta

logger = logging.getLogger(__name__)

# レイド名ごとに対応する絵文字を登録
RAID_EMOJIS = {
    "The Nameless Anomaly": "<:wynn_tna:1400385557795835958>",
    "The Canyon Colossus": "<:wynn_tcc:1400385514460155914>",
    "Orphion's Nexus of Light": "<:wynn_nol:1400385439508074618>",
    "Nest of the Grootslangs": "<:wynn_notg:1400385362299195424>"
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

async def notify_member_removed(bot, member_data):
    """
    ギルドから脱退したメンバーを通知する
    member_data: dict {mcid, discord_id, rank}
    """
    NOTIFY_CHANNEL_ID = int(get_config("MEMBER_NOTIFY_CHANNEL_ID") or "0")
    channel = bot.get_channel(NOTIFY_CHANNEL_ID)
    if not channel:
        logger.warning("メンバー通知チャンネルが見つかりません")
        return
    embed = discord.Embed(
        title="Guild Member Removed",
        color=discord.Color.red()
    )
    embed.add_field(name="MCID", value=f"`{member_data.get('mcid', 'N/A')}`", inline=True)
    embed.add_field(name="Discord", value=f"<@{member_data.get('discord_id', 'N/A')}>", inline=True)
    embed.add_field(name="Rank", value=f"`{member_data.get('rank', 'N/A')}`", inline=True)
    embed.set_footer(text="Member Removal | Minister Chikuwa")
    await channel.send(embed=embed)
    logger.info(f"Guild脱退通知: {member_data}")

async def notify_member_left_discord(bot, member_data):
    """
    Discordサーバーから退出したメンバーを通知する
    member_data: dict {mcid, discord_id, rank}
    """
    NOTIFY_CHANNEL_ID = int(get_config("MEMBER_NOTIFY_CHANNEL_ID") or "0")
    channel = bot.get_channel(NOTIFY_CHANNEL_ID)
    if not channel:
        logger.warning("メンバー通知チャンネルが見つかりません")
        return
    embed = discord.Embed(
        title="Discord Member Left",
        color=discord.Color.orange()
    )
    embed.add_field(name="MCID", value=f"`{member_data.get('mcid', 'N/A')}`", inline=True)
    embed.add_field(name="Discord", value=f"<@{member_data.get('discord_id', 'N/A')}>", inline=True)
    embed.add_field(name="Rank", value=f"`{member_data.get('rank', 'N/A')}`", inline=True)
    embed.set_footer(text="Discord Leave | Minister Chikuwa")
    await channel.send(embed=embed)
    logger.info(f"Discord退出通知: {member_data}")
