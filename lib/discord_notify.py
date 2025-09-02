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
    "* ご自身でギルドから抜けた場合には、このメッセージは無視してください。\n\n"
    "最近、Wynncraft内での活動が盛んではないかつ、新しいメンバーが加入するためにキックいたしました。\n"
    "再度加入したい場合は、[こちらのチャンネル]({channel_link})でその旨伝えてください。\n"
    "またWynncraftにログインできなくなる理由がある場合は、ここで伝えてもらえれば枠をキープすることもできます。"
)

ENGLISH_MESSAGE = (
    "* If you left the guild yourself, please ignore this message.\n\n"
    "You were kicked because there hasn't been much activity in Wynncraft recently and to make way for new members.\n"
    "If you would like to rejoin, please let us know [here]({channel_link}).\n"
    "Also, if there is a reason why you can no longer log in to Wynncraft, you can let us know there and we will be able to keep your spot."
)

def get_emoji_for_raid(raid_name):
    return RAID_EMOJIS.get(raid_name, DEFAULT_EMOJI)

# Button-based language switching system
class ButtonLanguageManager:
    def __init__(self):
        # Store message states: {message_id: {'user_id': int, 'language': str, 'created_at': float}}
        self.message_states = {}
        self.timeout_seconds = 15 * 60  # 15 minutes
        
    def add_message(self, message_id: int, target_user_id: int, initial_language: str = "ja"):
        """Register a message for button-based language switching"""
        self.message_states[message_id] = {
            'user_id': target_user_id,
            'language': initial_language,
            'created_at': time.time()
        }
        
    def remove_message(self, message_id: int):
        """Remove a message from tracking"""
        self.message_states.pop(message_id, None)
        
    def can_switch_language(self, message_id: int, user_id: int) -> bool:
        """Check if user can switch language (permission + timeout)"""
        state = self.message_states.get(message_id)
        if not state:
            return False
            
        # Check if user is authorized
        if state['user_id'] != user_id:
            return False
            
        # Check 15-minute timeout
        current_time = time.time()
        if current_time - state['created_at'] > self.timeout_seconds:
            return False
            
        return True
        
    def is_expired(self, message_id: int) -> bool:
        """Check if the message has exceeded the 15-minute timeout"""
        state = self.message_states.get(message_id)
        if not state:
            return True
            
        current_time = time.time()
        return current_time - state['created_at'] > self.timeout_seconds
        
    def switch_language(self, message_id: int, new_language: str):
        """Switch language"""
        if message_id in self.message_states:
            self.message_states[message_id]['language'] = new_language
            
    def get_language(self, message_id: int) -> str:
        """Get current language for message"""
        state = self.message_states.get(message_id)
        return state['language'] if state else "ja"

# Global instance
button_manager = ButtonLanguageManager()

class LanguageSwitchView(discord.ui.View):
    def __init__(self, message_id: int, target_user_id: int):
        super().__init__(timeout=15 * 60)  # 15 minutes timeout
        self.message_id = message_id
        self.target_user_id = target_user_id
        
    @discord.ui.button(label="🇯🇵 日本語", style=discord.ButtonStyle.secondary)
    async def japanese_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_language_switch(interaction, "ja")
        
    @discord.ui.button(label="🇬🇧 English", style=discord.ButtonStyle.secondary)
    async def english_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_language_switch(interaction, "en")
        
    @discord.ui.button(label="🗑️ Delete", style=discord.ButtonStyle.danger)
    async def delete_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Only the target user can delete
        if interaction.user.id != self.target_user_id:
            await interaction.response.send_message("❌ このメッセージを削除する権限がありません。", ephemeral=True)
            return
            
        try:
            button_manager.remove_message(self.message_id)
            await interaction.response.edit_message(content="🗑️ メッセージが削除されました。", embed=None, view=None)
        except Exception as e:
            logger.error(f"Failed to delete message: {e}")
            await interaction.response.send_message("❌ メッセージの削除に失敗しました。", ephemeral=True)
    
    async def handle_language_switch(self, interaction: discord.Interaction, new_language: str):
        # Check if user can switch
        if not button_manager.can_switch_language(self.message_id, interaction.user.id):
            if interaction.user.id != self.target_user_id:
                await interaction.response.send_message("❌ 言語を切り替える権限がありません。", ephemeral=True)
            else:
                await interaction.response.send_message(
                    "⏰ 15分が経過したため、ボタンによる言語切替はできません。\n"
                    "`/switch ja` または `/switch en` コマンドをお使いください。", 
                    ephemeral=True
                )
            return
            
        # Get current language
        current_language = button_manager.get_language(self.message_id)
        
        # Don't switch if already in the requested language
        if current_language == new_language:
            lang_name = "日本語" if new_language == "ja" else "English"
            await interaction.response.send_message(f"📝 すでに{lang_name}で表示されています。", ephemeral=True)
            return
            
        # Update language and edit message
        button_manager.switch_language(self.message_id, new_language)
        new_embed = create_departure_embed(new_language)
        
        try:
            await interaction.response.edit_message(embed=new_embed, view=self)
        except Exception as e:
            logger.error(f"Failed to edit message: {e}")
            await interaction.response.send_message("❌ メッセージの更新に失敗しました。", ephemeral=True)
    
    async def on_timeout(self):
        """Called when the view times out (15 minutes)"""
        try:
            # Disable all buttons
            for item in self.children:
                item.disabled = True
            
            # Update the message to show timeout instructions
            current_language = button_manager.get_language(self.message_id)
            embed = create_departure_embed(current_language)
            
            # Add timeout message to embed
            if current_language == "en":
                embed.add_field(
                    name="⏰ Button Timeout",
                    value="15 minutes have passed. Use `/switch ja` or `/switch en` to change language.",
                    inline=False
                )
            else:
                embed.add_field(
                    name="⏰ ボタンタイムアウト",
                    value="15分が経過しました。言語を変更するには `/switch ja` または `/switch en` コマンドをお使いください。",
                    inline=False
                )
            
            # We need to get the message to edit it
            # This is a bit tricky since we don't have direct access to the message
            # The interaction should handle this, but we'll implement it when we can access the message
            pass
        except Exception as e:
            logger.error(f"Error in view timeout: {e}")

