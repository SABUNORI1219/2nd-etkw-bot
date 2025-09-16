import discord
from discord.ext import commands
from discord.ui import View, Modal, TextInput, button
import time
from typing import Optional
import logging

from lib.db import save_application
from lib.profile_renderer import generate_profile_card
from cogs.player_cog import build_profile_info
from lib.api_stocker import WynncraftAPI, OtherAPI
from lib.banner_renderer import BannerRenderer
from PIL import Image
from io import BytesIO

logger = logging.getLogger(__name__)

# ID
APPLICATION_CATEGORY_ID = 1415492214087483484
APPLICATION_CHANNEL_ID = 1415107620108501082
TICKET_STAFF_ROLE_ID = 1404665259112792095  # チケットのスタッフロールID
STAFF_ROLE_ID = 1158540148783448134         # 申請フォーム用スタッフロールID

# Guild Search Helper Function dayo!
async def search_guild(api, guild_input):
    patterns = [
        guild_input,
        guild_input.capitalize(),
        guild_input.upper(),
        guild_input.lower()
    ]
    # 全パターンでprefix検索（4回）
    for pattern in patterns:
        guild = await api.get_guild_by_prefix(pattern)
        if guild and guild.get('name'):
            return guild
    # 全パターンでname検索（4回）
    for pattern in patterns:
        guild = await api.get_guild_by_name(pattern)
        if guild and guild.get('name'):
            return guild
    return None

# Embed
def make_reason_embed(reason):
    return discord.Embed(
        title="加入理由/Reason",
        description=reason,
        color=discord.Color.purple()
    )

class DeclineConfirmView(View):
    def __init__(self, discord_id, channel_id):
        super().__init__(timeout=60)
        self.discord_id = discord_id
        self.channel_id = channel_id

    @button(label="拒否を確定/Confirm Decline", style=discord.ButtonStyle.danger, custom_id="decline_confirm")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        # DBから削除
        delete_application_by_discord_id(self.discord_id)
        # チャンネル削除
        try:
            await interaction.channel.delete(reason="申請を拒否(Decline)ボタンで削除")
        except Exception as e:
            await interaction.response.send_message("チャンネル削除に失敗しました。", ephemeral=True)
            logger.error(f"申請チャンネル削除失敗(Decline): {e}")
            return
        # チャンネルが消えるので以降の処理は不要

    @button(label="キャンセル/Cancel", style=discord.ButtonStyle.secondary, custom_id="decline_cancel")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("申請拒否をキャンセルしました。", ephemeral=True)
        await interaction.message.delete(delay=2)

class DeclineButtonView(View):
    def __init__(self, discord_id=None, channel_id=None):
        super().__init__(timeout=None)
        self.discord_id = discord_id
        self.channel_id = channel_id

    @button(label="拒否/Decline", style=discord.ButtonStyle.danger, custom_id="decline")
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        # 確認ダイアログ（ボタン）を送信
        view = DeclineConfirmView(self.discord_id, self.channel_id)
        await interaction.response.send_message(
            "本当にこの申請を拒否（削除）してもよろしいですか？\nAre you sure you want to decline and delete this application?",
            view=view,
            ephemeral=True,
        )

