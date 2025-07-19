import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime
import logging

from lib.database_handler import set_setting, get_raid_history_page

logger = logging.getLogger(__name__)

RAID_TYPES = [
    "Nest of the Grootslang",
    "Orphion's Nexus of Light",
    "The Canyon Colossus",
    "The Nameless Anomaly",
    "Total",
]

def is_specific_user(user_id: int):
    def predicate(interaction: discord.Interaction):
        if interaction.user.id != user_id:
            raise app_commands.CheckFailure(f"このコマンドは現在 <@{user_id}> のみが使用できます！")
        return True
    return app_commands.check(predicate)

class RaidHistoryView(discord.ui.View):
    def __init__(self, initial_page: int, total_pages: int, since_date: datetime | None, raid_type: str):
        super().__init__(timeout=180.0) # 3分でボタンを無効化
        self.current_page = initial_page
        self.total_pages = total_pages
        self.since_date = since_date
        self.raid_type = raid_type
        self.update_buttons()

    def create_embed(self):
        # ページデータ取得
        results, _ = get_raid_history_page(page=self.current_page, since_date=self.since_date)
        desc_lines = []
        total_count = 0
        for raid_name, timestamp, players in results:
            # フィルタ
            if self.raid_type != "Total" and raid_name != self.raid_type:
                continue
            dt_object = timestamp if hasattr(timestamp, "strftime") else datetime.fromisoformat(timestamp)
            formatted_ts = dt_object.strftime("%Y/%m/%d %H:%M")
            desc_lines.append(f"**{raid_name}** - `{formatted_ts}`\n> **Members:** {players}\n")
            total_count += 1

        embed = discord.Embed(title="Guild Raid Clear History", description="\n".join(desc_lines) or "該当レイドの記録はありません。")
        embed.set_footer(text=f"Page {self.current_page}/{self.total_pages} | Raid: {self.raid_type} | Total clears: {total_count}")
        return embed

    @discord.ui.button(label="次へ ▶️", style=discord.ButtonStyle.blurple)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page += 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.create_embed(), view=self)

    @discord.ui.button(label="◀️ 前へ", style=discord.ButtonStyle.blurple)
    async def prev_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page -= 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.create_embed(), view=self)

    def update_buttons(self):
        """ページの状況に応じてボタンの有効/無効を切り替える"""
        # 前へボタン
        self.children[0].disabled = self.current_page <= 1
        # 次へボタン
        self.children[1].disabled = self.current_page >= self.total_pages

class TrackerCog(commands.GroupCog, group_name="graid", description="ギルドレイド関連"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        logger.info(f"--- [Cog] {self.__class__.__name__} が読み込まれました。")

    @app_commands.command(name="channel", description="ギルドレイドの通知を送信するチャンネルを設定")
    @app_commands.describe(channel="通知を送信するチャンネル")
    @is_specific_user(1062535250099589120)
    async def set_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        set_setting("raid_notification_channel", str(channel.id))
        await interaction.response.send_message(
            f"✅ ギルドレイドの通知チャンネルを {channel.mention} に設定しました。",
            ephemeral=True
        )
        logger.info(f"ギルドレイドの通知チャンネルが更新されました: {channel.mention}")

    @app_commands.command(name="list", description="記録されたギルドレイドのクリア履歴を表示")
    @app_commands.describe(
        raid_type="表示するレイド種別を選択",
        since="日付 (YYYY-MM-DD形式) で絞り込み"
    )
    @app_commands.choices(
        raid_type=[
            app_commands.Choice(name=ra, value=ra) for ra in RAID_TYPES
        ]
    )
    @is_specific_user(1062535250099589120)
    async def list(self, interaction: discord.Interaction, raid_type: str, since: str = None):
        await interaction.response.defer(ephemeral=True)
        since_date = None
        if since:
            try:
                since_date = datetime.strptime(since, "%Y-%m-%d")
            except ValueError:
                await interaction.followup.send("日付の形式が正しくありません。`YYYY-MM-DD`形式で入力してください。")
                return

        # ページ数はフィルタ前で取得
        _, total_pages = get_raid_history_page(page=1, since_date=since_date)
        if total_pages == 0:
            message = "まだレイドのクリア記録がありません。"
            if since_date:
                message = f"{since_date.strftime('%Y-%m-%d')}以降のクリア記録はありません。"
            await interaction.followup.send(message)
            return

        view = RaidHistoryView(initial_page=1, total_pages=total_pages, since_date=since_date, raid_type=raid_type)
        embed = view.create_embed()
        await interaction.followup.send(embed=embed, view=view)

async def setup(bot: commands.Bot):
    await bot.add_cog(TrackerCog(bot))
