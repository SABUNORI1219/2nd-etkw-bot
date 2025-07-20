import discord
from discord import app_commands
from discord.ext import commands
from lib.db import fetch_history, set_config
import os
import logging

logger = logging.getLogger(__name__)
AUTHORIZED_USER_IDS = [1062535250099589120]  # サンプルID

RAID_CHOICES = [
    app_commands.Choice(name="Nest of the Grootslang", value="Nest of the Grootslang"),
    app_commands.Choice(name="Orphion's Nexus of Light", value="Orphion's Nexus of Light"),
    app_commands.Choice(name="The Canyon Colossus", value="The Canyon Colossus"),
    app_commands.Choice(name="The Nameless Anomaly", value="The Nameless Anomaly"),
    app_commands.Choice(name="Total", value="Total"),
]

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
    @app_commands.command(name="channel", description="Guild Raid通知チャンネルを設定")
    async def guildraid_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        # 権限チェック
        if interaction.user.id not in AUTHORIZED_USER_IDS:
            await interaction.response.send_message("権限がありません。", ephemeral=True)
            return
        set_config("NOTIFY_CHANNEL_ID", str(channel.id))
        await interaction.response.send_message(f"Guild Raid通知チャンネルを {channel.mention} に設定しました。", ephemeral=True)
        logger.info(f"通知チャンネル設定: {channel.id}")

    # 履歴リスト出力コマンド
    @app_commands.command(name="list", description="指定レイド・日付の履歴をリスト表示")
    @app_commands.describe(
        raid_name="表示するレイド名を選択してください（Totalはすべてのレイド合計）",
        date="履歴を表示したい日付（例: 2025-07-20、2025-07 など。未指定なら全期間）"
    )
    @app_commands.choices(raid_name=RAID_CHOICES)
    async def guildraid_list(self, interaction: discord.Interaction, raid_name: str, date: str = None):
        """
        raid_name: 上記RAID_CHOICESから選択
        date: "2025-07-20"（日単位）, "2025-07"（月単位）, "2025"（年単位）など
        """
        if interaction.user.id not in AUTHORIZED_USER_IDS:
            await interaction.response.send_message("権限がありません。", ephemeral=True)
            return
        
        # 合計集計
        if raid_name == "Total":
            rows = []
            for raid_choice in RAID_CHOICES[:-1]:
                raid_rows = fetch_history(raid_name=raid_choice.value, date_from=date)
                rows.extend(raid_rows)
            title_text = "Guild Raid Player Counts: 合計"
        else:
            rows = fetch_history(raid_name=raid_name, date_from=date)
            title_text = f"Guild Raid Player Counts: {raid_name}"

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
        embed = discord.Embed(title=title_text)
        for name, count in sorted_counts[:10]:
            safe_name = discord.utils.escape_markdown(name)
            embed.add_field(name=safe_name, value=f"Count: {count}", inline=False)
        embed.set_footer(text=f"Page 1/{view.max_page+1}")

        # 日付記述方法の説明をEmbedのdescriptionに追加
        embed.description = (
            "【日付指定の記述方法例】\n"
            "・2025-07-20：2025年7月20日のみ\n"
            "・2025-07：2025年7月全体\n"
            "・2025：2025年全体\n"
            "（未指定なら全期間表示）"
        )

        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        logger.info(f"履歴リスト出力: {raid_name} {date} (embed形式ページ付き)")

    # 管理者補正コマンド
    @app_commands.command(name="count", description="指定プレイヤーのレイドクリア回数を補正")
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