def make_prev_guild_embed(guild_info, input_name):
    banner_renderer = BannerRenderer()
    banner_bytes = None
    banner_file = None

    if isinstance(guild_info, dict) and guild_info.get("name"):
        name = guild_info.get('name', 'N/A')
        prefix = guild_info.get('prefix', 'N/A')
        owner_list = guild_info.get('members', {}).get('owner', {})
        owner = list(owner_list.keys())[0] if owner_list else "N/A"
        created_date = guild_info.get('created', 'N/A').split("T")[0] if guild_info.get('created') else "N/A"
        level = guild_info.get('level', 0)
        xp_percent = guild_info.get('xpPercent', 0)
        wars = guild_info.get('wars', 0)
        territories = guild_info.get('territories', 0)
        season_ranks = guild_info.get('seasonRanks', {})
        latest_season = str(max([int(k) for k in season_ranks.keys()])) if season_ranks else "N/A"
        rating = season_ranks.get(latest_season, {}).get('rating', "N/A") if season_ranks else "N/A"
        rating_display = f"{rating:,}" if isinstance(rating, int) else rating
        total_members = guild_info.get('members', {}).get('total', 0)
        online_members = guild_info.get('online', 0)

        # bannerがある場合のみ画像生成
        banner_info = guild_info.get('banner')
        if banner_info:
            banner_bytes = banner_renderer.create_banner_image(banner_info)
            if banner_bytes:
                banner_file = discord.File(fp=banner_bytes, filename="guild_banner.png")

        desc = (
            f"```python\n"
            f"Guild: {name} [{prefix}]\n"
            f"Owner: {owner}\n"
            f"Created: {created_date}\n"
            f"Level: {level} [{xp_percent}%]\n"
            f"Wars: {wars}\n"
            f"Latest SR: {rating_display} [Season {latest_season}]\n"
            f"Territories: {territories}\n"
            f"Members online/total: {online_members}/{total_members}\n"
            f"```\n"
        )
    elif input_name:
        desc = f"ギルド「{input_name}」の情報が見つかりませんでした。"
    else:
        desc = "過去ギルド情報は未入力です。"
    # 6000文字制限対策
    if len(desc) > 6000:
        desc = desc[:5900] + "\n...（一部省略されました）"

    embed = discord.Embed(
        title="過去ギルド/Previous Guild",
        description=desc,
        color=discord.Color.orange()
    )
    embed.set_footer(text=f"入力情報/Input: {input_name}")

    # バナーが生成できた場合のみサムネ設定
    if banner_file:
        embed.set_thumbnail(url="attachment://guild_banner.png")

    return embed, banner_file

async def make_profile_embed(mcid: str) -> tuple[discord.Embed, Optional[discord.File], Optional[str]]:
    """
    プロファイル画像生成＋画像付きEmbed（画像生成失敗時はテキストEmbed）
    """
    try:
        api = WynncraftAPI()
        other_api = OtherAPI()
        banner_renderer = BannerRenderer()
        player_data = await api.get_official_player_data(mcid)
        if not player_data:
            raise Exception("APIからプレイヤーデータ取得失敗")
        profile_info = await build_profile_info(player_data, api, banner_renderer)
        username = profile_info.get("username") or mcid
        uuid = profile_info.get("uuid")
        skin_image = None
        if uuid:
            try:
                skin_bytes = await other_api.get_vzge_skin(uuid)
                if skin_bytes:
                    skin_image = Image.open(BytesIO(skin_bytes)).convert("RGBA")
            except Exception:
                skin_image = None
        output_path = f"profile_card_{uuid}.png" if uuid else "profile_card.png"
        generate_profile_card(profile_info, output_path, skin_image=skin_image)
        embed = discord.Embed(
            title="プレイヤー情報/Player Info",
            color=discord.Color.blue()
        )
        embed.set_image(url=f"attachment://{output_path}")
        embed.set_footer(text=f"入力情報/Input: {mcid}")
        return embed, discord.File(output_path), username
    except Exception as e:
        embed = discord.Embed(
            title="プレイヤープロフィール取得失敗",
            description=f"MCID: {mcid}\n情報取得中にエラーが発生しました。",
            color=discord.Color.red()
        )
        logger.error(f"ぷろふぁいるいめーじせいせいにしっっぱいしたました: {e}")
        return embed, None, None

