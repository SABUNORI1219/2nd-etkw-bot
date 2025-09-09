import discord
import asyncio
import logging
from typing import Optional
from datetime import datetime

from lib.db import save_application_request, get_application_by_discord_id
from lib.api_stocker import WynncraftAPI, OtherAPI
from lib.ticket_embeds import make_user_guide_embed
from config import APPLICATION_CATEGORY_ID, APPLICATION_STAFF_ROLE_ID

logger = logging.getLogger(__name__)

class ApplicationFormModal(discord.ui.Modal, title="ギルド加入申請フォーム"):
    """申請フォームモーダル"""
    
    def __init__(self):
        super().__init__()
    
    mcid = discord.ui.TextInput(
        label="MCID（必須）",
        placeholder="あなたのMinecraftのユーザーネームを入力してください",
        required=True,
        max_length=16
    )
    
    reason = discord.ui.TextInput(
        label="加入理由（必須）",
        placeholder="なぜETKWに加入したいのか、理由を教えてください",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=1000
    )
    
    past_guild = discord.ui.TextInput(
        label="過去所属ギルド（任意）",
        placeholder="以前所属していたギルドがあれば記入してください（任意）",
        required=False,
        max_length=100
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        """フォーム送信時の処理"""
        try:
            await interaction.response.defer(ephemeral=True)
            
            # 既存申請チェック
            existing_app = get_application_by_discord_id(interaction.user.id)
            if existing_app:
                await interaction.followup.send(
                    "❌ 既に申請が提出済みです。重複申請はできません。",
                    ephemeral=True
                )
                return
            
            # 申請専用チャンネル作成
            guild = interaction.guild
            category = guild.get_channel(APPLICATION_CATEGORY_ID)
            if not category:
                await interaction.followup.send(
                    "❌ 申請チャンネルの作成に失敗しました（カテゴリが見つかりません）。",
                    ephemeral=True
                )
                return
            
            # チャンネル名生成
            channel_name = f"申請-{interaction.user.display_name}-{self.mcid.value}"
            # Discord チャンネル名の制限に合わせる
            channel_name = channel_name.replace(" ", "-").lower()[:100]
            
            # 権限設定
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=False),
                interaction.user: discord.PermissionOverwrite(
                    read_messages=True, 
                    send_messages=True, 
                    read_message_history=True
                ),
                guild.get_role(APPLICATION_STAFF_ROLE_ID): discord.PermissionOverwrite(
                    read_messages=True, 
                    send_messages=True, 
                    read_message_history=True,
                    manage_messages=True
                )
            }
            
            # チャンネル作成
            application_channel = await category.create_text_channel(
                name=channel_name,
                overwrites=overwrites,
                topic=f"MCID: {self.mcid.value} の加入申請チャンネル"
            )
            
            # DB保存
            success = save_application_request(
                mcid=self.mcid.value,
                discord_id=interaction.user.id,
                reason=self.reason.value,
                past_guild=self.past_guild.value or None,
                channel_id=application_channel.id
            )
            
            if not success:
                await application_channel.delete()
                await interaction.followup.send(
                    "❌ 申請データの保存に失敗しました。しばらく時間をおいてから再度お試しください。",
                    ephemeral=True
                )
                return
            
            # 申請チャンネルにEmbedを送信
            await self._send_application_embeds(
                channel=application_channel, 
                applicant=interaction.user,
                mcid=self.mcid.value,
                reason=self.reason.value,
                past_guild=self.past_guild.value
            )
            
            await interaction.followup.send(
                f"✅ 申請が正常に提出されました！\n専用チャンネル: {application_channel.mention}",
                ephemeral=True
            )
            
        except Exception as e:
            logger.error(f"[ApplicationForm] 申請処理中にエラー: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ 申請処理中にエラーが発生しました。管理者にお問い合わせください。",
                ephemeral=True
            )
    
    async def _send_application_embeds(self, channel, applicant, mcid: str, reason: str, past_guild: str):
        """申請チャンネルにEmbedを送信"""
        
        # 1. ユーザーガイドEmbed
        guide_embed = make_user_guide_embed(lang="ja")
        await channel.send(f"<@{applicant.id}>", embed=guide_embed)
        
        # 2. MCID情報Embed
        await self._send_mcid_info_embed(channel, mcid)
        
        # 3. 申請理由Embed
        reason_embed = discord.Embed(
            title="📝 加入理由",
            description=reason,
            color=0x00FF00,
            timestamp=datetime.utcnow()
        )
        reason_embed.set_author(name=f"{applicant.display_name} の申請", icon_url=applicant.avatar.url if applicant.avatar else None)
        await channel.send(embed=reason_embed)
        
        # 4. 過去ギルド情報Embed
        if past_guild and past_guild.strip():
            await self._send_past_guild_embed(channel, past_guild, applicant)
    
    async def _send_mcid_info_embed(self, channel, mcid: str):
        """MCID情報Embed送信"""
        try:
            api = WynncraftAPI()
            other_api = OtherAPI()
            
            # プレイヤー情報取得
            player_data = await api.get_official_player_data(mcid)
            
            embed = discord.Embed(
                title="🎮 プレイヤー情報",
                color=0x0099FF,
                timestamp=datetime.utcnow()
            )
            
            if player_data and player_data.get('username'):
                # プロフィール画像取得
                try:
                    if player_data.get('uuid'):
                        skin_image = await other_api.get_vzge_skin_image(player_data['uuid'])
                        if skin_image:
                            # Note: この実装では直接画像URLは設定できないため、画像は後で処理
                            pass
                except Exception as e:
                    logger.warning(f"[ApplicationForm] プロフィール画像取得失敗: {e}")
                
                embed.add_field(name="MCID", value=player_data['username'], inline=True)
                embed.add_field(name="UUID", value=player_data['uuid'][:8] + "...", inline=True)
                
                # ランク情報
                if player_data.get('rank'):
                    embed.add_field(name="ランク", value=player_data['rank'], inline=True)
                
                # クラス情報
                if player_data.get('classes'):
                    classes_info = []
                    for cls_name, cls_data in player_data['classes'].items():
                        level = cls_data.get('level', 0)
                        classes_info.append(f"{cls_name}: Lv.{level}")
                    if classes_info:
                        embed.add_field(
                            name="クラス", 
                            value="\n".join(classes_info[:5]),  # 最大5つまで表示
                            inline=False
                        )
                
                # ギルド情報
                if player_data.get('guild'):
                    guild_info = player_data['guild']
                    guild_name = guild_info.get('name', 'Unknown')
                    guild_prefix = guild_info.get('prefix', '')
                    rank = guild_info.get('rank', '')
                    embed.add_field(
                        name="現在のギルド", 
                        value=f"{guild_name} [{guild_prefix}] - {rank}",
                        inline=False
                    )
                else:
                    embed.add_field(name="現在のギルド", value="なし", inline=False)
                    
            else:
                embed.add_field(name="MCID", value=mcid, inline=True)
                embed.add_field(name="ステータス", value="プレイヤー情報が見つかりませんでした", inline=True)
                embed.color = 0xFF9900
            
            await channel.send(embed=embed)
            
        except Exception as e:
            logger.error(f"[ApplicationForm] MCID情報Embed送信エラー: {e}", exc_info=True)
            # エラー時でも基本情報は表示
            error_embed = discord.Embed(
                title="🎮 プレイヤー情報",
                description=f"MCID: {mcid}\n⚠️ 詳細情報の取得に失敗しました",
                color=0xFF9900,
                timestamp=datetime.utcnow()
            )
            await channel.send(embed=error_embed)
    
    async def _send_past_guild_embed(self, channel, past_guild: str, applicant):
        """過去ギルド情報Embed送信"""
        try:
            api = WynncraftAPI()
            
            embed = discord.Embed(
                title="🏰 過去所属ギルド情報",
                color=0x9966CC,
                timestamp=datetime.utcnow()
            )
            embed.set_author(name=f"{applicant.display_name} の申請", icon_url=applicant.avatar.url if applicant.avatar else None)
            
            # ギルド名またはプレフィックスで検索
            guild_data = None
            
            # まずプレフィックスで検索
            if len(past_guild) <= 4:
                guild_data = await api.get_guild_by_prefix(past_guild.upper())
            
            # プレフィックスで見つからない場合、名前で検索
            if not guild_data:
                # 名前での検索は完全一致のみ対応
                guilds_list = await api.get_guild_list()
                if guilds_list:
                    for guild_name in guilds_list:
                        if guild_name.lower() == past_guild.lower():
                            guild_data = await api.get_guild_by_name(guild_name)
                            break
            
            if guild_data:
                embed.add_field(name="ギルド名", value=guild_data.get('name', 'Unknown'), inline=True)
                embed.add_field(name="プレフィックス", value=guild_data.get('prefix', 'Unknown'), inline=True)
                embed.add_field(name="レベル", value=guild_data.get('level', 'Unknown'), inline=True)
                
                if guild_data.get('created'):
                    embed.add_field(name="設立日", value=guild_data['created'], inline=True)
                
                # メンバー数
                if guild_data.get('members'):
                    total_members = guild_data['members'].get('total', 0)
                    embed.add_field(name="メンバー数", value=f"{total_members}人", inline=True)
                
                embed.add_field(name="検索結果", value="✅ ギルド情報が見つかりました", inline=False)
            else:
                embed.add_field(name="入力されたギルド", value=past_guild, inline=True)
                embed.add_field(name="検索結果", value="⚠️ ギルド情報が見つかりませんでした", inline=False)
                embed.color = 0xFF9900
            
            await channel.send(embed=embed)
            
        except Exception as e:
            logger.error(f"[ApplicationForm] 過去ギルドEmbed送信エラー: {e}", exc_info=True)
            # エラー時でも基本情報は表示
            error_embed = discord.Embed(
                title="🏰 過去所属ギルド情報",
                description=f"入力されたギルド: {past_guild}\n⚠️ ギルド情報の取得に失敗しました",
                color=0xFF9900,
                timestamp=datetime.utcnow()
            )
            error_embed.set_author(name=f"{applicant.display_name} の申請", icon_url=applicant.avatar.url if applicant.avatar else None)
            await channel.send(embed=error_embed)


