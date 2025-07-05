import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime

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

    def _create_online_players_table(self, members: list) -> tuple[str, int]:
        """オンラインプレイヤーのリストからASCIIテーブルと人数を生成する"""
        online_players = []
        rank_map = {
            "OWNER": "*****", "CHIEF": "****", "STRATEGIST": "***",
            "CAPTAIN": "**", "RECRUITER": "*", "RECRUIT": ""
        }
        for member_data in members:
            if isinstance(member_data, dict) and member_data.get('online'):
                online_players.append({
                    "name": member_data.get("name", "N/A"),
                    "server": member_data.get("server", "N/A"),
                    "rank_stars": rank_map.get(member_data.get("rank", "").upper(), "")
                })
        
        if not online_players:
            return "（現在オンラインのメンバーはいません）", 0

        max_name_len = max(len(p['name']) for p in online_players) if online_players else 6
        max_server_len = max(len(p['server']) for p in online_players) if online_players else 2
        
        header = f"║ {'WC'.center(max_server_len)} ║ {'Player'.ljust(max_name_len)} ║ Rank  ║"
        divider = f"╠═{'═'*max_server_len}═╬═{'═'*max_name_len}═╬═══════╣"
        top_border = f"╔═{'═'*max_server_len}═╦═{'═'*max_name_len}═╦═══════╗"
        bottom_border = f"╚═{'═'*max_server_len}═╩═{'═'*max_name_len}═╩═══════╝"

        player_rows = []
        for p in sorted(online_players, key=lambda x: x['name']): # 名前順にソート
            server = p['server'].center(max_server_len)
            name = p['name'].ljust(max_name_len)
            rank = p['rank_stars'].ljust(5)
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
        prefix = self._safe_get(data, ['prefix'])
        owner = self._safe_get(data, ['owner', 'name'])
        created_date = self._safe_get(data, ['created'], "N/A").split("T")[0]
        level = self._safe_get(data, ['level'], 0)
        xp_percent = self._safe_get(data, ['xp'], 0)
        wars = self._safe_get(data, ['wars'], 0)
        territories = self._safe_get(data, ['territories'], 0)
        
        season_ranks = self._safe_get(data, ['seasonRanks'], {})
        latest_season = str(max([int(k) for k in season_ranks.keys()])) if season_ranks else "N/A"
        rating = self._safe_get(season_ranks, [latest_season, 'rating'], "N/A")
        rating_display = f"{rating:,}" if isinstance(rating, int) else rating
        
        # メンバーのリストと総数を、それぞれ正しいキーから取得
        member_list = self._safe_get(data, ['members'], [])
        total_members = self._safe_get(data, ['totalMembers'], len(member_list)) # totalMembersキーを優先
        online_players_table, online_count = self._create_online_players_table(member_list)
        
        # 埋め込みメッセージを作成
        description = f"""
    [公式サイトへのリンク](https://wynncraft.com/stats/guild/{prefix})
Owner: {owner}
Created on: {created_date}
Level: {level} [{xp_percent}%]
War count: {wars}
Rating: {rating_display} [Season {latest_season}]
Territory count: {territories}
Members: {total_members}
Online Players: {online_count}/{total_members}
{online_players_table}

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
        
        embed.set_footer(text=f"Data from Nori API | Requested by {interaction.user.display_name}")

        await interaction.followup.send(embed=embed)

# BotにCogを登録するためのセットアップ関数
async def setup(bot: commands.Bot):
    await bot.add_cog(GuildCog(bot))
