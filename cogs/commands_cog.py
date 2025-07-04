import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timezone, timedelta

# libフォルダから専門家たちをインポート
from lib.wynncraft_api import WynncraftAPI
from lib.database_handler import get_raid_counts
# configから設定をインポート
from config import RAID_TYPES, EMBED_COLOR_BLUE, EMBED_COLOR_GREEN

class PlayerSelectView(discord.ui.View):
    def __init__(self, player_options: list, cog_instance):
        super().__init__(timeout=60.0)  # 60秒で操作不能になる
        self.cog_instance = cog_instance # commands_cogのインスタンスを保持

        # ドロップダウンメニューの選択肢を作成
        options = [
            discord.SelectOption(label=p['storedName'], value=p['uuid'])
            for p in player_options
        ]
        
        # ドロップダウンメニューを作成
        self.select_menu = discord.ui.Select(placeholder="プレイヤーを選択してください...", options=options)
        self.select_menu.callback = self.select_callback # コールバック関数を登録
        self.add_item(self.select_menu)

    async def select_callback(self, interaction: discord.Interaction):
        # ユーザーが選択肢を選ぶと、この関数が実行される
        selected_uuid = self.select_menu.values[0] # 選択されたUUIDを取得
        
        # ドロップダウンを無効化し、「考え中...」を表示
        self.select_menu.disabled = True
        await interaction.response.edit_message(view=self)
        
        # UUIDを使って再度APIから詳細データを取得
        # Nori APIはUUIDでも検索できる
        data = await self.cog_instance.wynn_api.get_nori_player_data(selected_uuid)
        
        if not data or 'uuid' not in data:
            await interaction.followup.send("選択されたプレイヤーの情報を取得できませんでした。")
            return
            
        # 取得したデータから埋め込みメッセージを作成
        embed = self.cog_instance._create_player_embed(data)
        
        # 元のメッセージを、完成した埋め込みに置き換える
        await interaction.message.edit(content=None, embed=embed, view=None)

class GameCommandsCog(commands.Cog):
    """
    プレイヤーが直接実行するゲーム関連のスラッシュコマンドを担当するCog。
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.wynn_api = WynncraftAPI()
        print("--- [CommandsCog] ゲームコマンドCogが読み込まれました。")

    # 指定されたデータを安全に取得するためのヘルパー関数
    def _safe_get(self, data: dict, keys: list, default: any = "N/A"):
        for key in keys:
            if not isinstance(data, dict):
                return default
            data = data.get(key)
        return data if data is not None else default

    def _create_player_embed(self, data: dict) -> discord.Embed:
        username = self._safe_get(data, ['username'])
        uuid = self._safe_get(data, ['uuid'])
        support_rank = self._safe_get(data, ['supportRank'], "Player").capitalize()
        is_online = self._safe_get(data, ['online'], False)
        server = self._safe_get(data, ['server'], "Unknown")
        
        # ▼▼▼【修正点3】ギルドの星を[]で囲む ▼▼▼
        guild_name = self._safe_get(data, ['guild', 'name'], "N/A")
        guild_prefix = self._safe_get(data, ['guild', 'prefix'], "")
        guild_rank = self._safe_get(data, ['guild', 'rank'], "")
        guild_rank_stars = self._safe_get(data, ['guild', 'rankStars'], "")
        guild_display = f"[{guild_prefix}] {guild_name} / {guild_rank}[{guild_rank_stars}]" if guild_name != "N/A" else "N/A"

        first_join = self._safe_get(data, ['firstJoin'], "N/A").split('T')[0]
        
        # ▼▼▼【修正点4】Streamの表示ロジックを修正 ▼▼▼
        last_join_str = self._safe_get(data, ['lastJoin'], "1970-01-01T00:00:00.000Z")
        last_join_dt = datetime.fromisoformat(last_join_str.replace('Z', '+00:00'))
        time_diff = datetime.now(timezone.utc) - last_join_dt
        # オフラインかつ最終ログインが3秒以内の場合
        stream_status = "🟢Stream" if not is_online and time_diff.total_seconds() < 3 else "❌Stream"
        last_join_display = f"{last_join_str.split('T')[0]} [{stream_status}]"
        
        # ▼▼▼【ここから3点の修正を反映】▼▼▼
        # 1. activeCharacterの取得パスを修正
        active_char_uuid = self._safe_get(data, ['activeCharacter'])
        
        # 2. 'N/A'チェックを削除し、常にキーが存在する前提で処理
        char_obj = self._safe_get(data, ['characters', active_char_uuid], {})
        char_type = self._safe_get(char_obj, ['type'])
        nickname = self._safe_get(char_obj, ['nickname'])
        reskin = self._safe_get(char_obj, ['reskin'])

        # 3. reskinの有無で表示を分岐させるロジックに変更
        if reskin != "N/A":
            active_char_info = f"{reskin} ({nickname}) on {server}"
        else:
            active_char_info = f"{char_type} ({nickname}) on {server}"
        # ▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲

        killed_mobs = self._safe_get(data, ['globalData', 'killedMobs'], 0)
        chests_found = self._safe_get(data, ['globalData', 'chestsFound'], 0)
        playtime = self._safe_get(data, ['playtime'], 0)
        wars = self._safe_get(data, ['globalData', 'wars'], 0)
        war_rank = self._safe_get(data, ['ranking', 'warsCompletion'], 'N/A')
        pvp_kills = self._safe_get(data, ['globalData', 'pvp', 'kills'], 0)
        pvp_deaths = self._safe_get(data, ['globalData', 'pvp', 'deaths'], 0)
        quests = self._safe_get(data, ['globalData', 'completedQuests'], 0)
        total_level = self._safe_get(data, ['globalData', 'totalLevel'], 0)

        raid_list = self._safe_get(data, ['globalData', 'raids', 'list'], {})
        notg = self._safe_get(raid_list, ["Nest of the Grootslangs"], 0)
        nol = self._safe_get(raid_list, ["Orphion's Nexus of Light"], 0)
        tcc = self._safe_get(raid_list, ["The Canyon Colossus"], 0)
        tna = self._safe_get(raid_list, ["The Nameless Anomaly"], 0)
        dungeons = self._safe_get(data, ['globalData', 'dungeons', 'total'], 0)
        total_raids = self._safe_get(data, ['globalData', 'raids', 'total'], 0)

        # ▼▼▼【修正点2】UUID以降をコードブロックで囲む ▼▼▼
        description = f"""
