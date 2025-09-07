import discord
import asyncio
from typing import Optional
import time

TICKET_STAFF_ROLE_ID = 1404665259112792095
TICKET_CATEGORY_ID = 1134345613585170542

class TicketState:
    """1つのチケット用の状態管理"""
    def __init__(self):
        self.user_confirmed = False
        self.staff_confirmed = False
        self.user_id = None
        self.staff_id = None

_channel_ticket_state = {}

def get_ticket_state(channel_id):
    if channel_id not in _channel_ticket_state:
        _channel_ticket_state[channel_id] = TicketState()
    return _channel_ticket_state[channel_id]

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
        # クールダウンを更新
        self._question_cooldowns[key] = now
        modal = TicketQuestionModal(TICKET_STAFF_ROLE_ID)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="✅ 確認済み / Confirmed", style=discord.ButtonStyle.success, custom_id="user_confirmed")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        state = get_ticket_state(interaction.channel.id)
        if state.user_id is not None:
            if interaction.user.id != state.user_id:
                await interaction.response.send_message("このボタンは申請者のみ利用できます。", ephemeral=True)
                return
        else:
            state.user_id = interaction.user.id
        if state.user_confirmed:
            await interaction.response.send_message("すでに確認済みです。", ephemeral=True)
            return
        state.user_confirmed = True
        await interaction.response.send_message("確認済みとして受け付けました。スタッフの対応をお待ちください。", ephemeral=True)
        await check_ticket_completion(interaction.channel, state)

class TicketStaffView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="✅ 加入済み / Invited", style=discord.ButtonStyle.success, custom_id="staff_confirmed")
    async def staff_confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not any(r.id == TICKET_STAFF_ROLE_ID for r in getattr(interaction.user, "roles", [])):
            await interaction.response.send_message("このボタンはスタッフのみ利用できます。", ephemeral=True)
            return
        state = get_ticket_state(interaction.channel.id)
        if state.staff_confirmed:
            await interaction.response.send_message("すでに加入済みが報告されています。", ephemeral=True)
            return
        state.staff_confirmed = True
        state.staff_id = interaction.user.id
        await interaction.response.send_message("加入完了を受け付けました。", ephemeral=True)
        await check_ticket_completion(interaction.channel, state)

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
            "- 情報の確認が終わりましたら「確認済み」ボタンを押してください。"
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
            "- When you've read the info, please click the Confirmed button."
        )
        embed = discord.Embed(
            title="Welcome & Info",
            description=desc,
            color=discord.Color.green()
        )
    embed.set_footer(text="チケットガイド | Minister Chikuwa")
    return embed

def make_staff_embed(profile_image_path: Optional[str], applicant_name: str) -> discord.Embed:
    desc = (
        f"- プレイヤー情報を確認してください。\n"
        "- 確認が終わったのちに、ゲーム内で該当プレイヤーを招待してください。\n"
        "「加入済み」ボタンをクリックすることで、該当ユーザーにロールを付与します。\n"
        "- **必ずゲーム内での招待およびプレイヤーの加入が終わったのちに実行してください**。\n"
        "- またAPIの更新の影響で、**加入後から最大10分後**に実行することが推奨されます。\n\n"
        "プレイヤーの招待およびユーザーからの確認が終わり次第、当チケットの保存および閉鎖をBotが自動実行します。"
    )
    embed = discord.Embed(
        title="プレイヤー情報",
        description=desc,
        color=discord.Color.blue()
    )
    embed.set_footer(text=f"申請者: {applicant_name}")
    if profile_image_path:
        embed.set_image(url=f"attachment://{profile_image_path}")
    return embed

async def check_ticket_completion(channel, state: TicketState, bot_token: str):
    if state.user_confirmed and state.staff_confirmed:
        await channel.send("両者の確認が取れたため、チケットのトランスクリプトおよびクローズを自動実行します。")
        try:
            await asyncio.sleep(2)
            await send_discord_interaction(
                guild_id=channel.guild.id,
                channel_id=channel.id,
                command_name="transcript",
                bot_token=bot_token
            )
            await asyncio.sleep(2)
            await send_discord_interaction(
                guild_id=channel.guild.id,
                channel_id=channel.id,
                command_name="close",
                bot_token=bot_token
            )
        except Exception as e:
            print(f"エラーが発生しました: {e}")

async def send_ticket_user_embed(channel, user_id: int, staff_role_id: int):
    embed = make_user_guide_embed(lang="ja")
    view = TicketUserView()
    content = f"<@{user_id}>" if user_id else None
    await channel.send(content=content, embed=embed, view=view)

async def send_ticket_staff_embed(channel, profile_image_path: Optional[str], applicant_name: str, user_id: int, staff_role_id: int):
    embed = make_staff_embed(profile_image_path, applicant_name)
    view = TicketStaffView()
    files = []
    if profile_image_path:
        files = [discord.File(profile_image_path)]
    await channel.send(embed=embed, view=view, files=files)

def register_persistent_views(bot: discord.Client):
    bot.add_view(TicketUserView())
    bot.add_view(TicketStaffView())

def extract_applicant_user_id_from_content(content: str) -> Optional[int]:
    # 例: <@123456789012345678> こんにちは！
    if content.startswith("<@"):
        end = content.find(">")
        if end != -1:
            user_id_str = content[2:end]
            if user_id_str.isdigit():
                return int(user_id_str)
    return None
