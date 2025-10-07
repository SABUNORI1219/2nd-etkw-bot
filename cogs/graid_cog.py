import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timedelta
import os
import re
import logging

from lib.db import fetch_history, set_config, adjust_player_raid_count
from lib.api_stocker import WynncraftAPI
from lib.utils import create_embed
from lib.discord_notify import RAID_EMOJIS, DEFAULT_EMOJI, get_emoji_for_raid
from config import AUTHORIZED_USER_IDS, send_authorized_only_message, RESTRICTION, ETKW

logger = logging.getLogger(__name__)

RAID_CHOICES = [
    app_commands.Choice(name="Nest of the Grootslangs", value="Nest of the Grootslangs"),
    app_commands.Choice(name="Orphion's Nexus of Light", value="Orphion's Nexus of Light"),
    app_commands.Choice(name="The Canyon Colossus", value="The Canyon Colossus"),
    app_commands.Choice(name="The Nameless Anomaly", value="The Nameless Anomaly"),
    app_commands.Choice(name="Total", value="Total"),
    app_commands.Choice(name="Test", value="Test"),
]

ADDC_RAID_CHOICES = [
    app_commands.Choice(name="Nest of the Grootslangs", value="Nest of the Grootslangs"),
    app_commands.Choice(name="Orphion's Nexus of Light", value="Orphion's Nexus of Light"),
    app_commands.Choice(name="The Canyon Colossus", value="The Canyon Colossus"),
    app_commands.Choice(name="The Nameless Anomaly", value="The Nameless Anomaly")
]

GUILDRAID_SUBMIT_CHANNEL_ID = 1397480193270222888

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

class TestPlayerCountView(discord.ui.View):
    def __init__(self, sorted_counts, period_counts, today_counts, yesterday_counts, total_period, total_today, total_yesterday, period_start, period_end, title, color, page=0, per_page=12, timeout=120):
        super().__init__(timeout=timeout)
        self.sorted_counts = sorted_counts
        self.period_counts = period_counts  # 期間全体
        self.today_counts = today_counts    # 今日分
        self.yesterday_counts = yesterday_counts  # 昨日分
        self.total_period = total_period    # 期間合計
        self.total_today = total_today      # 今日合計
        self.total_yesterday = total_yesterday  # 昨日合計
        self.period_start = period_start
        self.period_end = period_end
        self.page = page
        self.per_page = per_page
        self.max_page = (len(sorted_counts) - 1) // per_page if sorted_counts else 0
        self.title = title
        self.color = color
        self.message = None
        self.previous.disabled = self.page == 0
        self.next.disabled = self.page == self.max_page

    def get_embed(self):
        start = self.page * self.per_page
        end = min(start + self.per_page, len(self.sorted_counts))
        emoji = "🏆"
        raid_emoji = "🗡️"
        rank_emojis = ["🥇", "🥈", "🥉"]
        embed = discord.Embed(
            title=f"{emoji} Guild Raid Counts (Page `{self.page+1}/{self.max_page+1}` - `#{start+1} ~ #{end}`)",
            color=self.color,
            description=f"⚔️ Raid: Total\nPeriod: `{self.period_start}` ~ `{self.period_end}`"
        )
        idx = start
        while idx < end:
            for i in range(3):
                if idx + i < end:
                    name, count = self.sorted_counts[idx + i]
                    today_count = self.today_counts.get(name, 0)
                    yesterday_count = self.yesterday_counts.get(name, 0)
                    diff_val = today_count - yesterday_count
                    diff_str = f"+{diff_val}" if diff_val > 0 else f"{diff_val}"
                    rank_label = rank_emojis[idx + i] if (idx + i) < len(rank_emojis) else f"#{idx + i + 1}"
                    field_name = f"{rank_label} {name}"
                    field_value = f"{raid_emoji} Raids: {count} ({diff_str})"
                else:
                    field_name = field_value = "\u200b"
                embed.add_field(name=field_name, value=field_value, inline=True)
            idx += 3
        # 集計系
        # Average Per Player: 期間合計 / プレイヤー数
        avg_raids = int(self.total_period / len(self.period_counts)) if self.period_counts else 0
        # 📈 Compared to Last Day: 今日合計 - 昨日合計
        total_diff = self.total_today - self.total_yesterday
        total_pct = int((self.total_today / self.total_yesterday) * 100) if self.total_yesterday > 0 else 0
        embed.add_field(
            name="\u200b",
            value=(
                f"Total Raids: `{self.total_period}`\n"
                f"Average Per Player: `{avg_raids}`\n"
                f"📈 Compared to Last Day: `{total_diff}` (`{total_pct}%`)"
            ),
            inline=False
        )
        embed.set_footer(text="Guild Raidシステム | Minister Chikuwa")
        return embed

    async def update_message(self, interaction):
        embed = self.get_embed()
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

