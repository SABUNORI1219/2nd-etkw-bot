import discord
from discord import app_commands
from discord.ext import commands
import logging
from datetime import datetime, timezone
import re

from lib.wynncraft_api import WynncraftAPI
from lib.db import (
    add_member,
    remove_member,
    get_member,
    get_linked_members_page,
    set_config,
    get_all_linked_members,
    get_last_join_cache
)
from lib.discord_notify import notify_member_left_discord
from config import (
    GUILD_NAME,
    EMBED_COLOR_BLUE,
    AUTHORIZED_USER_IDS,
    send_authorized_only_message,
    RANK_ROLE_ID_MAP,
    ETKW,
    Ticket,
    PROMOTION_ROLE_MAP,
    ROLE_ID_TO_RANK
)

logger = logging.getLogger(__name__)

# ランクの選択肢 (オートコンプリート用)
RANK_ORDER = ["Owner", "Chief", "Strategist", "Captain", "Recruiter", "Recruit"]
RANK_CHOICES = [
    app_commands.Choice(name=rank, value=rank)
    for rank in RANK_ORDER
]

# ソート順の選択肢（rankは除外）
SORT_CHOICES = [
    app_commands.Choice(name="Last Seen (最終ログインが古い順)", value="last_seen")
]

def humanize_timedelta(dt: datetime) -> str:
    from math import floor
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    delta = now - dt
    seconds = int(delta.total_seconds())
    if seconds < 60:
        return f"{seconds} seconds ago"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} minutes ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours} hours ago"
    days = hours // 24
    if days < 30:
        return f"{days} days ago"
    months = floor(days / 30)
    if months < 12:
        return f"{months} months ago"
    years = floor(days / 365)
    return f"{years} years ago"

def sort_members_rank_order(members):
    rank_index = {rank: i for i, rank in enumerate(RANK_ORDER)}
    return sorted(members, key=lambda m: (rank_index.get(m["rank"], 999), m["mcid"].lower()))

def get_linked_members_page_ranked(page=1, rank_filter=None, per_page=10):
    all_members = get_all_linked_members(rank_filter=rank_filter)
    members_sorted = []
    for rank in RANK_ORDER:
        members_sorted.extend(
            [m for m in all_members if m["rank"] and m["rank"].strip().lower() == rank.lower()]
        )
    members_sorted.extend(
        [m for m in all_members if not m["rank"] or m["rank"].strip().lower() not in [r.lower() for r in RANK_ORDER]]
    )
    total_pages = (len(members_sorted) + per_page - 1) // per_page
    start = (page - 1) * per_page
    end = start + per_page
    return members_sorted[start:end], total_pages

async def get_last_seen_dict_db(limit=10):
    last_join_rows = get_last_join_cache(top_n=limit)
    mcids = [row[0] for row in last_join_rows]
    all_members = get_all_linked_members()
    member_dict = {m['mcid']: m for m in all_members}
    results = []
    for mcid, last_join in last_join_rows:
        m = member_dict.get(mcid)
        if not m:
            continue
        if last_join:
            try:
                last_join_dt = datetime.strptime(last_join, "%Y-%m-%dT%H:%M:%S.%fZ")
            except Exception:
                try:
                    last_join_dt = datetime.strptime(last_join, "%Y-%m-%dT%H:%M:%SZ")
                except Exception:
                    last_join_dt = None
        else:
            last_join_dt = None
        results.append((m, last_join_dt))
    return results

def extract_role_display_name(role_name: str) -> str:
    """
    ロール名から [★★] や [ABC] など [ ] で囲まれた部分を全て除去し、残りの文字列を返す。
    例: "[★★] 2nd Example [ABC]" -> "2nd Example"
    """
    s = re.sub(r"\s*\[.*?]\s*", " ", role_name)
    return s.strip()

