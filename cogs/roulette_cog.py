import discord
from discord import app_commands
from discord.ext import commands
import random
import logging
from typing import Optional
import asyncio

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
        title="ルーレットのタイトル",
        options="候補をスペースで区切って入力(候補は10文字以内で入力)"
    )
    async def roulette(self, interaction: discord.Interaction, title: str, options: str):
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

        for candidate in candidate_list:
            if len(candidate) > 10:
                await interaction.followup.send(f"候補「{candidate}」が長すぎます。各候補は10文字以内にしてください。")
                return

        # 2. 当選者をランダムに決定
        winner = random.choice(candidate_list)
        winner_index = candidate_list.index(winner)
        
        logger.info(f"ルーレットを実行します。タイトル: {title}, 候補: {candidate_list}, 当選者: {winner}")

        # 1. 描画担当者にGIFの生成を依頼（アニメーション時間も受け取る）
        gif_buffer, animation_duration = self.renderer.create_roulette_gif(candidate_list, winner_index)

        if gif_buffer:
            gif_file = discord.File(fp=gif_buffer, filename="roulette.gif")
            
            # 2. まず「回転中」のメッセージとGIFを送信
            embed = discord.Embed(
                title=(title),
                description="ルーレットを回しています...",
                color=discord.Color.light_gray()
            )
            embed.set_image(url="attachment://roulette.gif")
            
            message = await interaction.followup.send(embed=embed, file=gif_file)

            # 3. アニメーション時間分だけ待機
            await asyncio.sleep(animation_duration + 0.5) # 0.5秒の余韻

            # 4. メッセージを編集して結果を発表
            result_embed = discord.Embed(
                title=title,
                description=f"🎉 **{winner}** が選ばれました！",
                color=discord.Color.gold(),
                embed.set_footer(text=f"ルーレット | Minister Chikuwa")
            )
            result_embed.set_image(url="attachment://roulette.gif") # GIFはそのまま表示し続ける
            
            await message.edit(embed=result_embed)
        else:
            await interaction.followup.send("エラー：GIF画像の生成に失敗しました。")

# BotにCogを登録するためのセットアップ関数
async def setup(bot: commands.Bot):
    await bot.add_cog(RouletteCog(bot))