[公式サイトへのリンク](https://wynncraft.com/stats/player/{username})
```
[{support_rank}] {username} is {'online' if is_online else 'offline'}
Active Character: {active_char_info}
Guild: {guild_display}
First Joined: {first_join}
Last Seen: {last_join_display}
Mobs Killed: {killed_mobs:,}
Chests Looted: {chests_found:,}
Playtime: {playtime:,} hours
War Count: {wars:,} [#{war_rank:,}]
PvP: {pvp_kills:,} K / {pvp_deaths:,} D
Quests Total: {quests:,}
Total Level: {total_level:,}
╔═══════════╦════════╗
║  Content  ║ Clears ║
╠═══════════╬════════╣
║ NOTG      ║ {notg:>6,} ║
║ NOL       ║ {nol:>6,} ║
║ TCC       ║ {tcc:>6,} ║
║ TNA       ║ {tna:>6,} ║
║ Dungeons  ║ {dungeons:>6,} ║
║ All Raids ║ {total_raids:>6,} ║
╚═══════════╩════════╝
```
**UUID: {uuid}**
"""
    color = discord.Color.green() if is_online else discord.Color.dark_red()
        embed = discord.Embed(
            description=description,
            color=color
        )
        # ▼▼▼【修正点1】公式ウェブサイトへのリンクを設定 ▼▼▼
        embed.title = username
        
        embed.set_thumbnail(url=f"https://www.mc-heads.net/body/{username}/right")
        
        embed.set_footer(
            text=f"{username}'s Stats | Minister Chikuwa",
            icon_url=f"https://www.mc-heads.net/avatar/{username}"
        )

        return Embed

    @app_commands.command(name="player", description="Nori APIからプレイヤーの詳細情報を表示します。")
    @app_commands.describe(player_name="Minecraftのプレイヤー名")
    async def player(self, interaction: discord.Interaction, player_name: str):
        await interaction.response.defer()

        data = await self.wynn_api.get_nori_player_data(player_name)

        if not data or 'uuid' not in data:
            await interaction.followup.send(f"プレイヤー「{player_name}」が見つかりませんでした。")
            return
        if isinstance(data, list):
            # 衝突した場合、ドロップダウンメニューを表示
            view = PlayerSelectView(player_options=data, cog_instance=self)
            await interaction.followup.send("複数のプレイヤーが見つかりました。どちらのプレイヤーの情報を表示しますか？", view=view)
        elif isinstance(data, dict) and 'uuid' in data:
            # 衝突しなかった場合、通常通り埋め込みを作成して送信
            embed = self._create_player_embed(data)
            await interaction.followup.send(embed=embed)
        else:
            # 予期せぬデータ形式の場合
            await interaction.followup.send(f"プレイヤー「{player_name}」の情報を正しく取得できませんでした。")

# BotにCogを登録するためのセットアップ関数
async def setup(bot: commands.Bot):
    await bot.add_cog(GameCommandsCog(bot))
