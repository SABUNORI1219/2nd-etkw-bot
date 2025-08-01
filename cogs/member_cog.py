import discord
from discord import app_commands
from discord.ext import commands
import logging
from datetime import datetime, timezone

from lib.wynncraft_api import WynncraftAPI
from lib.db import add_member, remove_member, get_member, get_linked_members_page, set_config
from lib.discord_notify import notify_member_left_discord
from config import GUILD_NAME, EMBED_COLOR_BLUE, AUTHORIZED_USER_IDS, send_authorized_only_message

logger = logging.getLogger(__name__)

# ランクの選択肢 (オートコンプリート用)
RANK_ORDER = ["Owner", "Chief", "Strategist", "Captain", "Recruiter", "Recruit"]
RANK_CHOICES = [
    app_commands.Choice(name=rank, value=rank)
    for rank in RANK_ORDER
]

# ソート順の選択肢
SORT_CHOICES = [
    app_commands.Choice(name="Last Seen (最終ログインが古い順)", value="last_seen")
]

# /member list のためのページ送りView
class MemberListView(discord.ui.View):
    def __init__(self, cog_instance, initial_page: int, total_pages: int, rank_filter: str, sort_by: str):
        super().__init__(timeout=180.0)
        self.cog = cog_instance
        self.api = WynncraftAPI()
        self.current_page = initial_page
        self.total_pages = total_pages
        self.rank_filter = rank_filter
        self.sort_by = sort_by
        self.update_buttons()

    async def create_embed(self) -> discord.Embed:
        """現在のページに基づいてEmbedを作成する（新ビジュアル仕様・ランク順制御）"""
        members_on_page, self.total_pages = get_linked_members_page(page=self.current_page, rank_filter=self.rank_filter)
        
        embed = discord.Embed(title="メンバーリスト", color=EMBED_COLOR_BLUE)

        if not members_on_page:
            embed.description = "表示するメンバーがいません。"
            return embed

        # "Last Seen"ソートの場合、このページのメンバーのAPIデータを取得
        if self.sort_by == "last_seen":
            member_details = []
            for member in members_on_page:
                player_data = await self.cog.api.get_nori_player_data(member['username'])
                last_join = player_data.get('lastJoin', "1970-01-01T00:00:00.000Z") if player_data else "1970-01-01T00:00:00.000Z"
                member_details.append({**member, 'last_seen': datetime.fromisoformat(last_join.replace("Z", "+00:00"))})
            # 最終ログイン日時でソート (古い順)
            members_on_page = sorted(member_details, key=lambda x: x['last_seen'])

        # ランクごとにまとめる
        rank_to_members = {}
        for member in members_on_page:
            rank = member['rank']
            if rank not in rank_to_members:
                rank_to_members[rank] = []
            last_seen_str = member['last_seen'].strftime('%Y-%m-%d') if 'last_seen' in member else "N/A"
            # 2行表示
            member_str = f"**Account**: {member['mcid']} (<@{member['discord_id']}>)\n**Last Seen**: {last_seen_str}"
            rank_to_members[rank].append(member_str)

        # 指定した順でフィールドを追加
        for rank in RANK_ORDER:
            if rank in rank_to_members:
                embed.add_field(name=rank, value="\n\n".join(rank_to_members[rank]), inline=False)

        # RANK_ORDERにないランクがDBに入ってた場合も出す
        for rank in rank_to_members:
            if rank not in RANK_ORDER:
                embed.add_field(name=rank, value="\n\n".join(rank_to_members[rank]), inline=False)

        embed.set_footer(text=f"Page {self.current_page}/{self.total_pages} | Minister Chikuwa")
        return embed

    def update_buttons(self):
        self.children[0].disabled = self.current_page <= 1
        self.children[1].disabled = self.current_page >= self.total_pages

    @discord.ui.button(label="⏪️", style=discord.ButtonStyle.blurple)
    async def previous_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page -= 1
        embed = await self.create_embed()
        self.update_buttons()
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="⏩️", style=discord.ButtonStyle.blurple)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page += 1
        embed = await self.create_embed()
        self.update_buttons()
        await interaction.response.edit_message(embed=embed, view=self)


