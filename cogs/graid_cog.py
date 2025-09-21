import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime
import os
import logging

from lib.db import fetch_history, set_config, reset_player_raid_count
from lib.api_stocker import WynncraftAPI
from lib.utils import create_embed
from config import AUTHORIZED_USER_IDS, send_authorized_only_message, RESTRICTION

logger = logging.getLogger(__name__)

RAID_CHOICES = [
    app_commands.Choice(name="Nest of the Grootslangs", value="Nest of the Grootslangs"),
    app_commands.Choice(name="Orphion's Nexus of Light", value="Orphion's Nexus of Light"),
    app_commands.Choice(name="The Canyon Colossus", value="The Canyon Colossus"),
    app_commands.Choice(name="The Nameless Anomaly", value="The Nameless Anomaly"),
    app_commands.Choice(name="Total", value="Total"),
]

ADDC_RAID_CHOICES = [
    app_commands.Choice(name="Nest of the Grootslangs", value="Nest of the Grootslangs"),
    app_commands.Choice(name="Orphion's Nexus of Light", value="Orphion's Nexus of Light"),
    app_commands.Choice(name="The Canyon Colossus", value="The Canyon Colossus"),
    app_commands.Choice(name="The Nameless Anomaly", value="The Nameless Anomaly")
]

def normalize_date(date_str):
    parts = date_str.split('-')
    if len(parts) == 3:
        year, month, day = parts
        return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
    elif len(parts) == 2:
        year, month = parts
        return f"{year}-{month.zfill(2)}"
    elif len(parts) == 1:
        return parts[0]
    return date_str

