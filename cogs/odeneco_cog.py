import discord
import asyncio
from discord.ext import commands
import logging

from config import (
    ODENECO_AUTHORIZED_USERS,
    ODENECO_TARGET_CHANNEL,
    ODENECO_TARGET_ROLE,
    send_authorized_only_message
)
from lib.utils import create_embed

logger = logging.getLogger(__name__)

class OdenecoCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.ping_task = None
        self.is_pinging = False
        logger.info(f"--- [Cog] {self.__class__.__name__} が読み込まれました。")

    @discord.app_commands.command(name="odeneco", description="指定のロールを1秒おきにpingし続ける")
    async def odeneco_command(self, interaction: discord.Interaction):
        # 権限チェック
        if interaction.user.id not in ODENECO_AUTHORIZED_USERS:
            await send_authorized_only_message(interaction, ODENECO_AUTHORIZED_USERS)
            return

        # 既にpingが実行中の場合
        if self.is_pinging:
            embed = create_embed(
                title="既にpingが実行中yanen",
                description="既にpingが実行されていますゆお。停止するには `/stop` コマンドを使用してくだし。",
                color=discord.Color.orange(),
                footer_text="おでんぴんぐ"
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # pingタスクを開始
        self.is_pinging = True
        self.ping_task = asyncio.create_task(self._ping_loop())
        
        embed = create_embed(
            title="おでんをPingし始めたよ！",
            description=f"<#{ODENECO_TARGET_CHANNEL}> で <@&{ODENECO_TARGET_ROLE}> のpingを開始したよ！\n停止するには `/stop` コマンドを使用しよう！",
            color=discord.Color.green(),
            footer_text="おでんぴんぐ"
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        logger.info(f"--- [Odeneco] {interaction.user.name} がodenecoを開始しました")

    @discord.app_commands.command(name="stop", description="odenecoのpingを停止する")
    async def stop_command(self, interaction: discord.Interaction):
        # 権限チェック
        if interaction.user.id not in ODENECO_AUTHORIZED_USERS:
            await send_authorized_only_message(interaction, ODENECO_AUTHORIZED_USERS)
            return

        # pingが実行中でない場合
        if not self.is_pinging:
            embed = create_embed(
                title="pingは実行されていませんyo",
                description="現在おでんさんのぴんぎんぐは実行されていません。",
                color=discord.Color.orange(),
                footer_text="おでんぴんぐ"
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # pingタスクを停止
        self.is_pinging = False
        if self.ping_task:
            self.ping_task.cancel()
            self.ping_task = None

        embed = create_embed(
            title="おでんをPingし終わったよ！",
            description="pingを停止したよ！",
            color=discord.Color.red(),
            footer_text="おでんぴんぐ"
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        logger.info(f"--- [Odeneco] {interaction.user.name} がodenecoを停止しました")

    async def _ping_loop(self):
        """1秒おきにpingを送信するループ"""
        try:
            channel = self.bot.get_channel(ODENECO_TARGET_CHANNEL)
            if not channel:
                logger.error(f"--- [Odeneco] チャンネル {ODENECO_TARGET_CHANNEL} が見つかりません")
                return

            while self.is_pinging:
                try:
                    await channel.send(f"<@&{ODENECO_TARGET_ROLE}>")
                    await asyncio.sleep(1)
                except discord.Forbidden:
                    logger.error(f"--- [Odeneco] チャンネル {channel.name} に送信権限がありません")
                    self.is_pinging = False
                    break
                except Exception as e:
                    logger.error(f"--- [Odeneco] ping送信エラー: {e}")
                    await asyncio.sleep(1)  # エラー時も1秒待つ
                    
        except asyncio.CancelledError:
            logger.info("--- [Odeneco] pingタスクがキャンセルされました")
        except Exception as e:
            logger.error(f"--- [Odeneco] ping_loopで予期しない例外: {e}", exc_info=True)
        finally:
            self.is_pinging = False

    async def cog_unload(self):
        """Cog削除時にタスクを停止"""
        if self.ping_task:
            self.ping_task.cancel()
            self.is_pinging = False

# セットアップ関数
async def setup(bot: commands.Bot):
    await bot.add_cog(OdenecoCog(bot))