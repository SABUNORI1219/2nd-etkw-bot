import discord
import logging
from lib.db import get_config
import os
from datetime import timezone, timedelta
from config.py import ETKW_SERVER

logger = logging.getLogger(__name__)

# レイド名ごとに対応する絵文字を登録
RAID_EMOJIS = {
    "The Nameless Anomaly": "<:wynn_tna:1400385557795835958>",
    "The Canyon Colossus": "<:wynn_tcc:1400385514460155914>",
    "Orphion's Nexus of Light": "<:wynn_nol:1400385439508074618>",
    "Nest of the Grootslangs": "<:wynn_notg:1400385362299195424>"
}
DEFAULT_EMOJI = "🎲"  # 未登録レイド用

JAPANESE_MESSAGE = (
    "* ご自身でギルドから抜けた場合には、このメッセージは無視してください。\n\n"
    "最近、Wynncraft内での活動が盛んではないかつ、新しいメンバーが加入するためにキックいたしました。\n"
    "再度加入したい場合は、ここでその旨伝えてください。\n"
    "またWynncraftにログインできなくなる理由がある場合は、ここで伝えてもらえれば枠をキープすることもできます。"
)

ENGLISH_MESSAGE = (
    "* If you left the guild yourself, please ignore this message.\n\n"
    "You were kicked because there hasn't been much activity in Wynncraft recently and to make way for new members.\n"
    "If you would like to rejoin, please let us know here.\n"
    "Also, if there is a reason why you can no longer log in to Wynncraft, you can let us know here and we will be able to keep your spot."
)

def get_emoji_for_raid(raid_name):
    return RAID_EMOJIS.get(raid_name, DEFAULT_EMOJI)

class LanguageSwitchView(discord.ui.View):
    def __init__(self, target_user_id):
        super().__init__(timeout=180)
        self.target_user_id = target_user_id
        self.language = "ja"  # デフォルト日本語

    @discord.ui.button(label="日本語で表示", style=discord.ButtonStyle.primary)
    async def show_japanese(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.target_user_id:
            await interaction.response.send_message("この操作はご本人のみ利用できます。", ephemeral=True)
            return
        embed = discord.Embed(
            title="ギルド脱退のお知らせ",
            description=JAPANESE_MESSAGE,
            color=discord.Color.red()
        )
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Show in English", style=discord.ButtonStyle.secondary)
    async def show_english(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.target_user_id:
            await interaction.response.send_message("This action is only available to the person concerned.", ephemeral=True)
            return
        embed = discord.Embed(
            title="Guild Departure Notice",
            description=ENGLISH_MESSAGE,
            color=discord.Color.red()
        )
        await interaction.response.edit_message(embed=embed, view=self)

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
    # 通知Embed（管理用チャンネルに送信）
    NOTIFY_CHANNEL_ID = int(get_config("MEMBER_NOTIFY_CHANNEL_ID") or "0")
    channel = bot.get_channel(NOTIFY_CHANNEL_ID)
    if not channel:
        logger.warning("メンバー通知チャンネルが見つかりません")
        return
    embed = discord.Embed(
        title="Guild Departure Notice",
        color=discord.Color.red()
    )
    embed.add_field(name="MCID", value=f"`{member_data.get('mcid', 'N/A')}`", inline=True)
    embed.add_field(name="Discord", value=f"<@{member_data.get('discord_id', 'N/A')}>", inline=True)
    embed.add_field(name="Rank", value=f"`{member_data.get('rank', 'N/A')}`", inline=True)
    embed.set_footer(text="脱退通知 | Minister Chikuwa")
    await channel.send(embed=embed)
    logger.info(f"Guild脱退通知: {member_data}")

    # --- ロール追加処理 ---
    DEPARTURE_IDS = [1271173606478708811, 1151511274165895228] # Inactive, Chikuwaed
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

        # --- DM送信 ---
        user = bot.get_user(int(discord_id))
        view = LanguageSwitchView(target_user_id=int(discord_id))
        embed_dm = discord.Embed(
            title="Guild Departure Notice",
            description=JAPANESE_MESSAGE,
            color=discord.Color.red()
        )
        dm_failed = False
        try:
            await user.send(embed=embed_dm, view=view)
        except Exception as e:
            logger.warning(f"DM送信失敗: {e}")
            dm_failed = True

        # DM送信失敗時、指定チャンネル（ID: 1271174069433274399）でメンション＋Embed送信
        if dm_failed:
            backup_channel_id = 1271174069433274399
            backup_channel = bot.get_channel(backup_channel_id)
            if backup_channel:
                await backup_channel.send(
                    content=f"<@{discord_id}>",
                    embed=embed_dm,
                    view=view
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
