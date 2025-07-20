import discord
from discord import app_commands
from discord.ext import commands
from lib.db import fetch_history, set_config
import os
import logging

logger = logging.getLogger(__name__)
AUTHORIZED_USER_IDS = [1062535250099589120]  # サンプルID

# ページ付きEmbed用View
class PlayerCountView(discord.ui.View):
    def __init__(self, player_counts, page=0, per_page=10, timeout=120):
        super().__init__(timeout=timeout)
        self.player_counts = player_counts
        self.page = page
        self.per_page = per_page
        self.max_page = (len(player_counts) - 1) // per_page

    async def update_message(self, interaction):
        embed = discord.Embed(title="Guild Raid Player Counts")
        start = self.page * self.per_page
        end = start + self.per_page
        for name, count in self.player_counts[start:end]:
            embed.add_field(name=name, value=f"Count: {count}", inline=False)
        embed.set_footer(text=f"Page {self.page+1}/{self.max_page+1}")
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary)
    async def previous(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page > 0:
            self.page -= 1
            await self.update_message(interaction)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page < self.max_page:
            self.page += 1
            await self.update_message(interaction)

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
      set_config("NOTIFY_CHANNEL_ID", str(channel.id))
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

        # プレイヤーごとに累計カウント集計
        player_counts = {}
        for row in rows:
            # row[3]がparty_members
            for player in row[3]:
                player_counts[player] = player_counts.get(player, 0) + 1
        sorted_counts = sorted(player_counts.items(), key=lambda x: (-x[1], x[0]))

        # 最初のページを表示
        view = PlayerCountView(sorted_counts, page=0)
        embed = discord.Embed(title=f"Guild Raid Player Counts: {raid_name}")
        for name, count in sorted_counts[:10]:
            embed.add_field(name=name, value=f"Count: {count}", inline=False)
        embed.set_footer(text=f"Page 1/{view.max_page+1}")

        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        logger.info(f"履歴リスト出力: {raid_name} {date} (embed形式ページ付き)")

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
