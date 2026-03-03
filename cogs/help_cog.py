import discord
from discord import app_commands
from discord.ext import commands
import logging

from lib.utils import create_embed

logger = logging.getLogger(__name__)


class HelpSelectMenu(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(
                label="プレイヤー・ギルド情報",
                description="プレイヤーやギルドの情報を表示するコマンド",
                emoji="👤",
                value="player_guild"
            ),
            discord.SelectOption(
                label="テリトリー関連",
                description="テリトリーマップやステータスの確認",
                emoji="🗺️",
                value="territory"
            ),
            discord.SelectOption(
                label="その他・ユーティリティ",
                description="ルーレットなどのその他機能",
                emoji="🎲",
                value="utility"
            ),
            discord.SelectOption(
                label="メニューに戻る",
                description="ヘルプメニューのトップに戻る",
                emoji="🔙",
                value="main_menu"
            )
        ]
        super().__init__(placeholder="カテゴリを選択してください...", options=options)

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "main_menu":
            embed = create_embed(
                title="💡 ヘルプメニュー",
                description="このBotで利用できるコマンドのカテゴリです。\n下のメニューから詳細を確認したいカテゴリを選択してください。",
                color=discord.Color.blurple(),
                footer_text="ヘルプメニュー | Onyx"
            )
        elif self.values[0] == "player_guild":
            embed = create_embed(
                title="👤 プレイヤー・ギルド情報",
                description="プレイヤーやギルドの情報を表示するコマンド群です。",
                color=discord.Color.green(),
                footer_text="引数: <> = 必須, [] = 任意 | Onyx"
            )
            embed.add_field(
                name="/player <name>",
                value="指定したプレイヤーの詳細情報を表示します。\n• レベル、ギルド、統計情報等\n• プロファイルカード形式で表示",
                inline=False
            )
            embed.add_field(
                name="/guild <prefix/name>",
                value="指定したギルドの詳細情報を表示します。\n• メンバー数、レベル、テリトリー数\n• ギルドバナー形式で表示\n• プレフィックスまたはギルド名で検索可能",
                inline=False
            )
        elif self.values[0] == "territory":
            embed = create_embed(
                title="🗺️ テリトリー関連",
                description="テリトリーマップやステータスの確認に関するコマンド群です。",
                color=discord.Color.purple(),
                footer_text="引数: <> = 必須, [] = 任意 | Onyx"
            )
            embed.add_field(
                name="/territory map [guild]",
                value="テリトリーマップを生成します。\n• guild指定で特定ギルドをハイライト\n• 全テリトリーの保持状況を色分け表示\n• 保持時間も表示",
                inline=False
            )
            embed.add_field(
                name="/territory status <territory>",
                value="指定したテリトリーの詳細ステータスを表示します。\n• 保持ギルド、リソース情報\n• 保持開始時間、経過時間",
                inline=False
            )
        elif self.values[0] == "utility":
            embed = create_embed(
                title="🎲 その他・ユーティリティ",
                description="ルーレットなどのその他機能に関するコマンド群です。",
                color=discord.Color.orange(),
                footer_text="引数: <> = 必須, [] = 任意 | Onyx"
            )
            embed.add_field(
                name="/roulette <title> <options>",
                value="ルーレットを回します。\n• 各候補は10文字以内\n• 最大8つまでの候補\n• ランダムに1つを当選",
                inline=False
            )
            embed.add_field(
                name="/help",
                value="このヘルプメニューを表示します。\n• カテゴリ別の詳細説明\n• DMでも使用可能",
                inline=False
            )

        await interaction.response.edit_message(embed=embed, view=HelpView())


class HelpView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)  # 5分でタイムアウト
        self.add_item(HelpSelectMenu())

    async def on_timeout(self):
        # タイムアウト時にボタンを無効化
        for item in self.children:
            item.disabled = True

class HelpCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        logger.info(f"--- [Cog] {self.__class__.__name__} が読み込まれました。")

    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.checks.cooldown(1, 5.0, key=lambda i: i.user.id)
    @app_commands.command(name="help", description="Botのコマンド一覧を表示")
    async def help(self, interaction: discord.Interaction):
        embed = create_embed(
            title="💡 ヘルプメニュー",
            description="このBotで利用できるコマンドのカテゴリです。\n下のメニューから詳細を確認したいカテゴリを選択してください。",
            color=discord.Color.blurple(),
            footer_text="ヘルプメニュー | Onyx"
        )

        view = HelpView()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

# セットアップ関数
async def setup(bot: commands.Bot):
    await bot.add_cog(HelpCog(bot))
