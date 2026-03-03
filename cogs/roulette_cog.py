import discord
from discord import app_commands
from discord.ext import commands
import random
import logging
import asyncio

from lib.roulette_renderer import RouletteRenderer
from lib.utils import create_embed

logger = logging.getLogger(__name__)

class RouletteCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.renderer = RouletteRenderer()
        self.system_name = "ルーレット"
        logger.info(f"--- [Cog] {self.__class__.__name__} が読み込まれました。")

    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.checks.cooldown(1, 20.0)
    @app_commands.command(name="roulette", description="ルーレットを回してランダムに一つを当選")
    @app_commands.describe(
        title="ルーレットのタイトル",
        options="候補をスペース区切りで入力（各候補10文字以内、最大8個まで）"
    )
    async def roulette(self, interaction: discord.Interaction, title: str, options: str):
        await interaction.response.defer()

        candidate_list = options.split()
        random.shuffle(candidate_list)

        if len(candidate_list) < 2:
            embed = create_embed(description="候補は2つ以上指定してください。", title="🔴 エラーが発生しました", color=discord.Color.red(), footer_text=f"{self.system_name} | Onyx")
            await interaction.followup.send(embed=embed)
            return
        if len(candidate_list) > 8:
            embed = create_embed(description="候補は最大8個までにしてください。", title="🔴 エラーが発生しました", color=discord.Color.red(), footer_text=f"{self.system_name} | Onyx")
            await interaction.followup.send(embed=embed)
            return
        for candidate in candidate_list:
            if len(candidate) > 10:
                embed = create_embed(description=f"候補「{candidate}」が長すぎます。\n各候補は10文字以内にしてください。", title="🔴 エラーが発生しました", color=discord.Color.red(), footer_text=f"{self.system_name} | Onyx")
                await interaction.followup.send(embed=embed)
                return

        seed = int(interaction.user.id) ^ int(asyncio.get_event_loop().time() * 1000) ^ random.randint(0, 999999)
        random.seed(seed)
        winner = random.choice(candidate_list)
        winner_index = candidate_list.index(winner)
        logger.info(f"ルーレット実行: {title}, 候補: {candidate_list}, 当選: {winner}")

        # GIF生成
        gif_buffer, animation_duration = self.renderer.create_roulette_gif(candidate_list, winner_index)
        if gif_buffer:
            gif_file = discord.File(fp=gif_buffer, filename="roulette.gif")
            embed = discord.Embed(
                title=(title),
                description="ルーレットを回しています...",
                color=discord.Color.light_gray()
            )
            embed.set_image(url="attachment://roulette.gif")
            embed.set_footer(text=f"ルーレット | Onyx")
            message = await interaction.followup.send(embed=embed, file=gif_file)

            gif_buffer.close()
            gif_file.close()
            del gif_buffer, gif_file, embed

            await asyncio.sleep(animation_duration + 0.5)

            result_buffer = self.renderer.create_result_image(candidate_list, winner_index)
            result_file = discord.File(fp=result_buffer, filename="roulette_result.png")

            result_embed = discord.Embed(
                title=title,
                description=f"🎉 **{winner}** が選ばれました！",
                color=discord.Color.gold(),
            )
            result_embed.set_image(url="attachment://roulette_result.png")
            result_embed.set_footer(text=f"ルーレット | Onyx")
            await message.edit(embed=result_embed, attachments=[result_file])

            result_buffer.close()
            result_file.close()
            del result_buffer, result_file, result_embed
        else:
            embed = create_embed(description="GIF画像の生成に失敗しました。\nもう一度コマンドをお試しください。", title="🔴 エラーが発生しました", color=discord.Color.red(), footer_text=f"{self.system_name} | Onyx")
            await interaction.followup.send(embed=embed)
            del embed

async def setup(bot: commands.Bot):
    await bot.add_cog(RouletteCog(bot))