class ApplicationButtonView(discord.ui.View):
    """申請ボタン用Persistent View"""
    
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(
        label="📝 ギルド加入申請",
        style=discord.ButtonStyle.primary,
        custom_id="application_button",
        emoji="📝"
    )
    async def application_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """申請ボタン押下時の処理"""
        
        # 既存申請チェック
        existing_app = get_application_by_discord_id(interaction.user.id)
        if existing_app:
            await interaction.response.send_message(
                f"❌ 既に申請が提出済みです。\n専用チャンネル: <#{existing_app['channel_id']}>",
                ephemeral=True
            )
            return
        
        # 申請フォームモーダル表示
        modal = ApplicationFormModal()
        await interaction.response.send_modal(modal)


def create_application_embed() -> discord.Embed:
    """申請ボタン用Embed作成"""
    embed = discord.Embed(
        title="🏰 ETKW ギルド加入申請",
        description=(
            "**ETKWへの加入をご希望の方は、下記のボタンから申請フォームにご記入ください。**\n\n"
            "📋 **申請に必要な情報：**\n"
            "• MCID（Minecraftユーザーネーム）\n"
            "• 加入理由\n"
            "• 過去所属ギルド（任意）\n\n"
            "⚠️ **注意事項：**\n"
            "• 申請は1人1回まで\n"
            "• 虚偽の情報での申請は禁止\n"
            "• 申請後、専用チャンネルが作成されます\n"
            "• ギルド加入後、申請チャンネルは自動削除されます\n\n"
            "🤝 **皆様のご参加をお待ちしております！**"
        ),
        color=0x00FF00,
        timestamp=datetime.utcnow()
    )
    embed.set_footer(text="ETKW ギルド管理システム")
    return embed


def register_application_views(bot: discord.Client):
    """申請システムのPersistent View登録"""
    bot.add_view(ApplicationButtonView())
    logger.info("[ApplicationViews] 申請システムのPersistent Viewを登録しました")