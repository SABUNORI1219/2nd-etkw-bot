import discord
from discord import app_commands
from discord.ext import commands
from lib.db import fetch_history
import os
import logging

logger = logging.getLogger(__name__)

AUTHORIZED_USER_IDS = [1062535250099589120]  # サンプルID

# コマンド許可範囲の指定（guildsのみ）
@app_commands.allowed_installs(guilds=True, users=False)
@app_commands.allowed_contexts(guilds=True, dms=False, private_channels=True)
class GuildRaidDetector(commands.GroupCog, name="graid"):
  def __init__(self, bot):
        self.bot = bot

  # 通知チャンネル設定コマンド
  @app_commands.command(name="channel", description="Guild Raid通知チャンネルを設定します")
  async def guildraid_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
      # 権限チェック
      if interaction.user.id not in AUTHORIZED_USER_IDS:
        await interaction.response.send_message("権限がありません。", ephemeral=True)
        return
      os.environ["NOTIFY_CHANNEL_ID"] = str(channel.id)
      await interaction.response.send_message(f"Guild Raid通知チャンネルを {channel.mention} に設定しました。", ephemeral=True)
      logger.info(f"通知チャンネル設定: {channel.id}")

# 履歴リスト出力コマンド
  @app_commands.command(name="list", description="指定レイド・日付の履歴をリスト表示します")
  async def guildraid_list(self, interaction: discord.Interaction, raid_name: str, date: str = None):
    if interaction.user.id not in AUTHORIZED_USER_IDS:
        await interaction.response.send_message("権限がありません。", ephemeral=True)
        return
    rows = fetch_history(raid_name=raid_name, date_from=date)
    if not rows:
        await interaction.response.send_message("履歴がありません。", ephemeral=True)
        return
    msg = "\n".join([f"{r[1]} {', '.join(r[3])} サーバー:{r[4]} 信頼度:{r[5]}" for r in rows])
    await interaction.response.send_message(msg, ephemeral=True)
    logger.info(f"履歴リスト出力: {raid_name} {date}")

  # 管理者補正コマンド
  @app_commands.command(name="count", description="指定プレイヤーのレイドクリア回数を補正します")
  async def guildraid_count(self, interaction: discord.Interaction, player: str, raid_name: str, count: int):
    if interaction.user.id not in AUTHORIZED_USER_IDS:
        await interaction.response.send_message("権限がありません。", ephemeral=True)
        return
    # 補正ロジックは未実装
    await interaction.response.send_message(f"{player}の{raid_name}クリア回数を{count}だけ補正します（未実装）", ephemeral=True)
    logger.info(f"管理者補正: {player} {raid_name} {count}")

# セットアップ関数
async def setup(bot: commands.Bot):
    await bot.add_cog(GuildRaidDetector(bot))
