import discord
import asyncio
import logging
from typing import Optional
from io import BytesIO
from lib.db import add_application, get_application_by_discord_id
from lib.ticket_embeds import make_user_guide_embed
from lib.api_stocker import WynncraftAPI, OtherAPI
from config import ETKW_SERVER

logger = logging.getLogger(__name__)

# 設定値 - 必要に応じて config.py に移動可能
APPLICATION_CATEGORY_ID = 1134345613585170542  # 申請チャンネルのカテゴリID
LOG_CHANNEL_ID = None  # トランスクリプト送信先チャンネルID（後で設定）

class ApplicationButtonView(discord.ui.View):
    """申請ボタン付きの永続View"""
    
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🎮 ギルド加入申請", style=discord.ButtonStyle.primary, custom_id="application_button")
    async def application_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # 既存の申請があるかチェック
        existing_app = get_application_by_discord_id(interaction.user.id)
        if existing_app:
            await interaction.response.send_message(
                f"既に申請が存在します。申請チャンネル: <#{existing_app['channel_id']}>",
                ephemeral=True
            )
            return
        
        # 申請モーダルを表示
        modal = ApplicationModal()
        await interaction.response.send_modal(modal)


class ApplicationModal(discord.ui.Modal, title="ギルド加入申請"):
    """申請フォームモーダル"""
    
    def __init__(self):
        super().__init__()
        
        self.mcid = discord.ui.TextInput(
            label="MCID（必須）",
            placeholder="あなたのMinecraftユーザー名を入力してください",
            required=True,
            max_length=16
        )
        self.add_item(self.mcid)
        
        self.reason = discord.ui.TextInput(
            label="加入理由（必須）",
            style=discord.TextStyle.paragraph,
            placeholder="ギルドに加入したい理由を教えてください",
            required=True,
            max_length=500
        )
        self.add_item(self.reason)
        
        self.past_guild = discord.ui.TextInput(
            label="過去のギルド（任意）",
            placeholder="以前に所属していたギルドがあれば教えてください",
            required=False,
            max_length=100
        )
        self.add_item(self.past_guild)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        mcid = self.mcid.value.strip()
        reason = self.reason.value.strip()
        past_guild = self.past_guild.value.strip() if self.past_guild.value else None
        
        try:
            # 申請者専用チャンネルを作成
            guild = interaction.guild
            category = guild.get_channel(APPLICATION_CATEGORY_ID)
            
            if not category:
                await interaction.followup.send("申請チャンネルの作成に失敗しました。管理者にお問い合わせください。", ephemeral=True)
                return
            
            # チャンネル名は「申請-MCID」の形式
            channel_name = f"申請-{mcid}"
            
            # 申請者にのみ見えるチャンネルを作成
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=False),
                interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
                guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
            }
            
            # スタッフロールがあれば追加
            staff_role = guild.get_role(1404665259112792095)  # TICKET_STAFF_ROLE_ID
            if staff_role:
                overwrites[staff_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
            
            application_channel = await category.create_text_channel(
                name=channel_name,
                overwrites=overwrites,
                reason=f"ギルド加入申請 - {interaction.user} ({mcid})"
            )
            
            # DBに申請情報を保存
            if not add_application(mcid, interaction.user.id, reason, past_guild, application_channel.id):
                await application_channel.delete(reason="DB保存失敗により削除")
                await interaction.followup.send("申請の保存に失敗しました。もう一度お試しください。", ephemeral=True)
                return
            
            # 申請チャンネルにEmbedを送信
            await self.send_application_embeds(application_channel, interaction.user, mcid, reason, past_guild)
            
            await interaction.followup.send(
                f"申請を受け付けました！専用チャンネル: {application_channel.mention}\n"
                "スタッフが確認してゲーム内で招待いたします。しばらくお待ちください。",
                ephemeral=True
            )
            
        except Exception as e:
            logger.error(f"申請処理中にエラー: {e}", exc_info=True)
            await interaction.followup.send("申請の処理中にエラーが発生しました。管理者にお問い合わせください。", ephemeral=True)

    async def send_application_embeds(self, channel: discord.TextChannel, user: discord.User, mcid: str, reason: str, past_guild: Optional[str]):
        """申請チャンネルに必要なEmbedを送信"""
        
        # ① ご案内Embed（既存の関数を流用）
        guide_embed = make_user_guide_embed(lang="ja")
        await channel.send(f"<@{user.id}>", embed=guide_embed)
        
        # ② MCIDから取得できる情報のEmbed
        await self.send_mcid_profile_embed(channel, mcid)
        
        # ③ 理由のEmbed
        reason_embed = discord.Embed(
            title="🎯 加入理由",
            description=reason,
            color=discord.Color.blue()
        )
        await channel.send(embed=reason_embed)
        
        # ④ 過去ギルド情報のEmbed
        await self.send_past_guild_embed(channel, past_guild, mcid)

    async def send_mcid_profile_embed(self, channel: discord.TextChannel, mcid: str):
        """MCIDからプロファイル情報を取得してEmbedで送信"""
        try:
            api = WynncraftAPI()
            other_api = OtherAPI()
            
            # プレイヤーデータを取得
            player_data = await api.get_official_player_data(mcid)
            
            if not player_data:
                embed = discord.Embed(
                    title="⚠️ プレイヤー情報",
                    description=f"MCID: `{mcid}`\n\nプレイヤー情報を取得できませんでした。",
                    color=discord.Color.orange()
                )
                await channel.send(embed=embed)
                return
            
            # プレイヤー情報Embedを作成
            username = player_data.get("username", mcid)
            uuid = player_data.get("uuid")
            rank = player_data.get("rank", "Player")
            playtime = player_data.get("playtime", 0)
            
            # プレイ時間を時間単位に変換
            hours = playtime / 60 if playtime else 0
            
            embed = discord.Embed(
                title="📊 プレイヤー情報",
                color=discord.Color.green()
            )
            embed.add_field(name="MCID", value=f"`{username}`", inline=True)
            embed.add_field(name="ランク", value=rank, inline=True)
            embed.add_field(name="プレイ時間", value=f"{hours:.1f}時間", inline=True)
            
            if uuid:
                embed.add_field(name="UUID", value=f"`{uuid}`", inline=False)
                
                # スキン画像を取得してサムネイルに設定
                try:
                    skin_bytes = await other_api.get_vzge_skin(uuid)
                    if skin_bytes:
                        # 一時的にファイルとして保存してアップロード
                        skin_file = discord.File(BytesIO(skin_bytes), filename=f"{username}_skin.png")
                        embed.set_thumbnail(url=f"attachment://{username}_skin.png")
                        await channel.send(embed=embed, file=skin_file)
                        return
                except Exception as e:
                    logger.warning(f"スキン画像の取得に失敗: {e}")
            
            await channel.send(embed=embed)
            
        except Exception as e:
            logger.error(f"プレイヤー情報の取得に失敗: {e}", exc_info=True)
            embed = discord.Embed(
                title="⚠️ プレイヤー情報",
                description=f"MCID: `{mcid}`\n\nプレイヤー情報の取得中にエラーが発生しました。",
                color=discord.Color.red()
            )
            await channel.send(embed=embed)

    async def send_past_guild_embed(self, channel: discord.TextChannel, past_guild: Optional[str], mcid: str):
        """過去ギルド情報のEmbedを送信"""
        if not past_guild:
            embed = discord.Embed(
                title="🏰 過去のギルド",
                description="過去のギルド情報はありません。",
                color=discord.Color.light_grey()
            )
            await channel.send(embed=embed)
            return
        
        try:
            api = WynncraftAPI()
            
            # ギルド情報を取得（プレフィックスまたは名前で検索）
            guild_data = None
            
            # まずプレフィックスで検索
            try:
                guild_data = await api.get_guild_by_prefix(past_guild)
            except:
                pass
            
            # プレフィックスで見つからない場合は名前で検索
            if not guild_data:
                try:
                    guild_data = await api.get_guild_by_name(past_guild)
                except:
                    pass
            
            if guild_data:
                guild_name = guild_data.get("name", past_guild)
                guild_prefix = guild_data.get("prefix", "")
                member_count = guild_data.get("members", {}).get("total", 0)
                created = guild_data.get("created", "")
                
                embed = discord.Embed(
                    title="🏰 過去のギルド",
                    color=discord.Color.purple()
                )
                embed.add_field(name="ギルド名", value=guild_name, inline=True)
                if guild_prefix:
                    embed.add_field(name="プレフィックス", value=f"`{guild_prefix}`", inline=True)
                embed.add_field(name="メンバー数", value=f"{member_count}人", inline=True)
                if created:
                    embed.add_field(name="設立日", value=created, inline=False)
                
                # 該当プレイヤーがそのギルドにいるかチェック
                members = guild_data.get("members", {})
                found_in_guild = False
                for rank, rank_members in members.items():
                    if rank == "total":
                        continue
                    if mcid in rank_members:
                        embed.add_field(name="現在の状況", value=f"現在も`{rank}`として所属中", inline=False)
                        found_in_guild = True
                        break
                
                if not found_in_guild:
                    embed.add_field(name="現在の状況", value="現在は脱退済み", inline=False)
                    
            else:
                # ギルドが見つからない場合は入力された情報をそのまま表示
                embed = discord.Embed(
                    title="🏰 過去のギルド",
                    description=f"ギルド情報: `{past_guild}`\n\n*詳細な情報は取得できませんでした*",
                    color=discord.Color.orange()
                )
            
            await channel.send(embed=embed)
            
        except Exception as e:
            logger.error(f"過去ギルド情報の取得に失敗: {e}", exc_info=True)
            embed = discord.Embed(
                title="🏰 過去のギルド",
                description=f"ギルド情報: `{past_guild}`\n\n*情報取得中にエラーが発生しました*",
                color=discord.Color.red()
            )
            await channel.send(embed=embed)


def register_application_views(bot: discord.Client):
    """申請関連のViewを永続登録"""
    bot.add_view(ApplicationButtonView())
    logger.info("申請システムの永続Viewを登録しました")


async def send_application_embed(channel: discord.TextChannel):
    """申請チャンネルに申請ボタン付きEmbedを送信"""
    embed = discord.Embed(
        title="🎮 ギルド加入申請",
        description=(
            "ETKWギルドへの加入を希望される方は、下記ボタンから申請してください。\n\n"
            "**申請に必要な情報:**\n"
            "• MCID（Minecraftユーザー名）\n"
            "• 加入理由\n"
            "• 過去のギルド（任意）\n\n"
            "申請後、スタッフが確認してゲーム内で招待いたします。\n"
            "専用の申請チャンネルが自動作成されますので、そちらでお待ちください。"
        ),
        color=discord.Color.green()
    )
    embed.set_footer(text="Minister Chikuwa Bot | ETKW Guild Application System")
    
    view = ApplicationButtonView()
    await channel.send(embed=embed, view=view)


async def ensure_application_embed(bot: discord.Client, channel_id: int):
    """申請チャンネルに申請Embedが1つだけ存在することを確認"""
    try:
        channel = bot.get_channel(channel_id)
        if not channel:
            logger.warning(f"申請チャンネル (ID: {channel_id}) が見つかりません")
            return
        
        # 最新のメッセージを確認
        async for message in channel.history(limit=10):
            if (message.author == bot.user and 
                message.embeds and 
                "🎮 ギルド加入申請" in message.embeds[0].title and
                message.components):  # View付きのメッセージ
                # 既に適切な申請Embedが存在
                return
        
        # 申請Embedが見つからない場合は新規送信
        await send_application_embed(channel)
        logger.info(f"申請チャンネル (ID: {channel_id}) に申請Embedを送信しました")
        
    except Exception as e:
        logger.error(f"申請Embed確認中にエラー: {e}", exc_info=True)