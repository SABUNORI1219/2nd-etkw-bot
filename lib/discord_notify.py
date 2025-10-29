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
    "またWynncraftにログインできなくなる理由がある場合は、ここで伝えてもらえれば枠をキープすることもできます。"
)

ENGLISH_MESSAGE = (
    "If you left the guild yourself, please ignore this message.\n\n"
    "You were kicked because there hasn't been much activity in Wynncraft recently and to make way for new members.\n"
    "If you would like to rejoin, please let us know [here]({channel_link}).\n"
    "Also, if there is a reason why you can no longer log in to Wynncraft, you can let us know there and we will be able to keep your spot."
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

class LanguageSwitchView(discord.ui.View):
    def __init__(self, initial_lang="ja"):
        super().__init__(timeout=None)
        self.initial_lang = initial_lang

    @discord.ui.button(label="🇯🇵 日本語", style=discord.ButtonStyle.secondary, custom_id="lang_ja")
    async def ja_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = make_japanese_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="🇬🇧 English", style=discord.ButtonStyle.secondary, custom_id="lang_en")
    async def en_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = make_english_embed()
        await interaction.response.edit_message(embed=embed, view=self)

async def send_language_select_embed(user_or_channel, is_dm=False):
    """日本語Embedと切替ボタンを送信"""
    embed = make_japanese_embed()
    view = LanguageSwitchView(initial_lang="ja")
    return await user_or_channel.send(embed=embed, view=view)

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
    from datetime import datetime, timedelta
    from lib.db import get_last_join_cache_for_members
    
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

    # last_join_cacheを参照してロールを決定
    LONG_ABSENCE_ROLE_ID = 1271173606478708811  # 1週間以上非アクティブ
    SHORT_ABSENCE_ROLE_ID = 1151511274165895228  # 1週間未満
    
    discord_id = member_data.get('discord_id')
    mcid = member_data.get('mcid')
    
    if discord_id and mcid:
        # last_join_cacheから最終ログイン時刻を取得
        last_join_data = get_last_join_cache_for_members([mcid])
        last_join_str = last_join_data.get(mcid)
        
        role_id_to_add = SHORT_ABSENCE_ROLE_ID  # デフォルトは短期間非アクティブ
        
        if last_join_str:
            try:
                # lastJoinは "2024-10-29T12:34:56.789Z" 形式
                last_join_time = datetime.fromisoformat(last_join_str.replace('Z', '+00:00'))
                now = datetime.now(last_join_time.tzinfo)  # 同じタイムゾーンで比較
                days_since_last_join = (now - last_join_time).days
                
                if days_since_last_join >= 7:
                    role_id_to_add = LONG_ABSENCE_ROLE_ID
                    logger.info(f"[MemberRemoved] {mcid}: {days_since_last_join}日前が最終ログイン → 長期非アクティブロール付与")
                else:
                    logger.info(f"[MemberRemoved] {mcid}: {days_since_last_join}日前が最終ログイン → 短期非アクティブロール付与")
                    
            except Exception as e:
                logger.warning(f"[MemberRemoved] {mcid}: lastJoin解析失敗 ({last_join_str}) → デフォルトロール付与: {e}")
        else:
            logger.info(f"[MemberRemoved] {mcid}: lastJoinデータなし → デフォルトロール付与")
        
        guild = bot.get_guild(ETKW_SERVER)
        if guild:
            member = guild.get_member(int(discord_id))
            if member:
                role_to_add = guild.get_role(role_id_to_add)
                if role_to_add:
                    try:
                        await member.add_roles(role_to_add)
                        logger.info(f"[MemberRemoved] {mcid}: {role_to_add.name}ロール付与完了")
                    except Exception as e:
                        logger.warning(f"ロール追加失敗: {e}")

        user = bot.get_user(int(discord_id))
        embed_dm = make_japanese_embed()
        dm_failed = False
        try:
            logger.info("脱退通知Embedを該当メンバーに送信しました。")
            await user.send(embed=embed_dm, view=LanguageSwitchView())
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
                    embed=embed_dm,
                    view=LanguageSwitchView()
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