class GraidSubmitView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    def extract_raid_name(self, field_value):
        return re.sub(r"^(<a?:\w+:\d+>|\s*[\U0001F300-\U0001FAFF\u2600-\u27BF])+[\s]*", "", field_value)
    
    def unescape_mcid(self, m):
        return m.replace("\\_", "_").replace("\\*", "*").replace("\\~", "~")

    @discord.ui.button(label="承認/Approve", style=discord.ButtonStyle.success, custom_id="graid_approve")
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        # メッセージのEmbedからデータを取得
        embed = interaction.message.embeds[0]
        member_field = next((f for f in embed.fields if f.name == "メンバー"), None)
        raid_field = next((f for f in embed.fields if f.name == "レイド"), None)
        members = [m.strip() for m in member_field.value.split(",")] if member_field else []
        raid_name = raid_field.value if raid_field else ""
        submitter_id = int(embed.description.split("申請者: <@")[1].split(">")[0]) if embed.description else None

        real_members = [self.unescape_mcid(m.strip()) for m in member_field.value.split(",")] if member_field else []
        real_raid_name = self.extract_raid_name(raid_field.value) if raid_field else ""

        for mcid in real_members:
            adjust_player_raid_count(mcid, real_raid_name, 1)

        if submitter_id:
            user = await interaction.client.fetch_user(submitter_id)
            embed_dm = create_embed(
                description=None,
                title="✅️ あなたのギルドレイド申請が承認されました",
                color=discord.Color.green(),
                footer_text="Guild Raidシステム | Minister Chikuwa"
            )
            embed_dm.add_field(name="メンバー", value=", ".join(members), inline=False)
            embed_dm.add_field(name="レイド", value=raid_name, inline=False)
            try:
                await user.send(embed=embed_dm)
            except discord.Forbidden:
                embed = create_embed(description="申請者のDMがオフになっているため、DMを送信できませんでした。", title="🔴 エラーが発生しました", color=discord.Color.red(), footer_text=f"{self.system_name} | Minister Chikuwa")
                await interaction.followup.send(embed=embed, ephemeral=True)
        await interaction.message.delete()
        embed = create_embed(
            description="申請者にDMが送信されます。",
            title="✅️ 申請を承認しました",
            color=discord.Color.green(),
            footer_text="Guild Raidシステム | Minister Chikuwa"
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="拒否/Decline", style=discord.ButtonStyle.danger, custom_id="graid_reject")
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        # approve同様、メッセージから情報を取得してモーダルに渡す
        embed = interaction.message.embeds[0]
        member_field = next((f for f in embed.fields if f.name == "メンバー"), None)
        raid_field = next((f for f in embed.fields if f.name == "レイド"), None)
        members = [m.strip() for m in member_field.value.split(",")] if member_field else []
        raid_name = raid_field.value if raid_field else ""
        submitter_id = int(embed.description.split("申請者: <@")[1].split(">")[0]) if embed.description else None
        await interaction.response.send_modal(GraidRejectModal("Guild Raidシステム", submitter_id, members, raid_name, interaction.message))