class PlayerCountView(discord.ui.View):
    def __init__(self, player_counts, title, color=discord.Color.blue(), page=0, per_page=10, timeout=120):
        super().__init__(timeout=timeout)
        self.player_counts = player_counts
        self.page = page
        self.per_page = per_page
        self.max_page = (len(player_counts) - 1) // per_page
        self.title = title
        self.color = color
        self.message = None

        self.previous.disabled = self.page == 0
        self.next.disabled = self.page == self.max_page

    async def update_message(self, interaction):
        embed = discord.Embed(title=self.title, color=self.color)
        start = self.page * self.per_page
        end = start + self.per_page
        for name, count in self.player_counts[start:end]:
            safe_name = discord.utils.escape_markdown(name)
            embed.add_field(name=safe_name, value=f"Count: {count}", inline=False)
        embed.set_footer(text=f"Page {self.page+1}/{self.max_page+1} | Minister Chikuwa")
        self.previous.disabled = self.page == 0
        self.next.disabled = self.page == self.max_page
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="⏪️", style=discord.ButtonStyle.secondary)
    async def previous(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page > 0:
            self.page -= 1
            await self.update_message(interaction)

    @discord.ui.button(label="⏩️", style=discord.ButtonStyle.secondary)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page < self.max_page:
            self.page += 1
            await self.update_message(interaction)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self.message is None:
            self.message = interaction.message
        return True

    async def on_timeout(self):
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True

        if self.message:
            await self.message.edit(view=self)

class GuildRaidDetector(commands.GroupCog, name="graid"):
    def __init__(self, bot):
        self.bot = bot
        self.api = WynncraftAPI()
        self.etkw_member_cache = None
        self.system_name = "Guild Raidシステム"

    async def _get_etkw_members(self):
        PREFIX = "ETKW"
        data = await self.api.get_guild_by_prefix(PREFIX)
        members = set()
        if data and "members" in data:
            for rank_key, rank_obj in data["members"].items():
                if isinstance(rank_obj, dict):
                    for mcid in rank_obj.keys():
                        members.add(mcid)
        self.etkw_member_cache = members
        return members

    def _has_required_role(self, member: discord.Member) -> bool:
        required_role = member.guild.get_role(RESTRICTION)
        if not required_role:
            return False
        return any(role >= required_role for role in member.roles)

    async def etkw_member_autocomplete(self, interaction: discord.Interaction, current: str):
        members = await self._get_etkw_members()
        results = [name for name in members if current in name]
        return [app_commands.Choice(name=name, value=name) for name in sorted(results)[:25]]

    @app_commands.command(name="channel", description="Guild Raid通知チャンネルを設定")
    async def guildraid_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        # 権限チェック
        if interaction.user.id not in AUTHORIZED_USER_IDS:
            await send_authorized_only_message(interaction)
            return
        set_config("NOTIFY_CHANNEL_ID", str(channel.id))
        embed = create_embed(
            description=None,
            title="✅️ チャンネル設定が完了しました",
            color=discord.Color.green(),
            footer_text=f"{self.system_name} | Minister Chikuwa"
        )
        embed.add_field(name="新しいチャンネル", value=channel.mention, inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="list", description="指定レイド・日付の履歴をリスト表示")
    @app_commands.describe(
        raid_name="表示するレイド名(Totalはすべてのレイド合計)",
        date="履歴を表示したい日付(YYYY-MM-DD表記)",
        hidden="実行結果を自分だけに表示する（デフォルト: True）"
    )
    @app_commands.choices(raid_name=RAID_CHOICES)
    async def guildraid_list(self, interaction: discord.Interaction, raid_name: str, date: str = None, hidden: bool = True):
        date_from = None
        if date:
            normalized_date = normalize_date(date).strip()
            logger.info(f"normalized_date: '{normalized_date}'")
            try:
                dash_count = normalized_date.count('-')
                if dash_count == 2:
                    date_from = datetime.strptime(normalized_date, "%Y-%m-%d")
                elif dash_count == 1:
                    date_from = datetime.strptime(normalized_date, "%Y-%m")
                elif dash_count == 0:
                    date_from = datetime.strptime(normalized_date, "%Y")
            except Exception as e:
                date_from = None
                logger.info(f"日付パース失敗: '{normalized_date}', error: {e}")
        
        # 合計集計
        if raid_name == "Total":
            rows = []
            for raid_choice in RAID_CHOICES[:-1]:
                raid_rows = fetch_history(raid_name=raid_choice.value, date_from=date_from)
                rows.extend(raid_rows)
            title_text = "Guild Raid Player Counts: 合計"
        else:
            rows = fetch_history(raid_name=raid_name, date_from=date_from)
            title_text = f"Guild Raid Player Counts: {raid_name}"

        if not rows:
            embed = create_embed(description="履歴がありません。", title="🔴 エラーが発生しました", color=discord.Color.red(), footer_text=f"{self.system_name} | Minister Chikuwa")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        player_counts = {}
        for row in rows:
            member = row[3]
            player_counts[str(member)] = player_counts.get(str(member), 0) + 1
        sorted_counts = sorted(player_counts.items(), key=lambda x: (-x[1], x[0]))

        view = PlayerCountView(sorted_counts, title=title_text, color=discord.Color.blue(), page=0)
        embed = discord.Embed(title=title_text, color=discord.Color.blue())
        for name, count in sorted_counts[:10]:
            safe_name = discord.utils.escape_markdown(name)
            embed.add_field(name=safe_name, value=f"Count: {count}", inline=False)
        embed.set_footer(text=f"Page 1/{view.max_page+1} | Minister Chikuwa")

        await interaction.response.send_message(embed=embed, view=view, ephemeral=hidden)
        msg = await interaction.original_response()
        view.message = msg

    @app_commands.command(name="count", description="指定プレイヤーのレイドクリア回数を補正")
    @app_commands.describe(
        player="プレイヤー名",
        raid_name="レイド名",
        count="カウント数"
    )
    @app_commands.choices(raid_name=ADDC_RAID_CHOICES)
    @app_commands.autocomplete(player=etkw_member_autocomplete)
    async def guildraid_count(self, interaction: discord.Interaction, player: str, raid_name: str, count: int):
        await interaction.response.defer(ephemeral=True)
        
        if not isinstance(interaction.user, discord.Member):
            embed = create_embed(description="このコマンドはサーバー内でのみ利用可能です。", title="🔴 エラーが発生しました", color=discord.Color.red(), footer_text=f"{self.system_name} | Minister Chikuwa")
            await interaction.followup.send(embed=embed)
            return
        if not self._has_required_role(interaction.user):
            embed = create_embed(description="このコマンドを使用する権限がありません。", title="🔴 エラーが発生しました", color=discord.Color.red(), footer_text=f"{self.system_name} | Minister Chikuwa")
            await interaction.followup.send(embed=embed)
            return

        etkw_members = await self._get_etkw_members()
        if player not in etkw_members:
            embed = create_embed(description=f"指定プレイヤー **{player}** はETKWギルドメンバーではありません。", title="🔴 エラーが発生しました", color=discord.Color.red(), footer_text=f"{self.system_name} | Minister Chikuwa")
            await interaction.followup.send(embed=embed)
            return
        
        reset_player_raid_count(player, raid_name, count)
        
        embed = create_embed(
            description=None,
            title="✅️ クリア回数を補正しました",
            color=discord.Color.blue(),
            footer_text=f"{self.system_name} | Minister Chikuwa"
        )
        embed.add_field(name="プレイヤー", value=player, inline=False)
        embed.add_field(name="レイド名", value=raid_name, inline=False)
        embed.add_field(name="補正カウント数", value=str(count), inline=False)
        
        await interaction.followup.send(embed=embed)

# セットアップ関数
async def setup(bot: commands.Bot):
    await bot.add_cog(GuildRaidDetector(bot))
