import discord
from discord import app_commands
from discord.ext import commands
import logging

logger = logging.getLogger(__name__)

class HelpCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        logger.info(f"--- [Cog] {self.__class__.__name__} が読み込まれました。")

    @app_commands.checks.cooldown(1, 5.0, key=lambda i: i.user.id)
    @app_commands.command(name="help", description="Botのコマンド一覧を表示")
    async def help(self, interaction: discord.Interaction):
        # 埋め込みメッセージの器を作成
        embed = discord.Embed(
            title="💡 ヘルプメニュー",
            description="""
            このBotで利用できるコマンドの一覧です。
            引数に<>があるものは必須、[]があるものは任意です。
            """,
            color=discord.Color.blurple() # Discordのブランドカラー
        )

        # カテゴリー1: プレイヤー・ギルド情報
        embed.add_field(
            name="👤 プレイヤー・ギルド情報",
            value="`/player <name>`: プレイヤーの詳細情報を表示します。\n"
                  "`/guild <prefix/name>`: ギルドの詳細情報を表示します。",
            inline=False # このフィールドは横幅をすべて使う
        )

        # カテゴリー2: テリトリー関連
        embed.add_field(
            name="🗺️ テリトリー関連",
            value="`/territory map [guild]`: テリトリーマップを生成します。",
            inline=False
        )
        
        # カテゴリー3: その他
        embed.add_field(
            name="🎲 その他",
            value="`/roulette <title> <options>`: ルーレットを回します。",
            inline=False
        )

        embed.set_footer("ヘルプメニュー | Minister Chikuwa")

        # ephemeral=True にすることで、コマンドを実行した本人にしか見えないメッセージになる
        await interaction.response.send_message(embed=embed, ephemeral=True)

# BotにCogを登録するためのセットアップ関数
async def setup(bot: commands.Bot):
    await bot.add_cog(HelpCog(bot))
