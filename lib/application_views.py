import discord
from discord.ui import View, Modal, TextInput, button
from lib.db import save_application
from lib.ticket_embeds import make_application_guide_embed, make_profile_embed, make_reason_embed, make_prev_guild_embed
from lib.api_stocker import WynncraftAPI

# CATEGORY ID DESU
APPLICATION_CATEGORY_ID = 1415492214087483484

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
            # 必要に応じてスタッフロールにも閲覧権限を追加
        }

        # --- カテゴリ取得・指定（ID優先、なければNone） ---
        category = guild.get_channel(APPLICATION_CATEGORY_ID)
        if not isinstance(category, discord.CategoryChannel):
            category = None

        # --- 新規チャンネル作成 ---
        channel = await guild.create_text_channel(
            name=f"申請-{self.mcid.value}",
            overwrites=overwrites,
            category=category
        )

        # ①ご案内Embed
        await channel.send(embed=make_application_guide_embed())

        # ②MCIDからの情報Embed（API呼び出し等）
        profile_embed = None
        try:
            api = WynncraftAPI()
            profile_data = await api.get_player_profile(self.mcid.value)
            profile_embed = make_profile_embed(self.mcid.value, profile_data)
        except Exception as e:
            profile_embed = discord.Embed(
                title="プレイヤープロフィール取得失敗",
                description=f"MCID: {self.mcid.value}\n情報取得中にエラーが発生しました。",
                color=discord.Color.red()
            )
        await channel.send(embed=profile_embed)

        # ③理由Embed
        reason_embed = make_reason_embed(self.reason.value)
        await channel.send(embed=reason_embed)

        # ④過去ギルドEmbed（APIアクセス＋予備処理）
        prev_guild_embed = None
        prev_guild_name = self.prev_guild.value.strip() if self.prev_guild.value else ""
        if prev_guild_name:
            try:
                api = WynncraftAPI()
                # 入力値そのまま
                guild_info = await api.get_guild_by_name(prev_guild_name)
                # 最初だけ大文字
                if not guild_info:
                    guild_info = await api.get_guild_by_name(prev_guild_name.capitalize())
                # 全部大文字
                if not guild_info:
                    guild_info = await api.get_guild_by_name(prev_guild_name.upper())
                # 全部小文字
                if not guild_info:
                    guild_info = await api.get_guild_by_name(prev_guild_name.lower())
                prev_guild_embed = make_prev_guild_embed(guild_info, prev_guild_name)
            except Exception as e:
                prev_guild_embed = discord.Embed(
                    title="過去ギルド情報取得失敗",
                    description=f"入力: {prev_guild_name}\n情報取得中にエラーが発生しました。",
                    color=discord.Color.red()
                )
        else:
            prev_guild_embed = make_prev_guild_embed(None, "")

        await channel.send(embed=prev_guild_embed)

        # 必要な情報をDBに保存
        save_application(self.mcid.value, interaction.user.id, channel.id)
        await interaction.response.send_message(
            f"{channel.mention} に申請内容を送信しました。スタッフが確認するまでお待ちください。",
            ephemeral=True
        )

# --- PersistentViewの登録 ---
def register_persistent_views(bot: discord.Client):
    bot.add_view(ApplicationButtonView())
