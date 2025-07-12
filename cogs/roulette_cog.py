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

    # ▼▼▼【コマンドの定義を修正】▼▼▼
    @app_commands.command(name="roulette", description="ルーレットを回してランダムに一つを選びます。")
    @app_commands.describe(
        options="候補をスペースで区切って入力してください。"
    )
    async def roulette(self, interaction: discord.Interaction, options: str):
        await interaction.response.defer()

        # 1. 受け取った文字列をスペースで分割し、候補リストを作成
        candidate_list = options.split()

        if len(candidate_list) < 2:
            await interaction.followup.send("候補は2つ以上指定してください。")
            return
        
        # Discordの選択肢の最大数である25個に制限する
        if len(candidate_list) > 25:
            await interaction.followup.send("候補が多すぎます！25個以下にしてください。")
            return

        # 2. 当選者をランダムに決定
        winner = random.choice(candidate_list)
        winner_index = candidate_list.index(winner)
        
        logger.info(f"ルーレットを実行します。候補: {candidate_list}, 当選者: {winner}")

        # 3. 描画担当者にGIFの生成を依頼
        gif_buffer = self.renderer.create_roulette_gif(candidate_list, winner_index)

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
    # ▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲

# BotにCogを登録するためのセットアップ関数
async def setup(bot: commands.Bot):
    await bot.add_cog(RouletteCog(bot))
