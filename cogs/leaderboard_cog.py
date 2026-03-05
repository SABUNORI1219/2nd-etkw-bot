import discord
from discord.ext import commands
from discord import app_commands
import logging
import math
from lib.db import get_seasonal_rating_leaderboard, get_guild_count_by_season, get_available_seasons
from lib.utils import create_embed
from config import AUTHORIZED_USER_IDS, send_authorized_only_message

logger = logging.getLogger(__name__)

class SeasonalRatingView(discord.ui.View):
    """Seasonal Rating専用のページネーションView"""
    
    def __init__(self, season_number: int, items_per_page: int = 10, max_pages: int = 10):
        super().__init__(timeout=300)  # 5分でタイムアウト
        self.season_number = season_number
        self.items_per_page = items_per_page
        self.max_pages = max_pages
        self.current_page = 0
        self.total_items = 0
        self.data = []
        
    async def get_leaderboard_data(self, page: int):
        """シーズン別リーダーボードデータを取得"""
        offset = page * self.items_per_page
        data = get_seasonal_rating_leaderboard(
            season_number=self.season_number,
            limit=self.items_per_page, 
            offset=offset
        )
        total = get_guild_count_by_season(self.season_number)
        return data, total
    
    def create_leaderboard_embed(self, data, page: int, total_pages: int, total_items: int):
        """リーダーボードのEmbedを作成"""
        title = f"🏆 Season {self.season_number} Rating リーダーボード"
        description = f"総ギルド数: {total_items:,}\nページ {page + 1}/{total_pages}"
        
        embed = create_embed(
            title=title,
            description=description,
            color=discord.Color.gold()
        )
        
        if not data:
            embed.add_field(
                name="データなし",
                value=f"Season {self.season_number} のデータがありません",
                inline=False
            )
            return embed
        
        # ランキング表示
        rank_text = ""
        for i, row in enumerate(data):
            rank = (page * self.items_per_page) + i + 1
            
            guild_name, guild_prefix, rating, season_number, updated_at = row
            # メダル絵文字
            medal = ""
            if rank == 1:
                medal = "🥇 "
            elif rank == 2:
                medal = "🥈 "
            elif rank == 3:
                medal = "🥉 "
            
            rank_text += f"{medal}**#{rank}** `[{guild_prefix}]` {guild_name}\n"
            rank_text += f"　　📊 **{rating:,}** SR\n\n"
        
        embed.add_field(
            name=f"ランキング ({(page * self.items_per_page) + 1}-{min((page + 1) * self.items_per_page, total_items)}位)",
            value=rank_text or "データがありません",
            inline=False
        )
        
        return embed
    
    async def update_embed(self, interaction: discord.Interaction):
        """Embedを更新"""
        try:
            data, total_items = await self.get_leaderboard_data(self.current_page)
            self.data = data
            self.total_items = total_items
            
            # 総ページ数を計算
            total_pages = min(
                math.ceil(total_items / self.items_per_page) if total_items > 0 else 1,
                self.max_pages
            )
            
            # ボタンの状態を更新
            self.previous_button.disabled = self.current_page == 0
            self.next_button.disabled = (
                self.current_page >= total_pages - 1 or 
                self.current_page >= self.max_pages - 1
            )
            
            embed = self.create_leaderboard_embed(
                data, self.current_page, total_pages, total_items
            )
            
            await interaction.response.edit_message(embed=embed, view=self)
            
        except Exception as e:
            logger.error(f"Seasonal Rating Embed更新エラー: {e}", exc_info=True)
            error_embed = create_embed(
                title="❌ エラー",
                description="データの取得中にエラーが発生しました",
                color=discord.Color.red()
            )
            await interaction.response.edit_message(embed=error_embed, view=None)
    
    @discord.ui.button(label="◀️ 前のページ", style=discord.ButtonStyle.secondary)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page > 0:
            self.current_page -= 1
            await self.update_embed(interaction)
    
    @discord.ui.button(label="▶️ 次のページ", style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page += 1
        await self.update_embed(interaction)
    
    @discord.ui.button(label="🔄 更新", style=discord.ButtonStyle.primary)
    async def refresh_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.update_embed(interaction)
    
    async def on_timeout(self):
        """タイムアウト時の処理"""
        for item in self.children:
            item.disabled = True

class LeaderboardCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        logger.info("[LeaderboardCog] ロードされました")
    
    # leaderboard コマンドグループの作成
    leaderboard_group = app_commands.Group(
        name="leaderboard", 
        description="各種リーダーボードを表示します"
    )
    
    @leaderboard_group.command(
        name="sr",
        description="Seasonal Ratingのリーダーボードを表示します"
    )
    @app_commands.describe(
        season="表示するシーズン番号（空白で最新シーズン）"
    )
    async def seasonal_rating_leaderboard(
        self, 
        interaction: discord.Interaction, 
        season: int = None
    ):
        """Seasonal Ratingリーダーボードを表示"""
        try:
            # 権限確認（試験段階のため）
            if interaction.user.id not in AUTHORIZED_USER_IDS:
                await send_authorized_only_message(interaction)
                return
            
            await interaction.response.defer()
            
            # 利用可能なシーズンを取得
            available_seasons = get_available_seasons()
            if not available_seasons:
                info_embed = create_embed(
                    title="ℹ️ データなし",
                    description="まだデータが同期されていません。\n定期同期を待つか、管理者にお問い合わせください。",
                    color=discord.Color.blue()
                )
                await interaction.followup.send(embed=info_embed)
                return
            
            # シーズン指定の処理
            if season is None:
                # 最新シーズンを使用
                season_number = available_seasons[0]
                logger.info(f"最新シーズン {season_number} を自動選択")
            else:
                season_number = season
                if season_number not in available_seasons:
                    # 指定シーズンが存在しない場合
                    seasons_text = "、".join([f"S{s}" for s in available_seasons[:5]])
                    if len(available_seasons) > 5:
                        seasons_text += f"... 他{len(available_seasons)-5}シーズン"
                    
                    error_embed = create_embed(
                        title="❌ シーズンが見つかりません",
                        description=f"Season {season_number} のデータがありません。\n\n**利用可能なシーズン:**\n{seasons_text}",
                        color=discord.Color.red()
                    )
                    await interaction.followup.send(embed=error_embed)
                    return
            
            # リーダーボードViewを作成
            view = SeasonalRatingView(season_number=season_number)
            
            # 初期データを取得
            data, total_items = await view.get_leaderboard_data(0)
            
            if total_items == 0:
                # 該当シーズンにデータがない
                info_embed = create_embed(
                    title=f"ℹ️ Season {season_number} データなし",
                    description=f"Season {season_number} のデータがまだ同期されていません。",
                    color=discord.Color.blue()
                )
                await interaction.followup.send(embed=info_embed)
                return
            
            # 初期Embedを作成
            view.data = data
            view.total_items = total_items
            
            total_pages = min(
                math.ceil(total_items / view.items_per_page),
                view.max_pages
            )
            
            # ボタンの状態を初期化
            view.previous_button.disabled = True
            view.next_button.disabled = total_pages <= 1
            
            embed = view.create_leaderboard_embed(data, 0, total_pages, total_items)
            
            await interaction.followup.send(embed=embed, view=view)
            
        except Exception as e:
            logger.error(f"Seasonal Ratingコマンドエラー: {e}", exc_info=True)
            error_embed = create_embed(
                title="❌ エラー",
                description="リーダーボードの表示中にエラーが発生しました",
                color=discord.Color.red()
            )
            
            if interaction.response.is_done():
                await interaction.followup.send(embed=error_embed)
            else:
                await interaction.response.send_message(embed=error_embed)

async def setup(bot):
    await bot.add_cog(LeaderboardCog(bot))