def create_departure_embed(language: str = "ja") -> discord.Embed:
    """Create departure notification embed in specified language"""
    if language == "en":
        return discord.Embed(
            title="Guild Departure Notice",
            description=ENGLISH_MESSAGE.format(channel_link=channel_link),
            color=discord.Color.red()
        )
    else:
        return discord.Embed(
            title="ギルド脱退のお知らせ",
            description=JAPANESE_MESSAGE.format(channel_link=channel_link),
            color=discord.Color.red()
        )

# Note: get_user_for_reaction_removal function removed as it's no longer needed for button interactions

async def setup_button_language_switching(bot, message: discord.Message, target_user_id: int):
    """Setup button-based language switching for a message"""
    # Register the message
    button_manager.add_message(message.id, target_user_id)
    
    # Create and attach the view with buttons
    view = LanguageSwitchView(message.id, target_user_id)
    
    try:
        await message.edit(view=view)
    except Exception as e:
        logger.error(f"Failed to add language switching buttons: {e}")

# Note: The old reaction-based handler has been replaced with button interactions
# The button interactions are handled within the LanguageSwitchView class above

async def send_test_departure_embed(bot, channel_or_user, target_user_id: int):
    """
    Utility function for sending a test departure embed that can be deleted anytime.
    
    Args:
        bot: Discord bot instance
        channel_or_user: Channel or User object to send to
        target_user_id: ID of the user who can control the embed
    """
    embed = create_departure_embed("ja")  # Start with Japanese
    view = LanguageSwitchView(0, target_user_id)  # Temporary message_id, will be updated
    
    try:
        message = await channel_or_user.send(embed=embed, view=view)
        
        # Update the view with the actual message ID
        view.message_id = message.id
        button_manager.add_message(message.id, target_user_id)
        
        logger.info(f"Test departure embed sent to {channel_or_user} for user {target_user_id}")
        return message
    except Exception as e:
        logger.error(f"Failed to send test departure embed: {e}")
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

        # --- DM送信 (新しいボタン方式) ---
        user = bot.get_user(int(discord_id))
        embed_dm = create_departure_embed("ja")  # Start with Japanese
        view = LanguageSwitchView(0, int(discord_id))  # Temporary message_id, will be updated
        
        dm_failed = False
        try:
            logger.info("脱退通知Embedを該当メンバーに送信しました。")
            message = await user.send(embed=embed_dm, view=view)
            
            # Update the view with the actual message ID
            view.message_id = message.id
            button_manager.add_message(message.id, int(discord_id))
        except Exception as e:
            logger.warning(f"DM送信失敗: {e}")
            dm_failed = True

        # DM送信失敗時、指定チャンネル（ID: 1271174069433274399）でメンション＋Embed送信
        if dm_failed:
            backup_channel_id = 1271174069433274399
            backup_channel = bot.get_channel(backup_channel_id)
            if backup_channel:
                logger.info("inactiveチャンネルに脱退通知Embedを該当メンバーに送信しました。")
                backup_view = LanguageSwitchView(0, int(discord_id))  # Temporary message_id, will be updated
                message = await backup_channel.send(
                    content=f"<@{discord_id}>",
                    embed=embed_dm,
                    view=backup_view
                )
                
                # Update the view with the actual message ID
                backup_view.message_id = message.id
                button_manager.add_message(message.id, int(discord_id))
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
