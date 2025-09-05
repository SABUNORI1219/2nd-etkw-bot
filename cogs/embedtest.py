import discord
from discord.ext import commands
from discord import app_commands
from lib.discord_notify import make_japanese_embed, make_english_embed, send_language_select_embed

class EmbedTestCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="embedtest", description="Embedのテスト送信（リアクション切替も可能）")
    @app_commands.describe(
        lang="japanese / english / both (default: both)",
        dest="送信先: channel（チャンネル）または dm（DM）"
    )
    async def embedtest(
        self,
        interaction: discord.Interaction,
        lang: str = "both",
        dest: str = "channel"
    ):
        """Embedのテスト送信コマンド（DM/チャンネル両対応）"""
        await interaction.response.defer(ephemeral=True)
        # 日本語/英語Embed生成
        if lang.lower() == "japanese":
            embed = make_japanese_embed()
        elif lang.lower() == "english":
            embed = make_english_embed()
        else:
            embed = None  # 両方切替テスト

        # 送信先判定
        if dest.lower() == "dm":
            # DM送信
            try:
                user = interaction.user
                if embed:
                    await user.send(embed=embed)
                else:
                    await send_language_select_embed(user, is_dm=True)
                await interaction.followup.send("DMにテストEmbedを送信しました。", ephemeral=True)
            except Exception as e:
                await interaction.followup.send(f"DM送信失敗: {e}", ephemeral=True)
        else:
            # チャンネル送信
            if embed:
                await interaction.channel.send(embed=embed)
            else:
                await send_language_select_embed(interaction.channel)
            await interaction.followup.send("チャンネルにテストEmbedを送信しました。", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(EmbedTestCog(bot))
