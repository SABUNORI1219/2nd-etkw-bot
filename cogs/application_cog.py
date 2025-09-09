import discord
from discord.ext import commands
from discord import app_commands
import logging
from config import AUTHORIZED_USER_IDS, send_authorized_only_message
from lib.application_views import send_application_embed

logger = logging.getLogger(__name__)

class ApplicationCog(commands.Cog):
    """申請システム管理用のCog"""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        logger.info(f"--- [Cog] {self.__class__.__name__} が読み込まれました。")

    @app_commands.command(name="send_application_embed", description="申請チャンネルに申請Embedを送信します（管理者専用）")
    async def send_application_embed_command(self, interaction: discord.Interaction):
        """申請Embedを手動送信するコマンド"""
        
        # 権限チェック
        if interaction.user.id not in AUTHORIZED_USER_IDS:
            await send_authorized_only_message(interaction)
            return
        
        try:
            await interaction.response.defer()
            
            # 現在のチャンネルに申請Embedを送信
            await send_application_embed(interaction.channel)
            
            await interaction.followup.send("✅ 申請Embedを送信しました。", ephemeral=True)
            logger.info(f"申請Embedを手動送信: チャンネル {interaction.channel.name} (ID: {interaction.channel.id})")
            
        except Exception as e:
            logger.error(f"申請Embed送信でエラー: {e}", exc_info=True)
            await interaction.followup.send("❌ 申請Embedの送信に失敗しました。", ephemeral=True)

    @app_commands.command(name="application_stats", description="申請システムの統計情報を表示します（管理者専用）")
    async def application_stats_command(self, interaction: discord.Interaction):
        """申請システムの統計情報を表示"""
        
        # 権限チェック
        if interaction.user.id not in AUTHORIZED_USER_IDS:
            await send_authorized_only_message(interaction)
            return
        
        try:
            await interaction.response.defer()
            
            from lib.db import get_all_applications
            applications = get_all_applications()
            
            embed = discord.Embed(
                title="📊 申請システム統計",
                color=discord.Color.blue()
            )
            
            if applications:
                embed.add_field(
                    name="現在の申請数", 
                    value=f"{len(applications)}件", 
                    inline=True
                )
                
                # 最新の申請を表示
                latest_app = applications[-1]
                embed.add_field(
                    name="最新申請", 
                    value=f"MCID: {latest_app['mcid']}", 
                    inline=True
                )
                
                # 申請リスト
                app_list = []
                for app in applications[-5:]:  # 最新5件
                    app_list.append(f"• {app['mcid']} (<#{app['channel_id']}>)")
                
                if app_list:
                    embed.add_field(
                        name="申請一覧（最新5件）", 
                        value="\n".join(app_list), 
                        inline=False
                    )
            else:
                embed.add_field(
                    name="現在の申請数", 
                    value="0件", 
                    inline=False
                )
                embed.add_field(
                    name="状況", 
                    value="現在、申請中のメンバーはいません。", 
                    inline=False
                )
            
            embed.set_footer(text="申請システム管理 | Minister Chikuwa Bot")
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            logger.error(f"申請統計取得でエラー: {e}", exc_info=True)
            await interaction.followup.send("❌ 統計情報の取得に失敗しました。", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(ApplicationCog(bot))