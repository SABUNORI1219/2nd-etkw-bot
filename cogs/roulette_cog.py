import discord
from discord import app_commands
from discord.ext import commands
import random
import logging
import asyncio

from lib.roulette_renderer import RouletteRenderer

logger = logging.getLogger(__name__)

class RouletteCog(commands.Cog):
    """
    ルーレット機能：軽量化・ランダム性強化・静止画対応
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.renderer = RouletteRenderer()
        logger.info(f"--- [Cog] {self.__class__.__name__} が読み込まれました。")

    @app_commands.checks.cooldown(1, 20.0)
    @app_commands.command(name="roulette", description="ルーレットを回してランダムに一つを当選")
    @app_commands.describe(
        title="ルーレットのタイトル",
        options="候補をスペースで区切って入力(候補は10文字以内、6個以内で入力)"
    )
    async def roulette(self, interaction: discord.Interaction, title: str, options: str):
        await interaction.response.defer()

        candidate_list = options.split()
        if len(candidate_list) < 2:
            await interaction.followup.send("候補は2つ以上指定してください。")
            return
        if len(candidate_list) > 6:
            await interaction.followup.send("候補は6個以下にしてください。")
            return
        for candidate in candidate_list:
            if len(candidate) > 10:
                await interaction.followup.send(f"候補「{candidate}」が長すぎます。各候補は10文字以内にしてください。")
                return

        # --- ランダム性強化 ---
        # サーバー時刻, ユーザーID, 乱数などをseedに
        seed = int(interaction.user.id) ^ int(asyncio.get_event_loop().time() * 1000) ^ random.randint(0, 999999)
        random.seed(seed)
        winner = random.choice(candidate_list)
        winner_index = candidate_list.index(winner)
        logger.info(f"ルーレット実行: {title}, 候補: {candidate_list}, 当選: {winner}")

        # GIF生成（軽量化・乱数強化）
        gif_buffer, animation_duration = self.renderer.create_roulette_gif(candidate_list, winner_index)
        if gif_buffer:
            gif_file = discord.File(fp=gif_buffer, filename="roulette.gif")
            embed = discord.Embed(
                title=(title),
                description="ルーレットを回しています...",
                color=discord.Color.light_gray()
            )
            embed.set_image(url="attachment://roulette.gif")
            embed.set_footer(text=f"ルーレット | Minister Chikuwa")
            message = await interaction.followup.send(embed=embed, file=gif_file)

            # 回転アニメーション待機
            await asyncio.sleep(animation_duration + 0.5)

            # 結果静止画像生成
            result_buffer = self.renderer.create_result_image(candidate_list, winner_index)
            result_file = discord.File(fp=result_buffer, filename="roulette_result.png")

            result_embed = discord.Embed(
                title=title,
                description=f"🎉 **{winner}** が選ばれました！",
                color=discord.Color.gold(),
            )
            result_embed.set_image(url="attachment://roulette_result.png")
            result_embed.set_footer(text=f"ルーレット | Minister Chikuwa")
            await message.edit(embed=result_embed, attachments=[result_file])
        else:
            await interaction.followup.send("GIF画像の生成に失敗しました。もう一度コマンドをお試しください。")

async def setup(bot: commands.Bot):
    await bot.add_cog(RouletteCog(bot))
