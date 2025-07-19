import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime
import logging

from lib.database_handler import set_setting, get_raid_history_page

logger = logging.getLogger(__name__)

def is_specific_user(user_id: int):
    def predicate(interaction: discord.Interaction):
        if interaction.user.id != user_id:
            raise app_commands.CheckFailure(f"このコマンドは現在 <@{user_id}> のみが使用できます！")
        return True
    return app_commands.check(predicate)

class RaidHistoryView(discord.ui.View):
    def __init__(self, initial_page: int, total_pages: int):
        super().__init__(timeout=180.0) # 3分でボタンを無効化
        self.current_page = initial_page
        self.total_pages = total_pages
        self.update_buttons()

    def create_embed(self) -> discord.Embed:
        """現在のページに基づいてEmbedを作成する"""
        history, self.total_pages = get_raid_history_page(page=self.current_page)
        
        if not history:
            return discord.Embed(description=f"{self.current_page}ページ目には記録がありません。", color=discord.Color.greyple())

        embed = discord.Embed(title="Guild Raid Clear History", color=discord.Color.blue())
        
        desc_lines = []
        for raid_name, timestamp, players in history:
            dt_object = datetime.fromisoformat(timestamp)
            formatted_ts = dt_object.strftime("%Y/%m/%d %H:%M")
            desc_lines.append(f"**{raid_name}** - `{formatted_ts}`\n> **Members:** {players}\n")
        
        embed.description = "\n".join(desc_lines)
        embed.set_footer(text=f"Page {self.current_page}/{self.total_pages}")
        return embed

    def update_buttons(self):
        """ページの状況に応じてボタンの有効/無効を切り替える"""
        # 前へボタン
        self.children[0].disabled = self.current_page <= 1
        # 次へボタン
        self.children[1].disabled = self.current_page >= self.total_pages

    @discord.ui.button(label="◀️ 前へ", style=discord.ButtonStyle.blurple)
    async def previous_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page -= 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.create_embed(), view=self)

    @discord.ui.button(label="次へ ▶️", style=discord.ButtonStyle.blurple)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page += 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.create_embed(), view=self)

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
    @is_specific_user(1062535250099589120)
    async def list(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        history, total_pages = get_raid_history_page(page=1)

        if not history:
            await interaction.followup.send("まだレイドのクリア記録がありません。")
            return

        # 常に1ページ目からViewを開始
        view = RaidHistoryView(initial_page=1, total_pages=total_pages)
        embed = view.create_embed()
        
        await interaction.followup.send(embed=embed, view=view)

async def setup(bot: commands.Bot):
    await bot.add_cog(TrackerCog(bot))
