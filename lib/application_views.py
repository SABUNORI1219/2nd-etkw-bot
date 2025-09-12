import discord
from discord.ext import commands
from discord.ui import View, Modal, TextInput, button
import time
from typing import Optional

from lib.db import save_application
from lib.api_stocker import WynncraftAPI

# ---------- 設定ID ----------
APPLICATION_CATEGORY_ID = 1415492214087483484
APPLICATION_CHANNEL_ID = 1415107620108501082
TICKET_STAFF_ROLE_ID = 1404665259112792095  # チケットのスタッフロールID
STAFF_ROLE_ID = 1158540148783448134         # 申請フォーム用スタッフロールID

# ---------- Embed生成 ----------
def make_reason_embed(reason):
    return discord.Embed(
        title="加入理由",
        description=reason,
        color=discord.Color.purple()
    )

def make_prev_guild_embed(guild_info, input_name):
    # guild_infoがdictならguild_cogと同じ要約方式で整形
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
        # オンライン人数サマリは省略（長文化対策）
        desc = (
            f"```python\n"
            f"Guild: {name} [{prefix}]\n"
            f"Owner: {owner}\n"
            f"Created: {created_date}\n"
            f"Level: {level} [{xp_percent}%]\n"
            f"Wars: {wars}\n"
            f"Latest SR: {rating_display} [Season {latest_season}]\n"
            f"Territories: {territories}\n"
            f"Members: {total_members}\n"
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
        title="過去ギルド情報",
        description=desc,
        color=discord.Color.orange()
    )
    return embed

def make_profile_embed(mcid, profile_data):
    desc = f"```\n{profile_data}\n```" if profile_data else "情報取得失敗"
    embed = discord.Embed(
        title=f"{mcid} さんのプロフィール",
        description=desc,
        color=discord.Color.blue()
    )
    return embed

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
            "- 情報の確認が終わりましたらスタッフの案内に従ってください。"
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
        "ギルド加入希望の方はこちらのボタンから申請してください。\n"
        "申請後、スタッフが順次ご案内します。"
    )
    embed = discord.Embed(
        title="[ギルド加入申請] ご案内",
        description=desc,
        color=discord.Color.green()
    )
    embed.set_footer(text="Minister Chikuwa | 加入申請システム")
    return embed

# ---------- チケットビュー ----------
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

# ---------- チケット用埋め込み送信 ----------
async def send_ticket_user_embed(channel, user_id: int, staff_role_id: int):
    embed = make_user_guide_embed(lang="ja")
    view = TicketUserView()
    content = f"<@{user_id}>" if user_id else None
    await channel.send(content=content, embed=embed, view=view)

# ---------- 申請ボタンView ----------
class ApplicationButtonView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @button(label="加入申請はこちら", style=discord.ButtonStyle.green, custom_id="application_start")
    async def application_start(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ApplicationFormModal())

    @staticmethod
    def make_application_guide_embed():
        return make_application_guide_embed()

# ---------- 申請フォームModal ----------
class ApplicationFormModal(Modal, title="ギルド加入申請フォーム"):
    def __init__(self):
        super().__init__()
        self.mcid = TextInput(label="Minecraft ID", placeholder="正確に入力", required=True)
        self.reason = TextInput(label="加入理由", placeholder="簡単でOK", required=True, style=discord.TextStyle.long)
        self.prev_guild = TextInput(label="過去のギルド経験", placeholder="任意", required=False)
        self.add_item(self.mcid)
        self.add_item(self.reason)
        self.add_item(self.prev_guild)

    async def on_submit(self, interaction: discord.Interaction):
        guild = interaction.guild
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        }
        category = guild.get_channel(APPLICATION_CATEGORY_ID)
        if not isinstance(category, discord.CategoryChannel):
            category = None
        channel = await guild.create_text_channel(
            name=f"申請-{self.mcid.value}",
            overwrites=overwrites,
            category=category
        )

        # ①ご案内Embed（async関数はawaitして呼ぶ！）
        await send_ticket_user_embed(channel, interaction.user.id, STAFF_ROLE_ID)

        # ②MCIDからの情報Embed
        try:
            api = WynncraftAPI()
            profile_data = await api.get_player_profile(self.mcid.value)
            profile_embed = make_profile_embed(self.mcid.value, profile_data)
        except Exception:
            profile_embed = discord.Embed(
                title="プレイヤープロフィール取得失敗",
                description=f"MCID: {self.mcid.value}\n情報取得中にエラーが発生しました。",
                color=discord.Color.red()
            )
        await channel.send(embed=profile_embed)

        # ③理由Embed
        reason_embed = make_reason_embed(self.reason.value)
        await channel.send(embed=reason_embed)

        # ④過去ギルドEmbed
        prev_guild_embed = None
        prev_guild_name = self.prev_guild.value.strip() if self.prev_guild.value else ""
        if prev_guild_name:
            try:
                api = WynncraftAPI()
                guild_info = await api.get_guild_by_prefix(prev_guild_name)
                if not guild_info:
                    guild_info = await api.get_guild_by_prefix(prev_guild_name.capitalize())
                if not guild_info:
                    guild_info = await api.get_guild_by_prefix(prev_guild_name.upper())
                if not guild_info:
                    guild_info = await api.get_guild_by_prefix(prev_guild_name.lower())
                prev_guild_embed = make_prev_guild_embed(guild_info, prev_guild_name)
            except Exception:
                prev_guild_embed = discord.Embed(
                    title="過去ギルド情報取得失敗",
                    description=f"入力: {prev_guild_name}\n情報取得中にエラーが発生しました。",
                    color=discord.Color.red()
                )
        else:
            prev_guild_embed = make_prev_guild_embed(None, "")
        await channel.send(embed=prev_guild_embed)

        # DB登録
        save_application(self.mcid.value, interaction.user.id)
        await interaction.response.send_message(
            f"{channel.mention} に申請内容を送信しました。スタッフが確認するまでお待ちください。",
            ephemeral=True
        )

# ---------- PersistentViewの登録 ----------
def register_persistent_views(bot: discord.Client):
    bot.add_view(ApplicationButtonView())
    bot.add_view(TicketUserView())  # チケット内ガイド/質問ボタン用
