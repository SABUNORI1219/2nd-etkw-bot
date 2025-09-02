import discord
import logging
from lib.db import get_config
import os
from datetime import timezone, timedelta
from config import ETKW_SERVER
import asyncio
import time

logger = logging.getLogger(__name__)

# バックアップ通知チャンネルID
backup_channel_id = 1271174069433274399

# チャンネルリンク
channel_link = f"https://discord.com/channels/{str(ETKW_SERVER)}/{backup_channel_id}"

# レイド名ごとに対応する絵文字を登録
RAID_EMOJIS = {
    "The Nameless Anomaly": "<:wynn_tna:1400385557795835958>",
    "The Canyon Colossus": "<:wynn_tcc:1400385514460155914>",
    "Orphion's Nexus of Light": "<:wynn_nol:1400385439508074618>",
    "Nest of the Grootslangs": "<:wynn_notg:1400385362299195424>"
}
DEFAULT_EMOJI = "🎲"  # 未登録レイド用

JAPANESE_MESSAGE = (
    "**ご自身でギルドから抜けた場合には、このメッセージは無視してください**。\n\n"
    "最近、Wynncraft内での活動が盛んではないかつ、新しいメンバーが加入するためにキックいたしました。\n"
    "__再度加入したい場合は、[こちらのチャンネル]({channel_link})でその旨伝えてください__。\n"
    "またWynncraftにログインできなくなる理由がある場合は、ここで伝えてもらえれば枠をキープすることもできます。"
)

ENGLISH_MESSAGE = (
    "**If you left the guild yourself, please ignore this message**.\n\n"
    "You were kicked because there hasn't been much activity in Wynncraft recently and to make way for new members.\n"
    "__If you would like to rejoin, please let us know [here]({channel_link})__.\n"
    "Also, if there is a reason why you can no longer log in to Wynncraft, you can let us know there and we will be able to keep your spot."
)

def get_emoji_for_raid(raid_name):
    return RAID_EMOJIS.get(raid_name, DEFAULT_EMOJI)

def create_departure_embed_dual() -> discord.Embed:
    """
    日本語・英語両方を含めた脱退通知Embedを作成
    """
    embed = discord.Embed(
        title="ギルド脱退のお知らせ / Guild Departure Notice",
        color=discord.Color.red()
    )
    embed.add_field(
        name="日本語",
        value=JAPANESE_MESSAGE.format(channel_link=channel_link),
        inline=False
    )
    embed.add_field(
        name="English",
        value=ENGLISH_MESSAGE.format(channel_link=channel_link),
        inline=False
    )
    embed.set_footer(text="Inactive通知 | Minister Chikuwa")
    return embed

async def send_test_departure_embed(bot, channel_or_user, target_user_id: int):
    """
    Utility function for sending a test departure embed (日本語・英語両方入り).
    Args:
        bot: Discord bot instance
        channel_or_user: Channel or User object to send to
        target_user_id: ID of the user who can control the embed
    """
    embed = create_departure_embed_dual()  # 日英両方入りEmbed

    try:
        message = await channel_or_user.send(embed=embed)
        logger.info(f"Test departure embed (dual) sent to {channel_or_user} for user {target_user_id}")
        return message
    except Exception as e:
        logger.error(f"Failed to send test departure embed (dual): {e}")
        return None

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
    if isinstance(clear_time, str):
        from dateutil import parser
        clear_time_dt = parser.parse(clear_time)
    else:
        clear_time_dt = clear_time

    JST = timezone(timedelta(hours=9))
    clear_time_jst = clear_time_dt.astimezone(JST)
    unix_ts = int(clear_time_dt.replace(tzinfo=timezone.utc).timestamp())
    timestamp_str = f"<t:{unix_ts}:F>"

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
    ギルドから脱退したメンバーを通知する（Embedは日本語・英語両方）
    member_data: dict {mcid, discord_id, rank}
    """
    NOTIFY_CHANNEL_ID = int(get_config("MEMBER_NOTIFY_CHANNEL_ID") or "0")
    channel = bot.get_channel(NOTIFY_CHANNEL_ID)
    if not channel:
        logger.warning("メンバー通知チャンネルが見つかりません")
        return
    embed = discord.Embed(
        title="ゲーム内Guildのメンバーが退出しました",
        color=discord.Color.red()
    )
    embed.add_field(name="MCID", value=f"`{member_data.get('mcid', 'N/A')}`", inline=True)
    embed.add_field(name="Discord", value=f"<@{member_data.get('discord_id', 'N/A')}>", inline=True)
    embed.add_field(name="Rank", value=f"`{member_data.get('rank', 'N/A')}`", inline=True)
    embed.set_footer(text="脱退通知 | Minister Chikuwa")
    await channel.send(embed=embed)
    logger.info(f"Guild脱退通知: {member_data}")

    # --- ロール追加処理 ---
    DEPARTURE_IDS = [1271173606478708811, 1151511274165895228]
    discord_id = member_data.get('discord_id')
    if discord_id:
        guild = bot.get_guild(ETKW_SERVER)
        if guild:
            member = guild.get_member(int(discord_id))
            if member:
                roles_to_add = [guild.get_role(role_id) for role_id in DEPARTURE_IDS if guild.get_role(role_id)]
                if roles_to_add:
                    try:
                        await member.add_roles(*roles_to_add, reason="Guild removal auto role")
                    except Exception as e:
                        logger.warning(f"ロール追加失敗: {e}")

        # --- DM送信 (日英両方入りEmbed) ---
        user = bot.get_user(int(discord_id))
        embed_dm = create_departure_embed_dual()
        dm_failed = False
        try:
            logger.info("脱退通知Embed (dual) を該当メンバーに送信しました。")
            await user.send(embed=embed_dm)
        except Exception as e:
            logger.warning(f"DM送信失敗: {e}")
            dm_failed = True

        # DM送信失敗時、指定チャンネル(ID: 1271174069433274399)でメンション＋Embed送信
        if dm_failed:
            backup_channel_id = 1271174069433274399
            backup_channel = bot.get_channel(backup_channel_id)
            if backup_channel:
                logger.info("inactiveチャンネルに脱退通知Embed (dual) を該当メンバーに送信しました。")
                await backup_channel.send(
                    content=f"<@{discord_id}>",
                    embed=embed_dm
                )
            else:
                logger.warning(f"バックアップ通知チャンネル({backup_channel_id})が見つかりません")

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
        title="Discordのメンバーが退出しました",
        color=discord.Color.orange()
    )
    embed.add_field(name="MCID", value=f"`{member_data.get('mcid', 'N/A')}`", inline=True)
    if member_data['discord_id']:
        embed.add_field(name="Discord", value=f"<@{member_data.get('discord_id', 'N/A')}>", inline=True)
    else:
        embed.add_field(name="Discord", value="Discordなし", inline=True)
    embed.add_field(name="Rank", value=f"`{member_data.get('rank', 'N/A')}`", inline=True)
    embed.set_footer(text="脱退通知 | Minister Chikuwa")
    await channel.send(embed=embed)
    logger.info(f"Discord退出通知: {member_data}")