class GraidRejectModal(discord.ui.Modal, title="拒否理由を入力"):
    reason = discord.ui.TextInput(label="理由", style=discord.TextStyle.paragraph, required=True)

    def __init__(self, system_name, submitter_id, member_ids, raid_name, message):
        super().__init__()
        self.system_name = system_name
        self.submitter_id = submitter_id
        self.member_ids = member_ids
        self.raid_name = raid_name
        self.message = message

    async def on_submit(self, interaction: discord.Interaction):
        user = await interaction.client.fetch_user(self.submitter_id)
        embed_dm = create_embed(
            description=None,
            title="❌️ あなたのギルドレイド申請が拒否されました",
            color=discord.Color.red(),
            footer_text=f"{self.system_name} | Minister Chikuwa"
        )
        embed_dm.add_field(
            name="メンバー",
            value=", ".join(self.member_ids),
            inline=False
        )
        embed_dm.add_field(name="レイド", value=self.raid_name, inline=False)
        embed_dm.add_field(name="理由", value=self.reason.value, inline=False)
        try:
            await user.send(embed=embed_dm)
        except discord.Forbidden:
            embed = create_embed(description="申請者のDMがオフになっているため、DMを送信できませんでした。", title="🔴 エラーが発生しました", color=discord.Color.red(), footer_text=f"{self.system_name} | Minister Chikuwa")
            await interaction.followup.send(embed=embed, ephemeral=True)

        await self.message.delete()
        embed = create_embed(
            description="拒否理由を送信し、申請Embedを削除しました。",
            title="✅️ 申請を拒否しました",
            color=discord.Color.green(),
            footer_text=f"{self.system_name} | Minister Chikuwa"
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

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
        # 日付指定の処理
        date_from = None
        period_start = None
        period_end = None
        if date:
            normalized_date = normalize_date(date).strip()
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

        if raid_name == "Test":
            if interaction.user.id not in AUTHORIZED_USER_IDS:
                await send_authorized_only_message(interaction)
                return

            now = datetime.utcnow()
            today0 = datetime(now.year, now.month, now.day)

            # 期間指定： date_from～今日
            if date_from:
                period_start = date_from.strftime("%Y-%m-%d")
                period_end = today0.strftime("%Y-%m-%d")
                rows = []
                for raid_choice in RAID_CHOICES[:-2]:
                    raid_rows = fetch_history(raid_name=raid_choice.value, date_from=date_from, date_to=today0 + timedelta(days=1))
                    rows.extend(raid_rows)
            else:
                rows = []
                for raid_choice in RAID_CHOICES[:-2]:
                    raid_rows = fetch_history(raid_name=raid_choice.value)
                    rows.extend(raid_rows)
                # 表示期間: 最初～最新
                if rows:
                    period_start = min([r[2].strftime("%Y-%m-%d") for r in rows])
                    period_end = max([r[2].strftime("%Y-%m-%d") for r in rows])
                else:
                    period_start = period_end = today0.strftime("%Y-%m-%d")

            # 指定期間のMCID集計
            period_counts = {}
            for row in rows:
                member = row[3]
                period_counts[str(member)] = period_counts.get(str(member), 0) + 1
            sorted_counts = sorted(period_counts.items(), key=lambda x: (-x[1], x[0]))

            # 今日分（今日のみ）
            today_counts = {}
            for raid_choice in RAID_CHOICES[:-2]:
                today_rows = fetch_history(raid_name=raid_choice.value, date_from=today0, date_to=today0 + timedelta(days=1))
                for row in today_rows:
                    member = row[3]
                    today_counts[str(member)] = today_counts.get(str(member), 0) + 1

            # 昨日分（昨日のみ）
            yesterday0 = today0 - timedelta(days=1)
            yesterday_counts = {}
            for raid_choice in RAID_CHOICES[:-2]:
                yesterday_rows = fetch_history(raid_name=raid_choice.value, date_from=yesterday0, date_to=today0)
                for row in yesterday_rows:
                    member = row[3]
                    yesterday_counts[str(member)] = yesterday_counts.get(str(member), 0) + 1

            total_period = sum(period_counts.values())
            total_today = sum(today_counts.values())
            total_yesterday = sum(yesterday_counts.values())

            view = TestPlayerCountView(
                sorted_counts=sorted_counts,
                period_counts=period_counts,
                today_counts=today_counts,
                yesterday_counts=yesterday_counts,
                total_period=total_period,
                total_today=total_today,
                total_yesterday=total_yesterday,
                period_start=period_start,
                period_end=period_end,
                title="Guild Raid Counts",
                color=discord.Color.orange(),
                page=0,
                per_page=12
            )
            embed = view.get_embed()
            await interaction.response.send_message(embed=embed, view=view, ephemeral=hidden)
            msg = await interaction.original_response()
            view.message = msg
            return
        
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
            
        before_count = len([row for row in fetch_history(raid_name=raid_name) if row[3] == player])
        adjust_player_raid_count(player, raid_name, count)
        after_count = len([row for row in fetch_history(raid_name=raid_name) if row[3] == player])
        
        embed = create_embed(
            description=None,
            title="✅️ クリア回数を補正しました",
            color=discord.Color.blue(),
            footer_text=f"{self.system_name} | Minister Chikuwa"
        )
        embed.add_field(name="プレイヤー", value=player, inline=False)
        embed.add_field(name="レイド名", value=raid_name, inline=False)
        embed.add_field(name="補正前", value=str(before_count), inline=True)
        embed.add_field(name="補正後", value=str(after_count), inline=True)
        
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="submit", description="レイドクリア申請")
    @app_commands.describe(members="メンバー4人のMCID(空白区切り)", raid_name="レイド名", proof="証拠画像")
    @app_commands.choices(raid_name=ADDC_RAID_CHOICES)
    async def guildraid_submit(self, interaction: discord.Interaction, members: str, raid_name: str, proof: discord.Attachment):
        await interaction.response.defer(ephemeral=True)

        # 権限チェック
        if interaction.user.id not in AUTHORIZED_USER_IDS:
            await send_authorized_only_message(interaction)
            return

        guild: discord.Guild | None = interaction.guild
        if guild is None:
            embed = create_embed(description="このコマンドはサーバー内でのみ利用可能です。", title="🔴 エラーが発生しました", color=discord.Color.red(), footer_text=f"{self.system_name} | Minister Chikuwa")
            await interaction.followup.send(embed=embed)
            return

        member: discord.Member = interaction.user

        # 権限判定（ETKW ロールを持っているかどうか）
        if ETKW:
            etkw_role = guild.get_role(ETKW)
            if etkw_role and etkw_role.id not in [r.id for r in member.roles]:
                embed = create_embed(description="このコマンドを使用する権限がありません。", title="🔴 エラーが発生しました", color=discord.Color.red(), footer_text=f"{self.system_name} | Minister Chikuwa")
                await interaction.followup.send(embed=embed)
                return

        if proof.size > 8 * 1024 * 1024:
            embed = create_embed(
                description="添付された画像が8MBを超えています。8MB以下の画像をアップロードしてください。",
                title="🔴 エラーが発生しました",
                color=discord.Color.red(),
                footer_text=f"{self.system_name} | Minister Chikuwa"
            )
            await interaction.followup.send(embed=embed)
            return
        
        member_ids = members.split()
        if len(member_ids) != 4:
            embed = create_embed(description="メンバーは4人分のIDを空白区切りで指定してください。", title="🔴 エラーが発生しました", color=discord.Color.red(), footer_text=f"{self.system_name} | Minister Chikuwa")
            await interaction.followup.send(embed=embed)
            return

        member_ids = members.split()
        if len(member_ids) != 4:
            embed = create_embed(
                description="メンバーは4人分のIDを空白区切りで指定してください。",
                title="🔴 エラーが発生しました",
                color=discord.Color.red(),
                footer_text=f"{self.system_name} | Minister Chikuwa"
            )
            await interaction.followup.send(embed=embed)
            return
        
        etkw_members = await self._get_etkw_members()
        
        not_in_guild = [mcid for mcid in member_ids if mcid not in etkw_members]
        if not_in_guild:
            embed = create_embed(
                description=f"指定されたMCIDがETKWギルドメンバーに含まれていません: {', '.join(not_in_guild)}",
                title="🔴 エラーが発生しました",
                color=discord.Color.red(),
                footer_text=f"{self.system_name} | Minister Chikuwa"
            )
            await interaction.followup.send(embed=embed)
            return
        
        if len(set(member_ids)) != 4:
            embed = create_embed(
                description="同じMCIDが重複しています。4人すべて異なるMCIDを入力してください。",
                title="🔴 エラーが発生しました",
                color=discord.Color.red(),
                footer_text=f"{self.system_name} | Minister Chikuwa"
            )
            await interaction.followup.send(embed=embed)
            return

        image_url = proof.url
        emoji = get_emoji_for_raid(raid_name)

        app_embed = discord.Embed(
            title="ギルドレイドクリア申請",
            description=f"申請者: <@{interaction.user.id}>",
            color=discord.Color.orange()
        )
        app_embed.add_field(
            name="メンバー",
            value=", ".join([discord.utils.escape_markdown(m) for m in member_ids]),
            inline=False
        )
        app_embed.add_field(name="レイド", value=f"{emoji}{raid_name}", inline=False)
        app_embed.set_image(url=image_url)
        app_embed.set_footer(text=f"{self.system_name} | Minister Chikuwa")
        view = GraidSubmitView()

        channel = interaction.client.get_channel(GUILDRAID_SUBMIT_CHANNEL_ID)
        if not channel:
            channel = await interaction.client.fetch_channel(GUILDRAID_SUBMIT_CHANNEL_ID)
        await channel.send(embed=app_embed, view=view)

        embed = create_embed(
            description="承認をお待ち下さい。\n通知はDMで行われます。",
            title="✅️ 申請を送信しました",
            color=discord.Color.green(),
            footer_text=f"{self.system_name} | Minister Chikuwa"
        )

        await interaction.followup.send(embed=embed)

# セットアップ関数
async def setup(bot: commands.Bot):
    await bot.add_cog(GuildRaidDetector(bot))