def make_user_guide_embed(lang: str = "ja") -> discord.Embed:
    if lang == "ja":
        desc = (
            "こんにちは！\n"
            "スタッフがチケットを確認し、ゲーム内で招待するまでお待ちください。\n"
            "時間帯によっては、確認および招待までに時間がかかる場合があります。\n"
            "また何か質問があれば、下記ボタンから送信できます。担当スタッフが対応します。\n"
            "\n"
            "(以下ロール付与後に確認してください)\n"
            "**ギルドカテゴリ内チャンネル紹介:**\n"
            "> <#1310992907527786538> \n"
            "ギルド内でのアナウンスが行われます。\n\n"
            "> <#1333036649075970058> \n"
            "ギルドに関する情報が掲載されています。\n\n"
            "> <#1134309996339925113> \n"
            "ギルド内専用のチャットです。お気軽に質問等どうぞ。\n\n"
            "> <#1285559379890012282> \n"
            "自己紹介用のチャンネルです。任意です。\n\n"
            "> <#1343603819610898545> \n"
            "ギルド内でのゲームに関する情報が共有されています。ぜひご一読ください。\n\n"
        )
        embed = discord.Embed(
            title="ご案内",
            description=desc,
            color=discord.Color.green()
        )
    else:
        desc = (
            "Hello!\n"
            "Please wait while staff review your ticket and invite you in-game.\n"
            "Depending on the time of day, confirmation/invite may take some time.\n"
            "If you have any questions, use the button below. A staff member will assist you.\n"
            "\n"
            "(Please check the contents below after you got member role.)\n"
            "**Guild Channels:**\n"
            "> <#1310992907527786538> \n"
            "Announcements for the guild.\n\n"
            "> <#1333036649075970058> \n"
            "Information about the guild.\n\n"
            "> <#1195401593101766727> \n"
            "Guild chat channel. Feel free to ask questions, etc.\n\n"
            "> <#1285559379890012282> \n"
            "Self-introduction channel (optional).\n\n"
            "> <#1343603819610898545> \n"
            "Information sharing channel. Please take a look!\n\n"
            "- When you've read the info, please follow the staff's instructions."
        )
        embed = discord.Embed(
            title="Welcome & Info",
            description=desc,
            color=discord.Color.green()
        )
    embed.set_footer(text="チケットガイド | Minister Chikuwa")
    return embed

def make_application_guide_embed():
    desc = (
        "## > 🇯🇵｜日本語\n"
        "チケットを作成し質問に回答した上で、ゲーム内でのスタッフからの招待をお待ち下さい。\n"
        "スタッフが確認し次第、対応いたします。\n\n"
        "このギルドは、日本人と海外の人たちが共に仲良くWynncraftを楽しむためのギルドです。\n"
        "日本人の間ではあまりメジャーではないGuild Warにも取り組んでおり、Guild Raidも活発です。\n"
        "ぜひ、お気軽にご申請ください！\n\n\n"
        "### > 要件(無制限になる場合があります)\n"
        "- 少なくとも一つのClassが105レベル以上であること。\n"
        "- 週に合計で10時間以上プレイしていること。\n"
        "- メインアカウントであること - サブアカウントでの参加は原則禁止です。\n\n"
        "### > 質問\n"
        "- あなたのMCID(アカウントのお名前)をご記入ください。\n"
        "- 当ギルドに加入したいと考えた理由を教えて下さい。\n"
        "- 当ギルドへ参加する以前に、他のギルドに所属していたことがありますか？その場合、そのギルドの名前を教えていただけると幸いです。(任意です)\n\n"
        "### > 注意\n"
        "- 現在多くの申請をいただいているため、参加までしばらくの間お待ちいただく場合がございます。\n"
        "- また長期間ログインした記録がない場合(__1週間から2週間ほど__)や、プレイ時間が少ない場合にこちら側で退会の手続きを執り行う場合がございます。\n"
        "- その場合でも、再度Chiefにご連絡していただければ優先的に再加入することが可能です。\n\n\n"
        "## > 🇬🇧｜English\n"
        "Please open a ticket, answer the questions below, and wait for a staff member to invite you in-game.\n"
        "Once a staff member checks your application, we’ll get back to you!\n\n"
        "Our guild is all about bringing together Japanese and international players to enjoy Wynncraft together.\n"
        "We actively participate in Guild Wars and Guild Raids regularly.\n"
        "Feel free to apply—we’re looking forward to meeting you!\n\n\n"
        "### > Requirements (may change depending on activity)\n"
        "- At least one class at level 105+.\n"
        "- Around 10+ hours of playtime per week.\n"
        "- Main accounts only — alts are not allowed.\n\n"
        "### > Questions\n"
        "- What’s your MCID (in-game name)?\n"
        "- Why would you like to join our guild?\n"
        "- Have you ever been in another guild before? If yes, feel free to share the name. (optional)\n\n"
        "### > Notes\n"
        "- Due to the high number of applications, it may take some time before you can join.\n"
        "- Inactive players (__around 1–2 weeks without logging in__) or those with very low playtime may be removed.\n"
        "- Don’t worry though—if that happens, you can always reach out to a Chief member for priority rejoining."
    )
    embed = discord.Embed(
        title="Empire of TKW ギルドメンバー申請/Member Application｜📝",
        description=desc,
        color=discord.Color.blue()
    )
    embed.set_footer(text="加入申請システム | Minister Chikuwa")
    return embed

