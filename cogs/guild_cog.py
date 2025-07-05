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

    def _create_online_players_table(self, online_players_list: list) -> tuple[str, int]:
        """オンラインプレイヤーのリストからASCIIテーブルと人数を生成する"""
        
        # ▼▼▼【ロジック修正箇所】APIからのonline_playersリストを直接使う▼▼▼
        if not online_players_list:
            return "（現在オンラインのメンバーはいません）", 0

        # 各列の最大幅を計算
        max_name_len = max(len(p.get('name', 'N/A')) for p in online_players_list)
        max_server_len = max(len(p.get('server', 'N/A')) for p in online_players_list)
        max_rank_len = max(len(p.get('rank', 'N/A')) for p in online_players_list)
        
        header = f"║ {'WC'.center(max_server_len)} ║ {'Player'.center(max_name_len)} ║ {'Rank'.center(max_rank_len)} ║"
        divider = f"╠═{'═'*max_server_len}═╬═{'═'*max_name_len}═╬═{'═'*max_rank_len}═╣"
        top_border = f"╔═{'═'*max_server_len}═╦═{'═'*max_name_len}═╦═{'═'*max_rank_len}═╗"
        bottom_border = f"╚═{'═'*max_server_len}═╩═{'═'*max_name_len}═╩═{'═'*max_rank_len}═╝"

        # 各プレイヤーの行を作成
        player_rows = []
        # ▼▼▼【修正箇所】rank（星）の文字数で降順（多い順）にソートする▼▼▼
        for p in sorted(online_players_list, key=lambda x: len(x.get('rank', '')), reverse=True):
            server = p.get('server', 'N/A').center(max_server_len)
            name = p.get('name', 'N/A').center(max_name_len)
            rank = p.get('rank', '').ljust(max_rank_len)
            player_rows.append(f"║ {server} ║ {name} ║ {rank} ║")

        return "\n".join([top_border, header, divider] + player_rows + [bottom_border]), len(online_players_list)

    @app_commands.command(name="guild", description="ギルドのステータスを表示します。")
    @app_commands.describe(guild="Name or Prefix")
    async def guild(self, interaction: discord.Interaction, guild: str):
        await interaction.response.defer()

        data = await self.wynn_api.get_nori_guild_data(guild)

        if not data or 'name' not in data:
            await interaction.followup.send(f"ギルド「{guild}」が見つかりませんでした。")
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
        online_players_list = self._safe_get(data, ['online_players'], []) # online_playersリストを直接取得
        online_players_table, online_count = self._create_online_players_table(online_players_list)
        # ▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲
        
        # 埋め込みメッセージを作成
        description = f"""
    [公式サイトへのリンク](https://wynncraft.com/stats/guild/{encoded_name})
```
Owner: {owner}
Created on: {created_date}
Level: {level} [{xp_percent}%]
War count: {wars}
Rating: {rating_display} [Season{latest_season}]
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
        
        embed.title = [prefix] name
        
        embed.set_footer(text=f"{name}'s Stats | Minister Chikuwa")

        await interaction.followup.send(embed=embed)

# BotにCogを登録するためのセットアップ関数
async def setup(bot: commands.Bot):
    await bot.add_cog(GuildCog(bot))