class MemberCog(commands.GroupCog, group_name="member", description="ギルドメンバーとDiscordアカウントの連携を管理します。"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.api = WynncraftAPI()
        logger.info(f"--- [Cog] {self.__class__.__name__} が読み込まれました。")

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        linked_member = get_member(discord_id=member.id)
        if linked_member:
            remove_member(discord_id=member.id)
            logger.info(f"--- [MemberSync] {member.display_name} がサーバーから退出したため、連携を解除しました。")
            # Discord退出通知
            await notify_member_left_discord(self.bot, linked_member)

    @app_commands.command(name="channel", description="メンバー通知用のチャンネルを設定")
    async def set_member_notify_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        # 権限チェック
        if interaction.user.id not in AUTHORIZED_USER_IDS:
            await send_authorized_only_message(interaction)
            return
        set_config("MEMBER_NOTIFY_CHANNEL_ID", str(channel.id))
        await interaction.response.send_message(f"✅ メンバー通知チャンネルを {channel.mention} に設定しました。", ephemeral=True)

    @app_commands.command(name="add", description="メンバーを登録")
    @app_commands.checks.has_permissions(administrator=True)
    async def add(self, interaction: discord.Interaction, mcid: str, discord_user: discord.User):
        await interaction.response.defer(ephemeral=True)

        # 権限チェック
        if interaction.user.id not in AUTHORIZED_USER_IDS:
            await send_authorized_only_message(interaction)
            return
        
        # まず公式APIから最新のランク情報を取得
        guild_data = await self.api.get_guild_by_prefix("ETKW")
        if not guild_data:
            await interaction.followup.send("ギルドデータの取得に失敗しました。"); return
        
        ingame_rank = "Unknown"
        members_dict = guild_data.get('members', {})
        for rank, rank_members in members_dict.items():
            if rank == "total":
                continue
            if mcid in rank_members:
                ingame_rank = rank.capitalize()
                break
        
        success = add_member(mcid, discord_user.id, ingame_rank)
        if success:
            await interaction.followup.send(f"✅ メンバー `{mcid}` を `{discord_user.display_name}` としてランク `{ingame_rank}` で登録しました。")
        else:
            await interaction.followup.send("❌ メンバーの登録に失敗しました。")

    @app_commands.command(name="remove", description="メンバーの登録を解除")
    @app_commands.checks.has_permissions(administrator=True)
    async def remove(self, interaction: discord.Interaction, mcid: str = None, discord_user: discord.User = None):
        await interaction.response.defer(ephemeral=True)

        # 権限チェック
        if interaction.user.id not in AUTHORIZED_USER_IDS:
            await send_authorized_only_message(interaction)
            return
            
        if not mcid and not discord_user:
            await interaction.followup.send("MCIDまたはDiscordユーザーのどちらかを指定してください。"); return
        
        success = remove_member(mcid=mcid, discord_id=discord_user.id if discord_user else None)
        if success:
            target = mcid if mcid else discord_user.display_name
            await interaction.followup.send(f"✅ メンバー `{target}` の登録を解除しました。")
        else:
            await interaction.followup.send("❌ 登録解除に失敗したか、対象のメンバーが見つかりませんでした。")
    
    @app_commands.command(name="search", description="登録メンバーを検索")
    async def search(self, interaction: discord.Interaction, mcid: str = None, discord_user: discord.User = None):
        await interaction.response.defer(ephemeral=True)

        # 権限チェック
        if interaction.user.id not in AUTHORIZED_USER_IDS:
            await send_authorized_only_message(interaction)
            return
        
        if not mcid and not discord_user:
            await interaction.followup.send("MCIDまたはDiscordユーザーのどちらかを指定してください。"); return
            
        db_data = get_member(mcid=mcid, discord_id=discord_user.id if discord_user else None)
        if not db_data:
            await interaction.followup.send("指定されたメンバーは登録されていません。"); return
            
        # Nori APIから最新のLast Seenを取得
        player_data = await self.api.get_nori_player_data(db_data['mcid'])
        last_seen = "N/A"
        if player_data and 'lastJoin' in player_data:
            last_seen = player_data['lastJoin'].split('T')[0]
            
        embed = discord.Embed(title=db_data['mcid'], color=EMBED_COLOR_BLUE)
        embed.add_field(name="Rank", value=f"`{db_data['rank']}`", inline=False)
        embed.add_field(name="Last Seen", value=f"`{last_seen}`", inline=False)
        embed.add_field(name="Discord", value=f"<@{db_data['discord_id']}>", inline=False)
        
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="list", description="登録メンバーの一覧を表示")
    @app_commands.describe(rank="ランクで絞り込み", sort="その他の絞り込み")
    @app_commands.choices(rank=RANK_CHOICES, sort=SORT_CHOICES)
    async def list(self, interaction: discord.Interaction, rank: str = None, sort: str = None):
        await interaction.response.defer(ephemeral=True)

        # 権限チェック
        if interaction.user.id not in AUTHORIZED_USER_IDS:
            await send_authorized_only_message(interaction)
            return

        _, total_pages = get_linked_members_page(page=1, rank_filter=rank)
        if total_pages == 0:
            await interaction.followup.send("表示対象のメンバーが登録されていません。"); return

        view = MemberListView(self, 1, total_pages, rank, sort)
        embed = await view.create_embed()
        await interaction.followup.send(embed=embed, view=view)

async def setup(bot: commands.Bot):
    await bot.add_cog(MemberCog(bot))
