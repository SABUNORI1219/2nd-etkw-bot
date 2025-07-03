import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timedelta

# libフォルダから専門家たちをインポート
from lib.wynncraft_api import WynncraftAPI
from lib.database_handler import get_raid_counts
# configから設定をインポート
from config import RAID_TYPES

class GameCommandsCog(commands.Cog):
    """
    プレイヤーが直接実行するゲーム関連のスラッシュコマンドを担当するCog。
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.wynn_api = WynncraftAPI()
        print("--- [CommandsCog] ゲームコマンドCogが読み込まれました。")

    @app_commands.command(name="graidcount", description="プレイヤーのレイドクリア回数を集計します。")
    @app_commands.describe(
        player_name="Minecraftのプレイヤー名",
        since="集計開始日 (例: 2024-01-01)"
    )
    async def raid_count(self, interaction: discord.Interaction, player_name: str, since: str = None):
        """指定されたプレイヤーのレイドクリア回数を表示するコマンド"""
        await interaction.response.defer(ephemeral=True) # 他の人に見えないように考え中...

        # 日付が指定されていない場合は、過去30日間に設定
        if since:
            try:
                since_date = datetime.strptime(since, "%Y-%m-%d")
            except ValueError:
                await interaction.followup.send("日付の形式が正しくありません。`YYYY-MM-DD`の形式で入力してください。")
                return
        else:
            since_date = datetime.now() - timedelta(days=30)

        # 1. API担当に、プレイヤー名からUUIDの取得を依頼
        player_uuid = await self.wynn_api.get_uuid_from_name(player_name)
        if not player_uuid:
            await interaction.followup.send(f"プレイヤー「{player_name}」が見つかりませんでした。")
            return

        # 2. データベース担当に、レイドクリア回数の取得を依頼
        raid_counts = get_raid_counts(player_uuid, since_date)

        # 3. 結果を整形してユーザーに返信
        embed = discord.Embed(
            title=f"{player_name} のレイドクリア回数",
            description=f"{since_date.strftime('%Y年%m月%d日')} 以降の記録",
            color=discord.Color.blue()
        )

        if not raid_counts:
            embed.description += "\n\nクリア記録はありません。"
        else:
            total_clears = 0
            for raid_type, count in raid_counts:
                embed.add_field(name=raid_type, value=f"{count} 回", inline=True)
                total_clears += count
            embed.set_footer(text=f"合計クリア回数: {total_clears} 回")

        await interaction.followup.send(embed=embed)

    # 他のコマンドも必要に応じてこのクラスに追加していきます。
    # 例えば、/guildinfo や /itemsearch など。

# BotにCogを登録するためのセットアップ関数
async def setup(bot: commands.Bot):
    await bot.add_cog(GameCommandsCog(bot))
