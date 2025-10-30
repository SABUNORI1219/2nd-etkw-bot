import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timedelta
import os
import re
import logging
import pytz

from lib.db import fetch_history, set_config, adjust_player_raid_count, get_member
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
    app_commands.Choice(name="Total", value="Total")
]

ADDC_RAID_CHOICES = [
    app_commands.Choice(name="Nest of the Grootslangs", value="Nest of the Grootslangs"),
    app_commands.Choice(name="Orphion's Nexus of Light", value="Orphion's Nexus of Light"),
    app_commands.Choice(name="The Canyon Colossus", value="The Canyon Colossus"),
    app_commands.Choice(name="The Nameless Anomaly", value="The Nameless Anomaly")
]

GUILDRAID_SUBMIT_CHANNEL_ID = 1397480193270222888

def normalize_date(date_str):
    """JST基準で日付文字列を正規化"""
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

def parse_date_with_time(date_str):
    """JST基準で日付・時刻文字列をパース"""
    if not date_str:
        return None
    
    # JST タイムゾーンを設定
    jst = pytz.timezone('Asia/Tokyo')
    
    try:
        # 時刻指定がある場合 (YYYY-MM-DD HH:MM or YYYY-MM-DD-HH:MM)
        if ' ' in date_str or date_str.count('-') > 2:
            # スペースまたは3番目以降のハイフンを時刻区切りとして扱う
            if ' ' in date_str:
                date_part, time_part = date_str.split(' ', 1)
            else:
                parts = date_str.split('-')
                if len(parts) >= 4:
                    date_part = '-'.join(parts[:3])
                    time_part = ':'.join(parts[3:])
                else:
                    date_part = date_str
                    time_part = "00:00"
            
            # 時刻部分の処理
            time_part = time_part.replace('-', ':')
            if ':' not in time_part:
                time_part = f"{time_part}:00"
            
            datetime_str = f"{normalize_date(date_part)} {time_part}"
            parsed_dt = datetime.strptime(datetime_str, "%Y-%m-%d %H:%M")
        else:
            # 日付のみの場合
            normalized_date = normalize_date(date_str)
            dash_count = normalized_date.count('-')
            
            if dash_count == 2:
                parsed_dt = datetime.strptime(normalized_date, "%Y-%m-%d")
            elif dash_count == 1:
                parsed_dt = datetime.strptime(normalized_date, "%Y-%m")
            elif dash_count == 0:
                parsed_dt = datetime.strptime(normalized_date, "%Y")
            else:
                return None
        
        # JSTタイムゾーンを設定してUTCに変換
        jst_dt = jst.localize(parsed_dt)
        utc_dt = jst_dt.astimezone(pytz.UTC).replace(tzinfo=None)
        return utc_dt
        
    except Exception as e:
        logger.warning(f"日付パースエラー: {date_str} - {e}")
        return None