# チケット
class TicketUserView(discord.ui.View):
    _question_cooldowns = {}
    QUESTION_COOLDOWN_SEC = 600  # 10分

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🇯🇵 日本語", style=discord.ButtonStyle.secondary, custom_id="user_lang_ja")
    async def lang_ja(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = make_user_guide_embed(lang="ja")
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="🇬🇧 English", style=discord.ButtonStyle.secondary, custom_id="user_lang_en")
    async def lang_en(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = make_user_guide_embed(lang="en")
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="❓ 質問 / Question", style=discord.ButtonStyle.primary, custom_id="user_question")
    async def question(self, interaction: discord.Interaction, button: discord.ui.Button):
        now = int(time.time())
        key = (interaction.channel.id, interaction.user.id)
        last = self._question_cooldowns.get(key, 0)
        cooldown = self.QUESTION_COOLDOWN_SEC
        if now - last < cooldown:
            wait_sec = cooldown - (now - last)
            minutes = wait_sec // 60
            seconds = wait_sec % 60
            msg = f"質問ボタンはクールダウン中です。あと{minutes}分{seconds}秒お待ちください。"
            await interaction.response.send_message(msg, ephemeral=True)
            return
        self._question_cooldowns[key] = now
        modal = TicketQuestionModal(TICKET_STAFF_ROLE_ID)
        await interaction.response.send_modal(modal)

class TicketQuestionModal(discord.ui.Modal, title="質問 / Question"):
    def __init__(self, staff_role_id: int):
        super().__init__()
        self.staff_role_id = staff_role_id
        self.question = discord.ui.TextInput(
            label="質問内容 / Your Question",
            style=discord.TextStyle.paragraph,
            placeholder="聞きたい内容を入力してください / Please enter your question",
            required=True,
            max_length=500
        )
        self.add_item(self.question)

    async def on_submit(self, interaction: discord.Interaction):
        staff_mention = f"<@&{self.staff_role_id}>"
        q_text = self.question.value
        embed = discord.Embed(
            title="新規メンバーからの質問 / Question from Applicant",
            description=q_text,
            color=discord.Color.orange()
        )
        embed.set_footer(text=f"質問者: {interaction.user.display_name}")
        await interaction.channel.send(content=staff_mention, embed=embed)
        await interaction.response.send_message("質問を送信しました。スタッフの回答をお待ちください。", ephemeral=True)

# チケットEmbed送信
async def send_ticket_user_embed(channel, user_id: int, staff_role_id: int):
    embed = make_user_guide_embed(lang="ja")
    view = TicketUserView()
    content = f"<@{user_id}>" if user_id else None
    await channel.send(content=content, embed=embed, view=view)

