import discord
from discord import app_commands
from discord.ext import commands
import logging
from lib.discord_notify import button_manager, create_departure_embed

logger = logging.getLogger(__name__)

class LanguageSwitchCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="switch", description="Switch language of your departure notification embed")
    @app_commands.describe(language="Language to switch to (ja for Japanese, en for English)")
    @app_commands.choices(language=[
        app_commands.Choice(name="日本語 (Japanese)", value="ja"),
        app_commands.Choice(name="English", value="en")
    ])
    async def switch_language(self, interaction: discord.Interaction, language: str):
        """Switch the language of departure notification embeds"""
        
        # Find messages belonging to this user
        user_messages = []
        for message_id, state in button_manager.message_states.items():
            if state['user_id'] == interaction.user.id:
                user_messages.append(message_id)
        
        if not user_messages:
            if language == "ja":
                await interaction.response.send_message(
                    "❌ 言語切替可能な脱退通知メッセージが見つかりません。", 
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    "❌ No departure notification messages found that can be switched.", 
                    ephemeral=True
                )
            return
        
        # Switch language for all user's messages and update them
        updated_count = 0
        failed_count = 0
        
        for message_id in user_messages:
            try:
                # Get current language
                current_language = button_manager.get_language(message_id)
                
                # Don't switch if already in the requested language
                if current_language == language:
                    continue
                
                # Update language
                button_manager.switch_language(message_id, language)
                
                # Try to find and update the message
                message = None
                
                # Try DM channel first
                try:
                    dm_channel = interaction.user.dm_channel
                    if dm_channel:
                        message = await dm_channel.fetch_message(message_id)
                except:
                    pass
                
                # If not found in DM, try to search in guild channels
                if not message:
                    for guild in self.bot.guilds:
                        for channel in guild.text_channels:
                            try:
                                message = await channel.fetch_message(message_id)
                                break
                            except:
                                continue
                        if message:
                            break
                
                if message:
                    new_embed = create_departure_embed(language)
                    
                    # Check if message has expired (15 minutes)
                    if button_manager.is_expired(message_id):
                        # Add timeout message to embed
                        if language == "en":
                            new_embed.add_field(
                                name="⏰ Button Timeout",
                                value="15 minutes have passed. Use `/switch ja` or `/switch en` to change language.",
                                inline=False
                            )
                        else:
                            new_embed.add_field(
                                name="⏰ ボタンタイムアウト", 
                                value="15分が経過しました。言語を変更するには `/switch ja` または `/switch en` コマンドをお使いください。",
                                inline=False
                            )
                        
                        # Disable buttons in the view
                        view = discord.ui.View.from_message(message) if message.components else None
                        if view:
                            for item in view.children:
                                item.disabled = True
                        
                        await message.edit(embed=new_embed, view=view)
                    else:
                        # Buttons are still active, keep the view
                        await message.edit(embed=new_embed)
                    
                    updated_count += 1
                else:
                    failed_count += 1
                    logger.warning(f"Could not find message {message_id} to update")
                    
            except Exception as e:
                failed_count += 1
                logger.error(f"Failed to update message {message_id}: {e}")
        
        # Send response
        if language == "ja":
            if updated_count > 0:
                await interaction.response.send_message(
                    f"✅ {updated_count}個のメッセージを日本語に切り替えました。", 
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    "📝 すでに日本語で表示されています。", 
                    ephemeral=True
                )
        else:
            if updated_count > 0:
                await interaction.response.send_message(
                    f"✅ {updated_count} message(s) switched to English.", 
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    "📝 Already displaying in English.", 
                    ephemeral=True
                )

async def setup(bot: commands.Bot):
    await bot.add_cog(LanguageSwitchCog(bot))