import discord
import asyncio
from discord.utils import escape_markdown
from typing import Optional

TICKET_STAFF_ROLE_ID = 1387259707743277177  # スタッフロールID
TICKET_CATEGORY_ID = 1134345613585170542    # チケットカテゴリID

# --- ボタン押下フラグをViewで管理（各チャンネルごと） ---

class TicketState:
    """1つのチケット用の状態管理"""
    def __init__(self):
        self.user_confirmed = False
        self.staff_confirmed = False
        self.user_id = None
        self.staff_id = None

# --- グローバル: チャンネルID→TicketState ---
_channel_ticket_state = {}

def get_ticket_state(channel_id):
    if channel_id not in _channel_ticket_state:
        _channel_ticket_state[channel_id] = TicketState()
    return _channel_ticket_state[channel_id]

# --- 新規ユーザー案内Embed/ボタン ---

class TicketUserView(discord.ui.View):
    def __init__(self, user_id: int, staff_role_id: int, ticket_channel_id: int):
        super().__init__(timeout=None)
        self.user_id = user_id
        self.staff_role_id = staff_role_id
        self.ticket_channel_id = ticket_channel_id

    @discord.ui.button(label="🇯🇵 日本語", style=discord.ButtonStyle.secondary, custom_id="user_lang_ja")
    async def lang_ja(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This button is for the applicant.", ephemeral=True)
            return
        embed = make_user_guide_embed(self.user_id, lang="ja")
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="🇺🇸 English", style=discord.ButtonStyle.secondary, custom_id="user_lang_en")
    async def lang_en(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This button is for the applicant.", ephemeral=True)
            return
        embed = make_user_guide_embed(self.user_id, lang="en")
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="❓ 質問 / Question", style=discord.ButtonStyle.primary, custom_id="user_question")
    async def question(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("質問ボタンは申請者のみ利用できます。", ephemeral=True)
            return
        # Modalで質問内容を入力
        modal = TicketQuestionModal(self.staff_role_id)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="✅ 確認済み / Confirmed", style=discord.ButtonStyle.success, custom_id="user_confirmed")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("このボタンは申請者のみ利用できます。", ephemeral=True)
            return
        state = get_ticket_state(interaction.channel.id)
        if state.user_confirmed:
            await interaction.response.send_message("すでに確認済みです。", ephemeral=True)
            return
        state.user_confirmed = True
        state.user_id = interaction.user.id
        await interaction.response.send_message("確認済みとして受け付けました。スタッフの対応をお待ちください。", ephemeral=True)
        await check_ticket_completion(interaction.channel, state)

# --- スタッフ用Embed/ボタン ---

class TicketStaffView(discord.ui.View):
    def __init__(self, user_id: int, staff_role_id: int, ticket_channel_id: int):
        super().__init__(timeout=None)
        self.user_id = user_id
        self.staff_role_id = staff_role_id
        self.ticket_channel_id = ticket_channel_id

    @discord.ui.button(label="✅ 加入済み / Invited", style=discord.ButtonStyle.success, custom_id="staff_confirmed")
    async def staff_confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        # スタッフロールを持っていることを確認
        if not any(r.id == self.staff_role_id for r in interaction.user.roles):
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

# --- 「質問」モーダル ---

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

# --- Embed生成 ---

def make_user_guide_embed(user_id: int, lang: str = "ja") -> discord.Embed:
    user_mention = f"<@{user_id}>"
    if lang == "ja":
        desc = (
            f"{user_mention}\n"
            "こんにちは！\n"
            "スタッフがチケットを確認し、ゲーム内で招待するまでお待ちください。\n"
            "時間帯によっては、確認および招待までに時間がかかる場合があります。\n"
            "また何か質問があれば、下記ボタンから送信できます。担当スタッフが対応します。\n"
            "\n"
            "**ギルドカテゴリ内チャンネル紹介:**\n"
            "> <#1310992907527786538> \n"
            "ギルド内でのアナウンスが行われます。\n\n"
            "> <#1333036649075970058> \n"
            "ギルドに関する情報が掲載されています。\n\n"
            "> <#1134309996339925113> n"
            "ギルド内専用のチャットです。お気軽に質問等どうぞ。\n\n"
            "> <#1285559379890012282> \n"
            "自己紹介用のチャンネルです。任意です。\n\n"
            "> <#1343603819610898545> \n"
            "ギルド内での情報が共有されています。ぜひご一読ください。\n\n"
            "- 情報の確認が終わりましたら「確認済み」ボタンを押してください。"
        )
        embed = discord.Embed(
            title="ご案内",
            description=desc,
            color=discord.Color.green()
        )
    else:
        desc = (
            f"{user_mention}\n"
            "Hello!\n"
            "Please wait while staff review your ticket and invite you in-game.\n"
            "Depending on the time of day, confirmation/invite may take some time.\n"
            "If you have any questions, use the button below. A staff member will assist you.\n"
            "\n"
            "**Guild Channels:**\n"
            "> <#1310992907527786538> \n"
            "Announcements for the guild.\n\n"
            "> <#1333036649075970058> \n"
            "Information about the guild.\n\n"
            "> <#1134309996339925113> \n"
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
        "プレイヤーの招待およびユーザーからの確認が終わり次第、当チケットのトランスクリプト/クローズをBotが自動実行します。"
    )
    embed = discord.Embed(
        title="プレイヤー情報",
        description=desc,
        color=discord.Color.blue()
    )
    embed.set_footer(text=f"申請者 -> {applicant_name}")
    if profile_image_path:
        embed.set_image(url=f"attachment://{profile_image_path}")
    return embed

# --- チケット完了判定 ---

async def check_ticket_completion(channel, state: TicketState):
    """両方のボタンが押されたらtranscript/closeを自動実行"""
    if state.user_confirmed and state.staff_confirmed:
        await channel.send("両者の確認が取れたため、チケットのトランスクリプトおよびクローズを自動実行します。")
        # Ticket Toolのコマンド（slash command）を送信
        try:
            await asyncio.sleep(2)
            await channel.send("/transcript")
            await asyncio.sleep(2)
            await channel.send("/close")
        except Exception:
            pass

# --- 外部から呼び出す: Embed+View送信ヘルパ ---

async def send_ticket_user_embed(channel, user_id: int, staff_role_id: int):
    embed = make_user_guide_embed(user_id, lang="ja")
    view = TicketUserView(user_id, staff_role_id, channel.id)
    await channel.send(embed=embed, view=view)

async def send_ticket_staff_embed(channel, profile_image_path: Optional[str], applicant_name: str, user_id: int, staff_role_id: int):
    embed = make_staff_embed(profile_image_path, applicant_name)
    view = TicketStaffView(user_id, staff_role_id, channel.id)
    # プロファイル画像ありなら添付
    files = []
    if profile_image_path:
        files = [discord.File(profile_image_path)]
    await channel.send(embed=embed, view=view, files=files)