class GraidCountView(discord.ui.View):
    def __init__(self, sorted_counts, period_counts, today_counts, yesterday_counts, total_period, total_today, total_yesterday, period_start, period_end, title, color, raid_display_name="Total", user_mcid=None, page=0, per_page=12, timeout=120):
        super().__init__(timeout=timeout)
        self.sorted_counts = sorted_counts
        self.period_counts = period_counts  # 期間全体
        self.today_counts = today_counts    # 今週分
        self.yesterday_counts = yesterday_counts  # 先週分
        self.total_period = total_period    # 期間合計
        self.total_today = total_today      # 今週合計
        self.total_yesterday = total_yesterday  # 先週合計
        self.period_start = period_start
        self.period_end = period_end
        self.raid_display_name = raid_display_name  # 表示用レイド名
        self.user_mcid = user_mcid  # コマンド実行者のMCID
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
            description=f"⚔️ Raid: {self.raid_display_name}\nPeriod: `{self.period_start}` ~ `{self.period_end}`"
        )
        idx = start
        while idx < end:
            for i in range(3):
                if idx + i < end:
                    name, count = self.sorted_counts[idx + i]
                    this_week_count = self.today_counts.get(name, 0)
                    last_week_count = self.yesterday_counts.get(name, 0)
                    
                    # 先週・今週両方0の場合はNone表示
                    if this_week_count == 0 and last_week_count == 0:
                        diff_str = "None"
                    else:
                        diff_val = this_week_count - last_week_count
                        diff_str = f"+{diff_val}" if diff_val > 0 else f"{diff_val}"
                    
                    rank_label = rank_emojis[idx + i] if (idx + i) < len(rank_emojis) else f"#{idx + i + 1}"
                    
                    # ユーザーのMCIDをハイライト（🌟マークと太字）
                    if self.user_mcid and name == self.user_mcid:
                        field_name = f"{rank_label} 🌟 **{name}**"
                        field_value = f"{raid_emoji} Raids: **{count}** (**{diff_str}**)"
                    else:
                        field_name = f"{rank_label} {name}"
                        field_value = f"{raid_emoji} Raids: {count} ({diff_str})"
                else:
                    field_name = field_value = "\u200b"
                embed.add_field(name=field_name, value=field_value, inline=True)
            idx += 3
        # 集計系
        # Average Per Player: 期間合計 / プレイヤー数
        avg_raids = int(self.total_period / len(self.period_counts)) if self.period_counts else 0
        # 📈 Compared to Last Week: 今週合計 - 先週合計
        total_diff = self.total_today - self.total_yesterday
        # 週の％計算: 先週が0なら0.0%、それ以外は (今週/先週)*100
        if self.total_yesterday == 0:
            total_pct = 0.0 if self.total_today == 0 else float('inf')
            total_pct_str = "0.0%" if self.total_today == 0 else "∞%"
        else:
            total_pct = (self.total_today / self.total_yesterday) * 100
            total_pct_str = f"{total_pct:.1f}%"
        
        embed.add_field(
            name="\u200b",
            value=(
                f"Total Raids: `{self.total_period}`\n"
                f"Average Per Player: `{avg_raids}`\n"
                f"📈 Compared to Last Week: `{total_diff}` (`{total_pct_str}`)"
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
            okane = count / 2
            embed.add_field(name=safe_name, value=f"Count: {count} | {okane} <- okane suuji!!!", inline=False)
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
        date="履歴を表示したい日時(YYYY-MM-DD HH:MM 形式、JST基準)",
        hidden="実行結果を自分だけに表示する（デフォルト: True）"
    )
    @app_commands.choices(raid_name=RAID_CHOICES)
    async def guildraid_list(self, interaction: discord.Interaction, raid_name: str, date: str = None, hidden: bool = True):
        # 権限チェック
        if interaction.user.id not in AUTHORIZED_USER_IDS:
            await send_authorized_only_message(interaction)
            return

        # コマンド実行者のMCIDを取得
        user_mcid = None
        user_data = get_member(discord_id=interaction.user.id)
        if user_data:
            user_mcid = user_data.get('mcid')
            logger.info(f"[GraidList] ユーザー {interaction.user.id} のMCID: {user_mcid}")
        else:
            logger.info(f"[GraidList] ユーザー {interaction.user.id} はlinked_membersに登録されていません")

        # 日付指定の処理（JST基準）
        date_from = parse_date_with_time(date) if date else None
        
        now = datetime.utcnow()
        today0 = datetime(now.year, now.month, now.day)

        # 週の計算: 月曜日を週の開始とする
        def get_week_start(dt):
            """指定された日付の週の月曜日を返す"""
            days_since_monday = dt.weekday()
            return dt - timedelta(days=days_since_monday)
        
        def get_week_end(dt):
            """指定された日付の週の日曜日を返す"""
            days_since_monday = dt.weekday()
            return dt + timedelta(days=6 - days_since_monday)

        # 今週と先週の範囲計算
        this_week_start = get_week_start(today0)
        this_week_end = get_week_end(today0)
        last_week_start = this_week_start - timedelta(days=7)
        last_week_end = this_week_start - timedelta(days=1)

        # レイド名による処理分岐
        if raid_name == "Test":
            # Testは廃止予定のため、Totalにリダイレクト
            raid_name = "Total"
        
        # データ取得とタイトル設定
        if raid_name == "Total":
            # 全レイドの合計
            raid_choices_to_fetch = RAID_CHOICES[:-1]  # Totalを除く
            title_text = "Guild Raid Counts: 合計"
            raid_display_name = "Total"
            color = discord.Color.orange()
        else:
            # 特定のレイド
            raid_choices_to_fetch = [choice for choice in RAID_CHOICES[:-1] if choice.value == raid_name]
            title_text = f"Guild Raid Counts: {raid_name}"
            raid_display_name = raid_name
            color = discord.Color.blue()

        # 期間指定データの取得
        if date_from:
            # 時間指定がある場合は時間まで表示
            if date and (' ' in date or date.count('-') > 2):
                period_start = date_from.strftime("%Y-%m-%d %H:%M")
            else:
                period_start = date_from.strftime("%Y-%m-%d")
            period_end = today0.strftime("%Y-%m-%d")
            rows = []
            for raid_choice in raid_choices_to_fetch:
                raid_rows = fetch_history(raid_name=raid_choice.value, date_from=date_from, date_to=today0 + timedelta(days=1))
                rows.extend(raid_rows)
        else:
            rows = []
            for raid_choice in raid_choices_to_fetch:
                raid_rows = fetch_history(raid_name=raid_choice.value)
                rows.extend(raid_rows)
            # 表示期間: 最初～最新
            if rows:
                period_start = min([r[2].strftime("%Y-%m-%d") for r in rows])
                period_end = max([r[2].strftime("%Y-%m-%d") for r in rows])
            else:
                period_start = period_end = today0.strftime("%Y-%m-%d")

        if not rows:
            embed = create_embed(description="履歴がありません。", title="🔴 エラーが発生しました", color=discord.Color.red(), footer_text=f"{self.system_name} | Minister Chikuwa")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # 指定期間のMCID集計
        period_counts = {}
        for row in rows:
            member = row[3]
            period_counts[str(member)] = period_counts.get(str(member), 0) + 1
        sorted_counts = sorted(period_counts.items(), key=lambda x: (-x[1], x[0]))

        # 今週分（月曜～現在まで）
        this_week_counts = {}
        for raid_choice in raid_choices_to_fetch:
            this_week_rows = fetch_history(raid_name=raid_choice.value, date_from=this_week_start, date_to=today0 + timedelta(days=1))
            for row in this_week_rows:
                member = row[3]
                this_week_counts[str(member)] = this_week_counts.get(str(member), 0) + 1

        # 先週分（先週月曜～先週日曜）
        last_week_counts = {}
        for raid_choice in raid_choices_to_fetch:
            last_week_rows = fetch_history(raid_name=raid_choice.value, date_from=last_week_start, date_to=last_week_end + timedelta(days=1))
            for row in last_week_rows:
                member = row[3]
                last_week_counts[str(member)] = last_week_counts.get(str(member), 0) + 1

        total_period = sum(period_counts.values())
        total_this_week = sum(this_week_counts.values())
        total_last_week = sum(last_week_counts.values())

        view = GraidCountView(
            sorted_counts=sorted_counts,
            period_counts=period_counts,
            today_counts=this_week_counts,
            yesterday_counts=last_week_counts,
            total_period=total_period,
            total_today=total_this_week,
            total_yesterday=total_last_week,
            period_start=period_start,
            period_end=period_end,
            title=title_text,
            color=color,
            raid_display_name=raid_display_name,
            user_mcid=user_mcid,
            page=0,
            per_page=12
        )
        embed = view.get_embed()
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
