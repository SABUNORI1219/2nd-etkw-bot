import discord
from discord import app_commands
from discord.ext import commands
import random
import logging
from typing import Optional

# libフォルダから専門家をインポート
from lib.roulette_renderer import RouletteRenderer

logger = logging.getLogger(__name__)

class RouletteCog(commands.Cog):
    """
    ルーレット機能に関するスラッシュコマンドを担当するCog。
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.renderer = RouletteRenderer() # ルーレット描画担当者のインスタンスを作成
        logger.info(f"--- [Cog] {self.__class__.__name__} が読み込まれました。")

    @app_commands.command(name="roulette", description="ルーレットを回してランダムに一つを選びます。")
    @app_commands.describe(
        option1="候補1",
        option2="候補2",
        option3="候補3 (任意)",
        option4="候補4 (任意)",
        option5="候補5 (任意)",
        option6="候補6 (任意)",
        option7="候補7 (任意)",
        option8="候補8 (任意)",
    )
    async def roulette(
        self, 
        interaction: discord.Interaction, 
        option1: str, 
        option2: str,
        option3: Optional[str] = None,
        option4: Optional[str] = None,
        option5: Optional[str] = None,
        option6: Optional[str] = None,
        option7: Optional[str] = None,
        option8: Optional[str] = None,
    ):
        """ユーザーが入力した候補でルーレットを回すコマンド"""
        await interaction.response.defer()

        # 1. ユーザーが入力した候補をリストにまとめる
        options = [opt for opt in [option1, option2, option3, option4, option5, option6, option7, option8] if opt is not None]

        if len(options) < 2:
            await interaction.followup.send("候補は2つ以上指定してください。")
            return

        # 2. 当選者をランダムに決定
        winner = random.choice(options)
        winner_index = options.index(winner)
        
        logger.info(f"ルーレットを実行します。候補: {options}, 当選者: {winner}")

        # 3. 描画担当者にGIFの生成を依頼
        gif_buffer = self.renderer.create_roulette_gif(options, winner_index)

        # 4. 生成されたGIFを送信
        if gif_buffer:
            gif_file = discord.File(fp=gif_buffer, filename="roulette.gif")
            
            embed = discord.Embed(
                title="ルーレットの結果！",
                description=f"🎉 **{winner}** が選ばれました！",
                color=discord.Color.gold()
            )
            embed.set_image(url="attachment://roulette.gif")
            
            await interaction.followup.send(embed=embed, file=gif_file)
        else:
            await interaction.followup.send("エラー：GIF画像の生成に失敗しました。")

# BotにCogを登録するためのセットアップ関数
async def setup(bot: commands.Bot):
    await bot.add_cog(RouletteCog(bot))
