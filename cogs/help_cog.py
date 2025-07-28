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

        embed.add_field(
            name="👤 プレイヤー・ギルド情報",
            value="`/player <name>`: プレイヤーの詳細情報を表示します。\n"
                  "`/guild <prefix/name>`: ギルドの詳細情報を表示します。",
            inline=False # このフィールドは横幅をすべて使う
        )

        embed.add_field(
            name="🗺️ テリトリー関連",
            value="`/territory map [guild]`: テリトリーマップを生成します。HQの位置はあくまで推定です。\n"
                  "`/territory status <territory>`: テリトリーのステータスを表示します。",
            inline=False
        )

        embed.add_field(
            name="👹 Guild Raid関連",
            value="`/graid channel <channel>`: Guild Raidをトラックするチャンネルを設定します。（制作者のみ指定可能）\n"
                  "`/graid list <raid_name> [date]`: Guild Raidのクリア履歴を表示します。日付ソートはYYYY-MM-DD形式で入力してください。\n"
                  "`/graid count <player> <raid_name> <count>`: プレイヤーのGuild Raidのクリア回数を補正します。",
            inline=False
        )
        
        embed.add_field(
            name="🎲 その他",
            value="`/roulette <title> <options>`: ルーレットを回します。\n"
                  "各候補は10文字以内で入力、候補数は6つまでです。",
            inline=False
        )

        embed.set_footer(text="ヘルプメニュー | Minister Chikuwa")

        # ephemeral=True にすることで、コマンドを実行した本人にしか見えないメッセージになる
        await interaction.response.send_message(embed=embed, ephemeral=True)

# BotにCogを登録するためのセットアップ関数
async def setup(bot: commands.Bot):
    await bot.add_cog(HelpCog(bot))
