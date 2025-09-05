import discord
import logging
from lib.db import get_config
import os
from datetime import timezone, timedelta
from config import ETKW_SERVER

logger = logging.getLogger(__name__)

backup_channel_id = 1271174069433274399
channel_link = f"https://discord.com/channels/{str(ETKW_SERVER)}/{backup_channel_id}"

RAID_EMOJIS = {
    "The Nameless Anomaly": "<:wynn_tna:1400385557795835958>",
    "The Canyon Colossus": "<:wynn_tcc:1400385514460155914>",
    "Orphion's Nexus of Light": "<:wynn_nol:1400385439508074618>",
    "Nest of the Grootslangs": "<:wynn_notg:1400385362299195424>"
}
DEFAULT_EMOJI = "🎲"

JAPANESE_MESSAGE = (
    "ご自身でギルドから抜けた場合には、このメッセージは無視してください。\n\n"
    "最近、Wynncraft内での活動が盛んではないかつ、新しいメンバーが加入するためにキックいたしました。\n"
    "再度加入したい場合は、[こちらのチャンネル]({channel_link})でその旨伝えてください。\n"
    "またWynncraftにログインできなくなる理由がある場合は、ここで伝えてもらえれば枠をキープすることもできます。\n\n"
    "By reacting with 🇺🇸 on this Embed, all messeages will be translated."
)

ENGLISH_MESSAGE = (
    "If you left the guild yourself, please ignore this message.\n\n"
    "You were kicked because there hasn't been much activity in Wynncraft recently and to make way for new members.\n"
    "If you would like to rejoin, please let us know [here]({channel_link}).\n"
    "Also, if there is a reason why you can no longer log in to Wynncraft, you can let us know there and we will be able to keep your spot.\n\n"
    "🇯🇵でこのEmbedにリアクションすると、日本語に翻訳されます。"
)

def get_emoji_for_raid(raid_name):
    return RAID_EMOJIS.get(raid_name, DEFAULT_EMOJI)

def make_japanese_embed() -> discord.Embed:
    embed = discord.Embed(
        title="ギルド脱退のお知らせ",
        description=JAPANESE_MESSAGE.format(channel_link=channel_link),
        color=discord.Color.red()
    )
    embed.set_footer(text="Inactive通知 | Minister Chikuwa")
    return embed

def make_english_embed() -> discord.Embed:
    embed = discord.Embed(
        title="Guild Departure Notice",
        description=ENGLISH_MESSAGE.format(channel_link=channel_link),
        color=discord.Color.red()
    )
    embed.set_footer(text="Inactive Notification | Minister Chikuwa")
    return embed

async def send_language_select_embed(user_or_channel, is_dm=False):
    """
    日本語Embedを送信し、リアクションを付与
    """
    embed = make_japanese_embed()
    message = await user_or_channel.send(embed=embed)
    try:
        await message.add_reaction("🇯🇵")
        await message.add_reaction("🇺🇸")
    except Exception as e:
        logger.warning(f"リアクション付与失敗: {e}")
    return message

def get_embed_language(embed: discord.Embed):
    """フッターから言語を判定(lang:ja/lang:en)"""
    if embed.footer and embed.footer.text:
        if "lang:ja" in embed.footer.text:
            return "ja"
        if "lang:en" in embed.footer.text:
            return "en"
    # 旧仕様や手動の場合は本文などから判定もあり
    return None

async def on_raw_reaction_add(bot, payload):
    if payload.user_id == bot.user.id:
        return

    if payload.emoji.name not in ["🇯🇵", "🇺🇸"]:
        return

    channel = bot.get_channel(payload.channel_id)
    if channel is None:
        logger.warning("チャンネル取得失敗")
        return

    try:
        message = await channel.fetch_message(payload.message_id)
    except Exception:
        logger.warning("メッセージ取得失敗")
        return

    is_dm = isinstance(channel, discord.DMChannel) or (hasattr(channel, "type") and channel.type == discord.ChannelType.private)

    # 現在のEmbedの言語判定
    if not message.embeds:
        logger.warning("メッセージにEmbedがありません")
        return
    current_embed = message.embeds[0]
    current_lang = get_embed_language(current_embed)

    # 押されたリアクションが現状と同じ言語なら何もしない
    if (payload.emoji.name == "🇯🇵" and current_lang == "ja") or (payload.emoji.name == "🇺🇸" and current_lang == "en"):
        return

    # 切替先Embed生成
    if payload.emoji.name == "🇯🇵":
        new_embed = make_japanese_embed()
    else:
        new_embed = make_english_embed()

    if is_dm:
        # DMの場合: 前のEmbedメッセージを削除→新メッセージ送信＋リアクション付与
        try:
            await message.delete()
        except Exception as e:
            logger.warning(f"前のEmbed削除失敗: {e}")
        user = await bot.fetch_user(payload.user_id)
        try:
            new_msg = await user.send(embed=new_embed)
            await new_msg.add_reaction("🇯🇵")
            await new_msg.add_reaction("🇺🇸")
        except Exception as e:
            logger.warning(f"DMでのEmbed送信またはリアクション失敗: {e}")
    else:
        # チャンネルはEmbed編集＋リアクション削除
        try:
            await message.edit(embed=new_embed)
            guild = message.guild
            user = guild.get_member(payload.user_id)
            await message.remove_reaction(payload.emoji, user)
        except Exception as e:
            logger.warning(f"Embed編集またはリアクション削除失敗: {e}")

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

        user = bot.get_user(int(discord_id))
        embed_dm = make_japanese_embed()
        dm_failed = False
        try:
            logger.info("脱退通知Embedを該当メンバーに送信しました。")
            await user.send(embed=embed_dm)
        except Exception as e:
            logger.warning(f"DM送信失敗: {e}")
            dm_failed = True

        if dm_failed:
            backup_channel_id = 1271174069433274399
            backup_channel = bot.get_channel(backup_channel_id)
            if backup_channel:
                logger.info("inactiveチャンネルに脱退通知Embedを該当メンバーに送信しました。")
                await backup_channel.send(
                    content=f"<@{discord_id}>",
                    embed=embed_dm
                )
            else:
                logger.warning(f"バックアップ通知チャンネル({backup_channel_id})が見つかりません")

async def notify_member_left_discord(bot, member_data):
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
