import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime
from lib.db import fetch_history, set_config, reset_player_raid_count
from lib.wynncraft_api import WynncraftAPI
from config import AUTHORIZED_USER_IDS, send_authorized_only_message, RESTRICTION
import os
import logging

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

# ページ付きEmbed用View
class PlayerCountView(discord.ui.View):
    def __init__(self, player_counts, page=0, per_page=10, timeout=120):
        super().__init__(timeout=timeout)
        self.player_counts = player_counts
        self.page = page
        self.per_page = per_page
        self.max_page = (len(player_counts) - 1) // per_page

        # 最初のボタン状態をページ数に応じて設定
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
        self.api = WynncraftAPI()
        self.etkw_member_cache = None

    async def _get_etkw_members(self):
        # Empire of TKWのメンバーを、get_guild_by_prefixで全ランクから収集
        PREFIX = "ETKW"  # ETKWギルドのprefix（必要に応じてconfig参照にしてもOK）
        data = await self.api.get_guild_by_prefix(PREFIX)
        members = set()
        if data and "members" in data:
            for rank_key, rank_obj in data["members"].items():
                # rank_obj: {"MCID": {...}, ...} のdictであることが多いが、もしintなどなら無視
                if isinstance(rank_obj, dict):
                    for mcid in rank_obj.keys():
                        members.add(mcid)
        self.etkw_member_cache = members
        return members

    def _has_required_role(self, member: discord.Member) -> bool:
        required_role = member.guild.get_role(GRAID_COUNT_ROLE_ID)
        if not required_role:
            return False
        return any(role >= required_role for role in member.roles)

    async def etkw_member_autocomplete(self, interaction: discord.Interaction, current: str):
        members = await self._get_etkw_members()
        # currentの部分一致（大文字小文字区別・最大25件）
        results = [name for name in members if current in name]
        return [app_commands.Choice(name=name, value=name) for name in sorted(results)[:25]]

    # 通知チャンネル設定コマンド
    @app_commands.command(name="channel", description="Guild Raid通知チャンネルを設定")
    async def guildraid_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        # 権限チェック
        if interaction.user.id not in AUTHORIZED_USER_IDS:
            await send_authorized_only_message(interaction)
            return
        set_config("NOTIFY_CHANNEL_ID", str(channel.id))
        await interaction.response.send_message(f"Guild Raid通知チャンネルを {channel.mention} に設定しました。", ephemeral=True)
        logger.info(f"通知チャンネル設定: {channel.id}")

    # 履歴リスト出力コマンド
    @app_commands.command(name="list", description="指定レイド・日付の履歴をリスト表示")
    @app_commands.describe(
        raid_name="表示するレイド名(Totalはすべてのレイド合計)",
        date="履歴を表示したい日付(YYYY-MM-DD表記)"
    )
    @app_commands.choices(raid_name=RAID_CHOICES)
    async def guildraid_list(self, interaction: discord.Interaction, raid_name: str, date: str = None):
        """
        raid_name: 上記RAID_CHOICESから選択
        date: "2025-07-20"（日単位）, "2025-07"（月単位）, "2025"（年単位）など
        """
        if interaction.user.id not in AUTHORIZED_USER_IDS:
            await send_authorized_only_message(interaction)
            return

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
            await interaction.response.send_message("履歴がありません。", ephemeral=True)
            return

        # guild_raid_historyは1人1行で保存なので、playerカウント集計
        player_counts = {}
        for row in rows:
            # rowの構造: (id, raid_name, clear_time, member)
            member = row[3]
            player_counts[str(member)] = player_counts.get(str(member), 0) + 1
        sorted_counts = sorted(player_counts.items(), key=lambda x: (-x[1], x[0]))

        # 最初のページを表示
        view = PlayerCountView(sorted_counts, page=0)
        embed = discord.Embed(title=title_text)
        for name, count in sorted_counts[:10]:
            safe_name = discord.utils.escape_markdown(name)
            embed.add_field(name=safe_name, value=f"Count: {count}", inline=False)
        embed.set_footer(text=f"Page 1/{view.max_page+1} | Minister Chikuwa")

        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        logger.info(f"履歴リスト出力: {raid_name} {date} (embed形式ページ付き)")

    # 管理者補正コマンド
    @app_commands.command(name="count", description="指定プレイヤーのレイドクリア回数を補正")
    @app_commands.describe(
        player="プレイヤー名",
        raid_name="レイド名",
        count="カウント数"
    )
    @app_commands.choices(raid_name=ADDC_RAID_CHOICES)
    @app_commands.autocomplete(player=etkw_member_autocomplete)
    async def guildraid_count(self, interaction: discord.Interaction, player: str, raid_name: str, count: int):
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("このコマンドはサーバー内でのみ利用可能です。", ephemeral=True)
            return
        if not self._has_required_role(interaction.user):
            await interaction.response.send_message("このコマンドを使用する権限がありません。", ephemeral=True)
            return

        etkw_members = await self._get_etkw_members()
        if player not in etkw_members:
            await interaction.response.send_message(f"指定プレイヤー「{player}」はETKWギルドメンバーではありません。", ephemeral=True)
            return
        
        reset_player_raid_count(player, raid_name, count)
        await interaction.response.send_message(f"{player}の{raid_name}クリア回数を{count}に補正しました", ephemeral=True)
        logger.info(f"管理者補正: {player} {raid_name} {count}")

# セットアップ関数
async def setup(bot: commands.Bot):
    await bot.add_cog(GuildRaidDetector(bot))