class MemberListView(discord.ui.View):
    def __init__(self, cog_instance, initial_page: int, total_pages: int, rank_filter: str, sort_by: str, last_seen_members=None):
        super().__init__(timeout=180.0)
        self.cog = cog_instance
        self.api = WynncraftAPI()
        self.current_page = initial_page
        self.total_pages = total_pages
        self.rank_filter = rank_filter
        self.sort_by = sort_by
        self.last_seen_members = last_seen_members
        self.update_buttons()

    async def create_embed(self) -> discord.Embed:
        if self.sort_by == "last_seen":
            embed_title = "メンバーリスト: 最終ログイン順(上位10名)"
            lines = []
            for member, last_seen_dt in self.last_seen_members:
                mcid = discord.utils.escape_markdown(member['mcid'])
                if member.get('discord_id'):
                    discord_str = f"<@{member['discord_id']}>"
                else:
                    discord_str = "Discordなし"
                if last_seen_dt:
                    last_seen_str = humanize_timedelta(last_seen_dt)
                else:
                    last_seen_str = "N/A"
                lines.append(f"- **{mcid}** （{discord_str}） - Last Seen: {last_seen_str}")
            embed = discord.Embed(title=embed_title, color=EMBED_COLOR_BLUE)
            if not lines:
                embed.description = "表示するメンバーがいません。"
            else:
                embed.description = "\n".join(lines)
            embed.set_footer(text=f"最終ログイン | Minister Chikuwa")
            return embed

        if self.rank_filter in RANK_ORDER:
            members_on_page, self.total_pages = get_linked_members_page_ranked(page=self.current_page, rank_filter=self.rank_filter)
            embed_title = f"メンバーリスト: {self.rank_filter}"
        else:
            members_on_page, self.total_pages = get_linked_members_page_ranked(page=self.current_page)
            embed_title = "メンバーリスト"
        embed = discord.Embed(title=embed_title, color=EMBED_COLOR_BLUE)
        if not members_on_page:
            embed.description = "表示するメンバーがいません。"
            return embed
        lines = []
        for member in members_on_page:
            mcid = discord.utils.escape_markdown(member['mcid'])
            if member.get('discord_id'):
                lines.append(f"- **{mcid}** （<@{member['discord_id']}>）")
            else:
                lines.append(f"- **{mcid}** （Discordなし）")
        embed.description = "\n".join(lines)
        embed.set_footer(text=f"Page {self.current_page}/{self.total_pages} | Minister Chikuwa")
        return embed

    def update_buttons(self):
        if self.sort_by == "last_seen":
            self.children[0].disabled = True
            self.children[1].disabled = True
        else:
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
            await notify_member_left_discord(self.bot, linked_member)

    @app_commands.command(name="channel", description="メンバー通知用のチャンネルを設定")
    async def set_member_notify_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        if interaction.user.id not in AUTHORIZED_USER_IDS:
            await send_authorized_only_message(interaction)
            return
        set_config("MEMBER_NOTIFY_CHANNEL_ID", str(channel.id))
        await interaction.response.send_message(f"✅ メンバー通知チャンネルを {channel.mention} に設定しました。", ephemeral=True)

    @app_commands.command(name="add", description="メンバーを登録")
    @app_commands.describe(discord_user="登録したいDiscordユーザー（いない場合は入力不要、またはNone）")
    async def add(self, interaction: discord.Interaction, mcid: str, discord_user: discord.User = None):
        await interaction.response.defer()

        guild: discord.Guild | None = interaction.guild
        if guild is None:
            await interaction.followup.send("サーバー内でのみ使用できます。")
            return

        member: discord.Member = interaction.user

        # 権限判定-Ticket Chikuwa
        if Ticket:
            etkw_role = guild.get_role(Ticket)
            if etkw_role and etkw_role.id not in [r.id for r in member.roles]:
                await interaction.followup.send("このコマンドを使う権限がありません。")
                return

        guild_data = await self.api.get_guild_by_prefix("ETKW")
        if not guild_data:
            await interaction.followup.send("ギルドデータの取得に失敗しました。")
            return

        ingame_rank = None
        members_dict = guild_data.get('members', {})
        found = False
        for rank, rank_members in members_dict.items():
            if rank == "total":
                continue
            if mcid in rank_members:
                ingame_rank = rank.capitalize()
                found = True
                break
        if not found:
            await interaction.followup.send("❌ そのプレイヤーはギルドに所属していません。綴りを再確認してください。")
            return

        discord_id = discord_user.id if discord_user is not None else None

        success = add_member(mcid, discord_id, ingame_rank)
        if success:
            user_str = discord_user.display_name if discord_user else "Discordなし"
            await interaction.followup.send(f"✅ メンバー `{mcid}` を `{user_str}` としてランク `{ingame_rank}` で登録しました。")
        else:
            await interaction.followup.send("❌ メンバーの登録に失敗しました。")
            return

        if discord_user is not None:
            guild: discord.Guild = interaction.guild
            if guild is not None:
                try:
                    member: discord.Member = guild.get_member(discord_user.id)
                    if member is None:
                        member = await guild.fetch_member(discord_user.id)
                except Exception:
                    member = None

                if member is not None:
                    role_id = RANK_ROLE_ID_MAP.get(ingame_rank)
                    role_obj = None
                    if role_id:
                        role_obj = guild.get_role(role_id)
                    if ETKW:  # ETKWはint型のロールIDの場合
                        etkw_role = guild.get_role(ETKW)
                        if role_obj:
                            try:
                                await member.add_roles(role_obj, reason="ギルドランク連携")
                            except Exception as e:
                                logger.error(f"ロール付与エラー: {e}")
                        if etkw_role:
                            try:
                                await member.add_roles(etkw_role, reason="ちくわロール")
                            except Exception as e:
                                logger.error(f"ロール付与エラー: {e}")

                    # ロール名から[★★]や[ ]内の文字を除外
                    if role_obj:
                        role_name = extract_role_display_name(role_obj.name)
                    else:
                        role_name = ingame_rank
                    new_nick = f"{role_name} {mcid}"
                    try:
                        if not member.guild_permissions.administrator:
                            await member.edit(nick=new_nick, reason="ギルドメンバー登録時の自動ニックネーム設定")
                        else:
                            logger.warning(f"管理者権限ユーザー({member})のニックネームは編集できません")
                    except Exception as e:
                        logger.error(f"ニックネーム編集エラー: {e}")

    @app_commands.command(name="remove", description="メンバーの登録を解除")
    async def remove(self, interaction: discord.Interaction, mcid: str = None, discord_user: discord.User = None):
        await interaction.response.defer()

        guild: discord.Guild | None = interaction.guild
        if guild is None:
            await interaction.followup.send("サーバー内でのみ使用できます。")
            return

        member: discord.Member = interaction.user

        # 権限判定-Ticket Chikuwa
        if Ticket:
            etkw_role = guild.get_role(Ticket)
            if etkw_role and etkw_role.id not in [r.id for r in member.roles]:
                await interaction.followup.send("このコマンドを使う権限がありません。")
                return

        if not mcid and not discord_user:
            await interaction.followup.send("MCIDまたはDiscordユーザーのどちらかを指定してください。"); return

        # Discordメンバー取得
        target_member: discord.Member = None
        display_str = None
        if discord_user is not None:
            target_member = guild.get_member(discord_user.id)
            if target_member is None:
                try:
                    target_member = await guild.fetch_member(discord_user.id)
                except Exception:
                    target_member = None
            display_str = discord_user.display_name
        elif mcid is not None:
            # DBからdiscord_id取得
            db_data = get_member(mcid=mcid)
            if db_data and db_data.get("discord_id"):
                discord_id = db_data["discord_id"]
                target_member = guild.get_member(discord_id)
                if target_member is None:
                    try:
                        target_member = await guild.fetch_member(discord_id)
                    except Exception:
                        target_member = None
                display_str = db_data.get("mcid")
            else:
                display_str = mcid

        success = remove_member(mcid=mcid, discord_id=discord_user.id if discord_user else None)
        if success:
            target = mcid if mcid else discord_user.display_name
            await interaction.followup.send(f"✅ メンバー `{target}` の登録を解除しました。")
        else:
            await interaction.followup.send("❌ 登録解除に失敗したか、対象のメンバーが見つかりませんでした。")

        if target_member is not None:
            # ニックネームを元に戻す（None＝デフォルト名に戻す）
            try:
                if not target_member.guild_permissions.administrator:
                    await target_member.edit(nick=None, reason="removeコマンドによるニックネームリセット")
            except Exception as e:
                logger.error(f"remove ニックネームリセット失敗: {e}")

            # ROLE_ID_TO_RANK内のロールを全て削除
            roles_to_remove = [role for role in target_member.roles if role.id in ROLE_ID_TO_RANK]
            if roles_to_remove:
                try:
                    await target_member.remove_roles(*roles_to_remove, reason="removeコマンドによるランクロール削除")
                except Exception as e:
                    logger.error(f"remove ランクロール削除失敗: {e}")

    @app_commands.command(name="search", description="登録メンバーを検索")
    async def search(self, interaction: discord.Interaction, mcid: str = None, discord_user: discord.User = None):
        await interaction.response.defer()

        guild: discord.Guild | None = interaction.guild
        if guild is None:
            await interaction.followup.send("サーバー内でのみ使用できます。")
            return

        member: discord.Member = interaction.user

        # 権限判定-Ticket Chikuwa
        if Ticket:
            etkw_role = guild.get_role(Ticket)
            if etkw_role and etkw_role.id not in [r.id for r in member.roles]:
                await interaction.followup.send("このコマンドを使う権限がありません。")
                return

        if not mcid and not discord_user:
            await interaction.followup.send("MCIDまたはDiscordユーザーのどちらかを指定してください。"); return

        db_data = get_member(mcid=mcid, discord_id=discord_user.id if discord_user else None)
        if not db_data:
            await interaction.followup.send("指定されたメンバーは登録されていません。"); return

        player_data = await self.api.get_official_player_data(db_data['mcid'])
        last_seen = "N/A"
        if player_data and 'lastJoin' in player_data:
            last_seen = player_data['lastJoin'].split('T')[0]

        embed = discord.Embed(title=db_data['mcid'], color=EMBED_COLOR_BLUE)
        embed.add_field(name="Rank", value=f"`{db_data['rank']}`", inline=False)
        embed.add_field(name="Last Seen", value=f"`{last_seen}`", inline=False)
        if db_data['discord_id']:
            embed.add_field(name="Discord", value=f"<@{db_data['discord_id']}>", inline=False)
        else:
            embed.add_field(name="Discord", value="Discordなし", inline=False)

        await interaction.followup.send(embed=embed)

    @app_commands.command(name="list", description="登録メンバーの一覧を表示")
    @app_commands.describe(rank="ランクで絞り込み", sort="その他の絞り込み")
    @app_commands.choices(rank=RANK_CHOICES, sort=SORT_CHOICES)
    async def list(self, interaction: discord.Interaction, rank: str = None, sort: str = None):
        await interaction.response.defer(ephemeral=True)

        guild: discord.Guild | None = interaction.guild
        if guild is None:
            await interaction.followup.send("サーバー内でのみ使用できます。")
            return

        member: discord.Member = interaction.user

        # 権限判定-Ticket Chikuwa
        if Ticket:
            etkw_role = guild.get_role(Ticket)
            if etkw_role and etkw_role.id not in [r.id for r in member.roles]:
                await interaction.followup.send("このコマンドを使う権限がありません。")
                return

        if sort == "last_seen":
            last_seen_members = await get_last_seen_dict_db(limit=10)
            view = MemberListView(self, 1, 1, rank, sort, last_seen_members=last_seen_members)
            embed = await view.create_embed()
            await interaction.followup.send(embed=embed, view=view)
            return

        if rank in RANK_ORDER:
            _, total_pages = get_linked_members_page_ranked(page=1, rank_filter=rank)
        else:
            _, total_pages = get_linked_members_page_ranked(page=1, rank_filter=None)
        if total_pages == 0:
            await interaction.followup.send("表示対象のメンバーが登録されていません。"); return

        view = MemberListView(self, 1, total_pages, rank, sort)
        embed = await view.create_embed()
        await interaction.followup.send(embed=embed, view=view)

    @app_commands.command(name="promote", description="対象ユーザーのロールを昇格")
    @app_commands.describe(user="昇格対象ユーザー")
    @app_commands.checks.has_permissions(administrator=True)
    async def promote(self, interaction: discord.Interaction, user: discord.User):
        await interaction.response.defer(ephemeral=True)

        if not PROMOTION_ROLE_MAP:
            await interaction.followup.send("PROMOTION_ROLE_MAP が設定されていません。config.py を確認してください。")
            return

        guild: discord.Guild | None = interaction.guild
        if guild is None:
            await interaction.followup.send("サーバー内でのみ使用できます。")
            return

        target: discord.Member | None = guild.get_member(user.id)
        if target is None:
            try:
                target = await guild.fetch_member(user.id)
            except Exception:
                target = None
        if target is None:
            await interaction.followup.send("対象ユーザーを取得できませんでした。")
            return

        target_role_ids = {r.id for r in target.roles}

        old_role_id = None
        new_role_id = None
        for src_id, dst_id in PROMOTION_ROLE_MAP.items():
            if src_id in target_role_ids:
                old_role_id = src_id
                new_role_id = dst_id
                break

        if old_role_id is None:
            await interaction.followup.send("昇格可能な旧ロールを保持していません。")
            return

        old_role = guild.get_role(old_role_id)
        new_role = guild.get_role(new_role_id) if new_role_id else None
        if new_role is None:
            await interaction.followup.send("新ロールが見つかりません。PROMOTION_ROLE_MAP を確認してください。")
            return

        add_ok = True
        remove_ok = True
        try:
            await target.add_roles(new_role, reason="昇格: 新ロール付与")
        except Exception as e:
            add_ok = False
            logger.error(f"新ロール付与失敗: {e}")

        if add_ok and old_role:
            try:
                await target.remove_roles(old_role, reason="昇格: 旧ロール削除")
            except Exception as e:
                remove_ok = False
                logger.error(f"旧ロール削除失敗: {e}")

        # ニックネーム再構築（ゲーム内ランクは変わらない前提なのでDB rankは更新しない）
        prefix = extract_role_display_name(new_role.name)
        db_info = get_member(discord_id=target.id)
        if db_info and db_info.get("mcid"):
            mcid = db_info["mcid"]
            base_nick = f"{prefix} {mcid}"
        else:
            # MCID 未登録なら display_name 後半を活かすか単純付与
            base_nick = f"{prefix} {target.display_name}"
        if len(base_nick) > 32:
            base_nick = base_nick[:32]

        try:
            if not target.guild_permissions.administrator:
                await target.edit(nick=base_nick, reason="昇格による接頭辞更新")
        except Exception as e:
            logger.error(f"昇格ニックネーム変更失敗: {e}")

        msgs = [f"✅ 昇格処理: <@{target.id}> {old_role.mention if old_role else old_role_id} -> {new_role.mention}"]
        if not add_ok:
            msgs.append("⚠️ 新ロール付与に失敗しました。")
        if not remove_ok:
            msgs.append("⚠️ 旧ロール削除に失敗しました。")
        await interaction.followup.send("\n".join(msgs))

    @app_commands.command(name="rename", description="任意の名前でニックネームを変更")
    @app_commands.describe(name="新しい名前")
    async def rename(self, interaction: discord.Interaction, name: str):
        await interaction.response.defer(ephemeral=True)

        guild: discord.Guild | None = interaction.guild
        if guild is None:
            await interaction.followup.send("サーバー内でのみ使用できます。")
            return

        member: discord.Member = interaction.user

        # 権限判定（ETKW ロールを持っているかどうか。複数条件にしたい場合はリスト化）
        if ETKW:
            etkw_role = guild.get_role(ETKW)
            if etkw_role and etkw_role.id not in [r.id for r in member.roles]:
                await interaction.followup.send("このコマンドを使う権限がありません。")
                return

        # ランクロール特定
        current_rank = None
        current_rank_role_obj = None
        for role in member.roles:
            rank = ROLE_ID_TO_RANK.get(role.id)
            if rank:
                current_rank = rank
                current_rank_role_obj = role
                break
        
        if current_rank is None:
            await interaction.followup.send("ランクロールを検出できませんでした。")
            return

        if current_rank_role_obj:
            prefix = extract_role_display_name(current_rank_role_obj.name)
        else:
            # ランクロールなしの場合はそのまま
            prefix = "Member"

        new_nick = f"{prefix} {name}".strip()
        if len(new_nick) > 32:
            new_nick = new_nick[:32]

        try:
            if not member.guild_permissions.administrator:
                await member.edit(nick=new_nick, reason="renameコマンド")
            else:
                logger.warning("管理者権限ユーザーはニックネーム変更できない場合があります。")
        except Exception as e:
            logger.error(f"rename ニックネーム変更失敗: {e}")
            await interaction.followup.send("ニックネーム変更に失敗しました。Botのロール位置や権限を確認してください。")
            return

        await interaction.followup.send(f"✅ ニックネームを `{new_nick}` に変更しました。")

async def setup(bot: commands.Bot):
    await bot.add_cog(MemberCog(bot))