# 申請ボタン
class ApplicationButtonView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @button(label="加入申請/Application", style=discord.ButtonStyle.green, custom_id="application_start")
    async def application_start(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        user = interaction.user
        category = guild.get_channel(APPLICATION_CATEGORY_ID)
        ticket_exists = False
        
        if category and isinstance(category, discord.CategoryChannel):
            for ch in category.text_channels:
                # チャンネル名にuser idやMCIDが入っている場合は、それで判定
                perms = ch.permissions_for(user)
                if perms.send_messages:
                    ticket_exists = True
                    break
        if ticket_exists:
            await interaction.response.send_message(
                "既にあなたのチケットが存在します。新しいチケットを作成できません。",
                ephemeral=True
            )
            return
            
        await interaction.response.send_modal(ApplicationFormModal())

    @staticmethod
    def make_application_guide_embed():
        return make_application_guide_embed()

# 申請フォーム
class ApplicationFormModal(Modal, title="ギルド加入申請フォーム"):
    def __init__(self):
        super().__init__()
        self.mcid = TextInput(label="MCID/Your IGN", placeholder="正確に入力/Type accurately", required=True)
        self.reason = TextInput(label="加入理由/Reason", placeholder="簡単でOK/Write simply", required=True, style=discord.TextStyle.long)
        self.prev_guild = TextInput(label="最後に所属していたギルド/The Last Guild", placeholder="任意/Optional", required=False)
        self.add_item(self.mcid)
        self.add_item(self.reason)
        self.add_item(self.prev_guild)

    async def on_submit(self, interaction: discord.Interaction):
        # 1. defer（最初に必ず返す！）
        await interaction.response.defer(ephemeral=True)

        guild = interaction.guild
        category = guild.get_channel(APPLICATION_CATEGORY_ID)
        
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        }
        
        if not isinstance(category, discord.CategoryChannel):
            category = None
        channel = await guild.create_text_channel(
            name=f"application-{self.mcid.value}",
            overwrites=overwrites,
            category=category
        )

        # ①ご案内Embed
        await send_ticket_user_embed(channel, interaction.user.id, STAFF_ROLE_ID)

        # ②MCIDからの情報Embed
        username_for_db = None
        try:
            profile_embed, profile_file, username_for_db = await make_profile_embed(self.mcid.value)
            if profile_file:
                await channel.send(embed=profile_embed, file=profile_file)
            else:
                await channel.send(embed=profile_embed)
        except Exception as ee:
            username_for_db = None
            profile_embed = discord.Embed(
                title="プレイヤープロフィール取得失敗",
                description=f"MCID: {self.mcid.value}\n情報取得中にエラーが発生しました。",
                color=discord.Color.red()
            )
            logger.error(f"ぷろふぁいるいめーじせいせいにしっっぱいしたました: {ee}", exc_info=True)
            await channel.send(embed=profile_embed)

        if not username_for_db:
            # 万が一API/profile_infoから取得できなかった場合はAPI再取得
            try:
                api = WynncraftAPI()
                player_data = await api.get_official_player_data(self.mcid.value)
                username_for_db = player_data.get("username", self.mcid.value)
            except Exception:
                username_for_db = self.mcid.value

        # ③理由Embed
        reason_embed = make_reason_embed(self.reason.value)
        await channel.send(embed=reason_embed)

        # ④過去ギルドEmbed
        prev_guild_embed = None
        prev_guild_name = self.prev_guild.value.strip() if self.prev_guild.value else ""
        if prev_guild_name:
            try:
                api = WynncraftAPI()
                guild_info = await search_guild(api, prev_guild_name)
                prev_guild_embed, banner_file = make_prev_guild_embed(guild_info, prev_guild_name)
            except Exception:
                prev_guild_embed, banner_file = discord.Embed(
                    title="過去ギルド情報取得失敗",
                    description=f"入力: {prev_guild_name}\n情報取得中にエラーが発生しました。",
                    color=discord.Color.red()
                ), None
        else:
            prev_guild_embed, banner_file = make_prev_guild_embed(None, "")
        
        view = DeclineButtonView(discord_id=interaction.user.id, channel_id=channel.id)
        if banner_file:
            await channel.send(embed=prev_guild_embed, file=banner_file, view=view)
        else:
            await channel.send(embed=prev_guild_embed, view=view)

        # DB登録
        save_application(username_for_db, interaction.user.id, channel.id)

        # 5. followupで通知
        await interaction.followup.send(
            f"{channel.mention} に申請内容を送信しました。スタッフが確認するまでお待ちください。",
            ephemeral=True
        )

# 登録
def register_persistent_views(bot: discord.Client):
    bot.add_view(ApplicationButtonView())
    bot.add_view(TicketUserView())  # チケット内ガイド/質問ボタン用
