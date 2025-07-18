import discord
from discord import app_commands
from discord.ext import commands
import logging

from lib.database_handler import set_setting

logger = logging.getLogger(__name__)

@app_commands.checks.has_permissions(administrator=True) # このグループのコマンドは管理者のみ
class TrackerCog(commands.GroupCog, group_name="raidtracker", description="レイドトラッカー関連のコマンド"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        logger.info(f"--- [Cog] {self.__class__.__name__} が読み込まれました。")

    @app_commands.command(name="channel", description="ギルドレイドの通知を送信するチャンネルを設定します。")
    @app_commands.describe(channel="通知を送信するテキストチャンネル")
    async def set_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        set_setting("raid_notification_channel", str(channel.id))
        await interaction.response.send_message(
            f"✅ ギルドレイドの通知チャンネルを {channel.mention} に設定しました。",
            ephemeral=True
        )
        logger.info(f"ギルドレイドの通知チャンネルが更新されました: {channel.mention}")

async def setup(bot: commands.Bot):
    await bot.add_cog(TrackerCog(bot))
