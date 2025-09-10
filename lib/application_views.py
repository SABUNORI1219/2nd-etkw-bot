import discord
from discord.ui import View, Modal, TextInput, button
from lib.db import save_application
from lib.ticket_embeds import make_application_guide_embed

# --- 申請ボタンView ---
class ApplicationButtonView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @button(label="加入申請はこちら", style=discord.ButtonStyle.green, custom_id="application_start")
    async def application_start(self, interaction: discord.Interaction, button: discord.ui.Button):
        # 申請フォームModalを表示
        await interaction.response.send_modal(ApplicationFormModal())

    @staticmethod
    def make_application_guide_embed():
        # 日本語案内Embed（lib.ticket_embeds.py流用推奨、なければここで定義）
        return make_application_guide_embed()

# --- 申請フォームModal ---
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
            # 必要に応じてスタッフロールにも閲覧権限
        }
        # 新規チャンネル作成
        category = discord.utils.get(guild.categories, name="加入申請")  # カテゴリ名は実際のサーバーに合わせて修正
        channel = await guild.create_text_channel(
            name=f"申請-{self.mcid.value}",
            overwrites=overwrites,
            category=category
        )
        # ①ご案内Embed
        await channel.send(embed=make_application_guide_embed())
        # ②MCIDからの情報Embed（ここでAPI呼び出し等）
        # ③理由Embed
        # ④過去ギルドEmbed（APIアクセス＋予備処理）
        # ...（ここは順次拡張）

        # 必要な情報をDBに保存
        save_application(self.mcid.value, interaction.user.id, channel.id)
        await interaction.response.send_message(
            f"{channel.mention} に申請内容を送信しました。スタッフが確認するまでお待ちください。",
            ephemeral=True
        )

# --- PersistentViewの登録 ---
def register_persistent_views(bot: discord.Client):
    bot.add_view(ApplicationButtonView())
