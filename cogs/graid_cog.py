import discord
from discord import app_commands
from discord.ext import commands
from lib.json_store import (
    get_all_guild_player_counts, set_guild_player_count
)
from lib.json_store import set_config  # 通知チャンネル設定
import logging

logger = logging.getLogger(__name__)
AUTHORIZED_USER_IDS = [1062535250099589120]

RAID_CHOICES = [
    app_commands.Choice(name="Nest of the Grootslang", value="Nest of the Grootslang"),
    app_commands.Choice(name="Orphion's Nexus of Light", value="Orphion's Nexus of Light"),
    app_commands.Choice(name="The Canyon Colossus", value="The Canyon Colossus"),
    app_commands.Choice(name="The Nameless Anomaly", value="The Nameless Anomaly"),
    app_commands.Choice(name="Total", value="Total"),
]

ADDC_RAID_CHOICES = [
    app_commands.Choice(name="Nest of the Grootslang", value="Nest of the Grootslang"),
    app_commands.Choice(name="Orphion's Nexus of Light", value="Orphion's Nexus of Light"),
    app_commands.Choice(name="The Canyon Colossus", value="The Canyon Colossus"),
    app_commands.Choice(name="The Nameless Anomaly", value="The Nameless Anomaly")
]

class PlayerCountView(discord.ui.View):
    def __init__(self, player_counts, page=0, per_page=10, timeout=120):
        super().__init__(timeout=timeout)
        self.player_counts = player_counts
        self.page = page
        self.per_page = per_page
        self.max_page = (len(player_counts) - 1) // per_page
        self.previous.disabled = self.page == 0
        self.next.disabled = self.page == self.max_page

    async def update_message(self, interaction):
        embed = discord.Embed(title="Guild Raid Player Counts")
        start = self.page * self.per_page
        end = start + self.per_page
        for name, count in self.player_counts[start:end]:
            safe_name = discord.utils.escape_markdown(name)
            embed.add_field(name=safe_name, value=f"Count: {count}", inline=False)
        embed.set_footer(text=f"Page {self.page+1}/{self.max_page+1}")
        self.previous.disabled = self.page == 0
        self.next.disabled = self.page == self.max_page
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

    @app_commands.command(name="channel", description="Guild Raid通知チャンネルを設定")
    async def guildraid_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        if interaction.user.id not in AUTHORIZED_USER_IDS:
            await interaction.response.send_message("権限がありません。", ephemeral=True)
            return
        set_config("NOTIFY_CHANNEL_ID", str(channel.id))
        await interaction.response.send_message(f"Guild Raid通知チャンネルを {channel.mention} に設定しました。", ephemeral=True)
        logger.info(f"通知チャンネル設定: {channel.id}")

    @app_commands.command(name="list", description="指定レイドのギルドレイド履歴をリスト表示")
    @app_commands.describe(
        raid_name="表示するレイド名（Totalはすべてのレイド合計）",
    )
    @app_commands.choices(raid_name=RAID_CHOICES)
    async def guildraid_list(self, interaction: discord.Interaction, raid_name: str):
        if interaction.user.id not in AUTHORIZED_USER_IDS:
            await interaction.response.send_message("権限がありません。", ephemeral=True)
            return

        if raid_name == "Total":
            counts = get_all_guild_player_counts()
            title_text = "Guild Raid Player Counts: 合計"
        else:
            counts = get_all_guild_player_counts(raid=raid_name)
            title_text = f"Guild Raid Player Counts: {raid_name}"

        if not counts:
            await interaction.response.send_message("履歴がありません。", ephemeral=True)
            return

        sorted_counts = sorted(counts.items(), key=lambda x: (-x[1], x[0]))
        view = PlayerCountView(sorted_counts, page=0)
        embed = discord.Embed(title=title_text)
        for name, count in sorted_counts[:10]:
            safe_name = discord.utils.escape_markdown(name)
            embed.add_field(name=safe_name, value=f"Count: {count}", inline=False)
        embed.set_footer(text=f"Page 1/{view.max_page+1}")
        embed.description = (
            "※この履歴はギルドレイド（パーティ推定成功分）のみのカウントです。"
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        logger.info(f"履歴リスト出力: {raid_name} (embed形式ページ付き)")

    @app_commands.command(name="count", description="指定プレイヤーのギルドレイドクリア回数を補正")
    @app_commands.describe(
        player="プレイヤー名",
        raid_name="レイド名",
        count="カウント数"
    )
    @app_commands.choices(raid_name=ADDC_RAID_CHOICES)
    async def guildraid_count(self, interaction: discord.Interaction, player: str, raid_name: str, count: int):
        if interaction.user.id not in AUTHORIZED_USER_IDS:
            await interaction.response.send_message("権限がありません。", ephemeral=True)
            return
        set_guild_player_count(player, raid_name, count)
        await interaction.response.send_message(f"{player}の{raid_name}ギルドレイドクリア回数を{count}に補正しました。", ephemeral=True)
        logger.info(f"管理者補正: {player} {raid_name} {count}")

async def setup(bot: commands.Bot):
    await bot.add_cog(GuildRaidDetector(bot))
