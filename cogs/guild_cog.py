import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime
from urllib.parse import quote

# libフォルダから専門家をインポート
from lib.wynncraft_api import WynncraftAPI
# configから設定をインポート
from config import EMBED_COLOR_BLUE # 色は好みに合わせて変更できます

class GuildCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.wynn_api = WynncraftAPI()
        print("--- [CommandsCog] ギルドコマンドCogが読み込まれました。")

    def _safe_get(self, data: dict, keys: list, default: any = "N/A"):
        """辞書から安全に値を取得するヘルパー関数"""
        for key in keys:
            if not isinstance(data, dict):
                return default
            data = data.get(key)
        return data if data is not None else default

    def _create_online_players_table(self, online_players_dict: dict) -> tuple[str, int]:
        """オンラインプレイヤーの辞書からASCIIテーブルと人数を生成する"""
        
        # ▼▼▼【ロジック修正箇所】辞書から直接データを読み込む▼▼▼
        if not online_players_dict or not isinstance(online_players_dict, dict):
            return "（現在オンラインのメンバーはいません）", 0

        online_players = list(online_players_dict.values())
        # ▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲

        # 各列の最大幅を計算して、テーブルの見た目を整える
        max_name_len = max(len(p.get('name', 'N/A')) for p in online_players) if online_players else 6
        max_server_len = max(len(p.get('server', 'N/A')) for p in online_players) if online_players else 2
        max_rank_len = max(len(p.get('rank', 'N/A')) for p in online_players) if online_players else 4
        
        header = f"║ {'WC'.center(max_server_len)} ║ {'Player'.ljust(max_name_len)} ║ {'Rank'.center(max_rank_len)} ║"
        divider = f"╠═{'═'*max_server_len}═╬═{'═'*max_name_len}═╬═{'═'*max_rank_len}═╣"
        top_border = f"╔═{'═'*max_server_len}═╦═{'═'*max_name_len}═╦═{'═'*max_rank_len}═╗"
        bottom_border = f"╚═{'═'*max_server_len}═╩═{'═'*max_name_len}═╩═{'═'*max_rank_len}═╝"

        # 各プレイヤーの行を作成
        player_rows = []
        for p in sorted(online_players, key=lambda x: x.get('name', '')): # 名前順にソート
            server = p.get('server', 'N/A').center(max_server_len)
            name = p.get('name', 'N/A').ljust(max_name_len)
            rank = p.get('rank', 'N/A').center(max_rank_len) # rankは星ではなくテキストと仮定
            player_rows.append(f"║ {server} ║ {name} ║ {rank} ║")

        return "\n".join([top_border, header, divider] + player_rows + [bottom_border]), len(online_players)

    @app_commands.command(name="guild", description="ギルドの詳細情報を表示します。")
    @app_commands.describe(guild_name="ギルド名またはギルドプレフィックス")
    async def guild(self, interaction: discord.Interaction, guild_name: str):
        await interaction.response.defer()

        data = await self.wynn_api.get_nori_guild_data(guild_name)

        if not data or 'name' not in data:
            await interaction.followup.send(f"ギルド「{guild_name}」が見つかりませんでした。")
            return

        # データを正しいAPIキーで取得
        name = self._safe_get(data, ['name'])
        encoded_name = quote(name)
        prefix = self._safe_get(data, ['prefix'])
        owner = self._safe_get(data, ['owner'])
        created_date = self._safe_get(data, ['created_date'])
        level = self._safe_get(data, ['level'], 0)
        xp_percent = self._safe_get(data, ['xp_percent'], 0)
        wars = self._safe_get(data, ['wars'], 0)
        territories = self._safe_get(data, ['territories'], 0)
        
        season_ranks = self._safe_get(data, ['seasonRanks'], {})
        latest_season = str(max([int(k) for k in season_ranks.keys()])) if season_ranks else "N/A"
        rating = self._safe_get(season_ranks, [latest_season, 'rating'], "N/A")
        rating_display = f"{rating:,}" if isinstance(rating, int) else rating
        
        # ▼▼▼【ロジック修正箇所】正しいデータソースを参照する▼▼▼
        total_members = self._safe_get(data, ['total_members'], 0)
        online_players_dict = self._safe_get(data, ['online_players'], {}) # online_players辞書を取得
        online_players_table, online_count = self._create_online_players_table(online_players_dict)
        # ▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲
        
        # 埋め込みメッセージを作成
        description = f"""
    [公式サイトへのリンク](https://wynncraft.com/stats/guild/{encoded_name})
```
Owner: {owner}
Created on: {created_date}
Level: {level} [{xp_percent}%]
War count: {wars}
Rating: {rating_display} [Season {latest_season}]
Territory count: {territories}
Members: {total_members}
Online Players: {online_count}/{total_members}
{online_players_table}
```
"""
        embed = discord.Embed(
            description=description,
            color=EMBED_COLOR_BLUE
        )

        banner_path = self._safe_get(data, ['banner', 'tierImage'], None)
        icon_url = f"https://cdn.wynncraft.com/{banner_path}" if banner_path else None
        
        embed.set_author(
            name=f"{name} [{prefix}]",
            url=f"https://wynncraft.com/stats/guild/{name.replace(' ', '%20')}",
            icon_url=icon_url
        )
        
        embed.set_footer(text=f"{name}'s Stats | Minister Chikuwa")

        await interaction.followup.send(embed=embed)

# BotにCogを登録するためのセットアップ関数
async def setup(bot: commands.Bot):
    await bot.add_cog(GuildCog(bot))
