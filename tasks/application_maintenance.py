import discord
from discord.ext import tasks, commands
import asyncio
import logging
from datetime import datetime

from lib.application_views import create_application_embed, ApplicationButtonView
from config import APPLICATION_CHANNEL_ID

logger = logging.getLogger(__name__)

class ApplicationMaintenance(commands.Cog):
    """申請システムのメンテナンス用Cog"""
    
    def __init__(self, bot):
        self.bot = bot
        self.application_embed_maintenance.start()
    
    def cog_unload(self):
        self.application_embed_maintenance.cancel()
    
    @tasks.loop(minutes=30)
    async def application_embed_maintenance(self):
        """申請Embedの維持・復旧タスク"""
        try:
            await self.maintain_application_embed()
        except Exception as e:
            logger.error(f"[ApplicationMaintenance] 申請Embed維持タスクでエラー: {e}", exc_info=True)
    
    @application_embed_maintenance.before_loop
    async def before_maintenance(self):
        """タスク開始前の待機"""
        await self.bot.wait_until_ready()
        # 起動後少し待ってから開始
        await asyncio.sleep(10)
    
    async def maintain_application_embed(self):
        """申請チャンネルに申請Embedが存在するかチェックし、なければ作成"""
        try:
            channel = self.bot.get_channel(APPLICATION_CHANNEL_ID)
            if not channel:
                logger.warning(f"[ApplicationMaintenance] 申請チャンネル {APPLICATION_CHANNEL_ID} が見つかりません")
                return
            
            # 最新のメッセージを確認
            found_application_embed = False
            
            async for message in channel.history(limit=50):
                # Botのメッセージで申請Embedがあるかチェック
                if (message.author == self.bot.user and 
                    message.embeds and 
                    len(message.embeds) > 0 and
                    "ETKW ギルド加入申請" in message.embeds[0].title and
                    message.components):
                    found_application_embed = True
                    logger.debug("[ApplicationMaintenance] 申請Embedが既に存在します")
                    break
            
            if not found_application_embed:
                logger.info("[ApplicationMaintenance] 申請Embedが見つからないため、新規作成します")
                embed = create_application_embed()
                view = ApplicationButtonView()
                await channel.send(embed=embed, view=view)
                logger.info("[ApplicationMaintenance] 申請Embedを新規作成しました")
            
        except Exception as e:
            logger.error(f"[ApplicationMaintenance] 申請Embed維持処理でエラー: {e}", exc_info=True)


async def setup(bot):
    """Cogのセットアップ"""
    await bot.add_cog(ApplicationMaintenance(bot))
    logger.info("[ApplicationMaintenance] 申請システムメンテナンスタスクを開始しました")