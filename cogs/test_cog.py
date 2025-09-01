import discord
from discord import app_commands
from discord.ext import commands
import logging
from config import AUTHORIZED_USER_IDS, send_authorized_only_message
from lib.discord_notify import send_test_departure_embed

logger = logging.getLogger(__name__)

class TestCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="test_departure", description="Send a test departure notification embed")
    @app_commands.describe(
        user="Target user who can control the embed",
        channel="Channel to send to (optional, defaults to current channel)"
    )
    async def test_departure(
        self, 
        interaction: discord.Interaction, 
        user: discord.User,
        channel: discord.TextChannel = None
    ):
        # Check authorization
        if interaction.user.id not in AUTHORIZED_USER_IDS:
            await send_authorized_only_message(interaction)
            return

        await interaction.response.defer(ephemeral=True)
        
        target_channel = channel or interaction.channel
        
        try:
            message = await send_test_departure_embed(self.bot, target_channel, user.id)
            if message:
                await interaction.followup.send(
                    f"✅ Test departure embed sent to {target_channel.mention} for {user.mention}\n"
                    f"User can react with 🇯🇵 (Japanese), 🇬🇧 (English), or 🗑️ (Delete)",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    "❌ Failed to send test departure embed",
                    ephemeral=True
                )
        except Exception as e:
            logger.error(f"Error in test_departure command: {e}")
            await interaction.followup.send(
                f"❌ Error sending test embed: {e}",
                ephemeral=True
            )

    @app_commands.command(name="test_departure_dm", description="Send a test departure notification embed via DM")
    @app_commands.describe(user="Target user who can control the embed")
    async def test_departure_dm(self, interaction: discord.Interaction, user: discord.User):
        # Check authorization
        if interaction.user.id not in AUTHORIZED_USER_IDS:
            await send_authorized_only_message(interaction)
            return

        await interaction.response.defer(ephemeral=True)
        
        try:
            message = await send_test_departure_embed(self.bot, user, user.id)
            if message:
                await interaction.followup.send(
                    f"✅ Test departure embed sent via DM to {user.mention}\n"
                    f"User can react with 🇯🇵 (Japanese), 🇬🇧 (English), or 🗑️ (Delete)",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    "❌ Failed to send test departure embed via DM",
                    ephemeral=True
                )
        except Exception as e:
            logger.error(f"Error in test_departure_dm command: {e}")
            await interaction.followup.send(
                f"❌ Error sending test DM: {e}",
                ephemeral=True
            )

async def setup(bot: commands.Bot):
    await bot.add_cog(TestCog(bot))