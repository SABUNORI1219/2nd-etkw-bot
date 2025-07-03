# =================================================================================
# main.py - 全機能統合版
# =================================================================================

import discord
from discord import app_commands
from discord.ext import tasks, commands
import os
import asyncio
import sys
import psycopg2
from datetime import datetime, timezone, timedelta
from flask import Flask
from threading import Thread
import aiohttp
import uuid

# =================================================================================
# 以前の config.py の内容
# =================================================================================
print("--- [Config] 設定値を読み込みます ---")
GUILD_NAME = "Empire of TKW"
GUILD_API_URL = f"https://nori.fish/api/guild/{GUILD_NAME.replace(' ', '%20')}"
PLAYER_API_URL = "https://api.wynncraft.com/v3/player/{}"
RAID_TYPES = ["tna", "tcc", "nol", "nog"]
EMBED_COLOR_GOLD = 0xFFD700
EMBED_COLOR_GREEN = 0x00FF00
EMBED_COLOR_BLUE = 0x0000FF
GUILD_ID_INT = int(os.getenv('GUILD_ID', 0))
TOKEN = os.getenv('DISCORD_TOKEN')
DATABASE_URL = os.getenv('DATABASE_URL')
NOTIFICATION_CHANNEL_ID = int(os.getenv('NOTIFICATION_CHANNEL_ID', 0))
print("--- [Config] 設定値の読み込み完了 ---")

# =================================================================================
# 以前の keep_alive.py の内容
# =================================================================================
print("--- [KeepAlive] Webサーバーの準備 ---")
app = Flask('')
@app.route('/')
def home():
    return "I'm alive"
def run_flask():
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
def keep_alive():
    server_thread = Thread(target=run_flask)
    server_thread.start()
    print("--- [KeepAlive] Webサーバーのスレッドを開始しました ---")

# =================================================================================
# 以前の database.py の内容
# =================================================================================
print("--- [Database] データベース関数の準備 ---")
def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

def setup_database():
    print("--- [Database] データベースのセットアップを開始... ---")
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS clear_records (
            id SERIAL PRIMARY KEY,
            group_id VARCHAR(255) NOT NULL,
            user_id BIGINT NOT NULL,
            player_uuid VARCHAR(255) NOT NULL,
            raid_type VARCHAR(50) NOT NULL,
            cleared_at TIMESTAMP NOT NULL DEFAULT current_timestamp
        );
    """)
    conn.commit()
    cur.close()
    conn.close()
    print("--- [Database] データベースのセットアップ完了 ---")

def add_raid_records(records):
    conn = get_db_connection()
    cur = conn.cursor()
    sql = "INSERT INTO clear_records (group_id, user_id, player_uuid, raid_type, cleared_at) VALUES (%s, %s, %s, %s, %s)"
    cur.executemany(sql, records)
    conn.commit()
    cur.close()
    conn.close()

def get_raid_counts(player_uuid, since_date):
    conn = get_db_connection()
    cur = conn.cursor()
    sql = "SELECT raid_type, COUNT(*) FROM clear_records WHERE player_uuid = %s AND cleared_at >= %s GROUP BY raid_type"
    cur.execute(sql, (player_uuid, since_date))
    results = cur.fetchall()
    cur.close()
    conn.close()
    return results

# =================================================================================
# 以前の models.py の内容
# =================================================================================
print("--- [Models] データモデルクラスの準備 ---")
class Player:
    def __init__(self, uuid, api_data):
        self.uuid = uuid
        self.data = api_data
    @property
    def username(self) -> str: return self.data.get('username', 'Unknown')
    def get_raid_count(self, raid_name: str) -> int:
        raids_dict = self.data.get("guild", {}).get("raids", {})
        return raids_dict.get(raid_name, 0)

class Guild:
    def __init__(self, api_data):
        self.data = api_data
    def get_all_member_uuids(self) -> list:
        return [m['uuid'] for m in self.data.get("members", []) if isinstance(m, dict) and 'uuid' in m]
    def get_online_members_info(self) -> dict:
        return {m['uuid']: {'server': m.get('server')} for m in self.data.get("members", []) if isinstance(m, dict) and m.get('online')}

# =================================================================================
# 以前の cogs/raid_tracker.py の内容 (クラスとして定義)
# =================================================================================
print("--- [Cog] RaidTrackerクラスの準備 ---")
class RaidTracker(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.previous_players_state = {}
        self.player_name_cache = {}
        self.raid_check_loop.start()

    def cog_unload(self):
        self.raid_check_loop.cancel()

    @tasks.loop(minutes=1.5)
    async def raid_check_loop(self):
        log_prefix = f"[{datetime.now().strftime('%H:%M:%S')}]"
        print(f"{log_prefix} ➡️ レイド数のチェックを開始...")
        try:
            async with aiohttp.ClientSession() as session:
                guild_data = await self.fetch_guild_data(session)
                if not guild_data: return

                guild = Guild(guild_data)
                member_uuids = guild.get_all_member_uuids()
                
                tasks = [self.fetch_player_data(session, uuid) for uuid in member_uuids]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                current_players_state = {player.uuid: player for res in results if isinstance(res, Player) and (player := res)}

                if not self.previous_players_state:
                    print(f"{log_prefix} ✅ 初回実行のため、{len(current_players_state)} 人の現在の状態を保存します。")
                    self.previous_players_state = current_players_state
                    return

                changed_players = self.find_changed_players(current_players_state)
                if changed_players:
                    print(f"{log_prefix} 🔥 レイド数が増加したプレイヤーを検出: {changed_players}")
                    online_info = guild.get_online_members_info()
                    raid_parties = self.identify_parties(changed_players, online_info)
                    if raid_parties:
                        print(f"{log_prefix} 🎉 パーティを特定しました: {raid_parties}")
                        await self.record_and_notify(raid_parties)

                self.previous_players_state = current_players_state
        except Exception as e:
            print(f"{log_prefix} ❌ ループ処理の内部で予期せぬエラーが発生しました: {e}")

    @raid_check_loop.before_loop
    async def before_raid_check_loop(self):
        await self.bot.wait_until_ready()
        print("--- [RaidTracker] 待機完了: ループを開始します。 ---")

    async def fetch_guild_data(self, session):
        try:
            async with session.get(GUILD_API_URL) as response:
                if response.status == 200: return await response.json()
                print(f"❌ ギルドAPIエラー: {response.status}")
                return None
        except Exception as e:
            print(f"❌ ギルドAPIリクエスト中にエラー: {e}")
            return None

    async def fetch_player_data(self, session, player_uuid):
        if not player_uuid: return None
        try:
            formatted_uuid = player_uuid.replace('-', '')
            async with session.get(PLAYER_API_URL.format(formatted_uuid)) as response:
                if response.status == 200:
                    data = await response.json()
                    self.player_name_cache[player_uuid] = data.get('username', 'Unknown')
                    return Player(player_uuid, data)
                return None
        except Exception as e:
            return e

    def find_changed_players(self, current_state):
        changed = {}
        for uuid, current in current_state.items():
            if uuid in self.previous_players_state:
                prev = self.previous_players_state[uuid]
                for r_type in RAID_TYPES:
                    if current.get_raid_count(r_type) > prev.get_raid_count(r_type):
                        if r_type not in changed: changed[r_type] = []
                        changed[r_type].append(uuid)
        return changed

    def identify_parties(self, changed, online):
        parties = []
        for r_type, uuids in changed.items():
            worlds = {}
            for uuid in uuids:
                if uuid in online:
                    world = online[uuid]['server']
                    if world not in worlds: worlds[world] = []
                    worlds[world].append(uuid)
            for w_players in worlds.values():
                if len(w_players) == 4: parties.append({'raid_type': r_type, 'players': w_players})
        return parties

    async def record_and_notify(self, parties):
        channel = self.bot.get_channel(NOTIFICATION_CHANNEL_ID)
        if not channel: return
        for party in parties:
            group_id, cleared_at = str(uuid.uuid4()), datetime.now(timezone.utc)
            records = [(group_id, 0, uuid, party['raid_type'], cleared_at) for uuid in party['players']]
            add_raid_records(records)
            names = [self.player_name_cache.get(uuid, "Unknown") for uuid in party['players']]
            embed = discord.Embed(title=f"🎉 ギルドレイドクリア！ [{party['raid_type'].upper()}]", description="以下のメンバーがクリアしました！", color=EMBED_COLOR_GOLD, timestamp=cleared_at)
            embed.add_field(name="メンバー", value="\n".join(names), inline=False)
            await channel.send(embed=embed)

# =================================================================================
# 以前の cogs/game_commands.py の内容 (クラスとして定義)
# =================================================================================
print("--- [Cog] GameCommandsクラスの準備 ---")
class GameCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def get_uuid_from_name(self, player_name: str):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(PLAYER_API_URL.format(player_name)) as response:
                    if response.status == 200: return (await response.json()).get('uuid')
                    return None
        except Exception: return None

    @app_commands.command(name="graidcount", description="指定プレイヤーのレイドクリア回数を集計します。")
    @app_commands.describe(player_name="Minecraftのプレイヤー名", since="集計開始日 (YYYY-MM-DD形式)")
    async def raid_count(self, interaction: discord.Interaction, player_name: str, since: str = None):
        await interaction.response.defer()
        since_date = datetime.now() - timedelta(days=30)
        if since:
            try: since_date = datetime.strptime(since, "%Y-%m-%d")
            except ValueError:
                await interaction.followup.send("日付の形式が正しくありません。`YYYY-MM-DD`形式で入力してください。"); return
        
        player_uuid = await self.get_uuid_from_name(player_name)
        if not player_uuid:
            await interaction.followup.send(f"プレイヤー「{player_name}」が見つかりませんでした。"); return

        records = get_raid_counts(player_uuid, since_date)
        embed = discord.Embed(title=f"{player_name}のレイドクリア回数", description=f"{since_date.strftime('%Y年%m月%d日')}以降の記録", color=EMBED_COLOR_BLUE)
        if not records: embed.description += "\n\nクリア記録はありませんでした。"
        else:
            total = sum(rec[1] for rec in records)
            for r_type, count in records: embed.add_field(name=r_type.upper(), value=f"{count} 回", inline=True)
            embed.set_footer(text=f"合計: {total} 回")
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="raidaddmanual", description="レイドクリア記録を手動で追加します。(MCID指定)")
    @app_commands.checks.has_any_role("Admin", "Officer")
    @app_commands.choices(raid_type=[app_commands.Choice(name=n.upper(), value=n) for n in RAID_TYPES])
    @app_commands.describe(raid_type="レイドの種類を選択", player1="プレイヤー1のMCID", player2="プレイヤー2のMCID", player3="プレイヤー3のMCID", player4="プレイヤー4のMCID")
    async def raid_add_manual(self, interaction: discord.Interaction, raid_type: app_commands.Choice[str], player1: str, player2: str, player3: str, player4: str):
        await interaction.response.defer()
        names = [player1, player2, player3, player4]
        uuids = await asyncio.gather(*[self.get_uuid_from_name(name) for name in names])
        not_found = [names[i] for i, u in enumerate(uuids) if not u]
        if not_found:
            await interaction.followup.send(f"以下のプレイヤーが見つかりませんでした: {', '.join(not_found)}"); return
        
        group_id, cleared_at = f"manual-{uuid.uuid4()}", datetime.now(timezone.utc)
        records = [(group_id, 0, u, raid_type.value, cleared_at) for u in uuids]
        add_raid_records(records)

        embed = discord.Embed(title=f"📝 手動で記録追加 [{raid_type.name}]", description="以下のメンバーのクリア記録が手動で追加されました。", color=EMBED_COLOR_GREEN, timestamp=cleared_at)
        embed.add_field(name="メンバー", value="\n".join(names), inline=False)
        embed.set_footer(text=f"実行者: {interaction.user.display_name}")
        await interaction.followup.send(embed=embed)

    @raid_add_manual.error
    async def on_raid_add_manual_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingAnyRole):
            if not interaction.response.is_done(): await interaction.response.send_message("このコマンドを実行する権限がありません。", ephemeral=True)
        else:
            if not interaction.response.is_done(): await interaction.response.send_message(f"エラーが発生しました: {error}", ephemeral=True)

# =================================================================================
# Botのメインクラスと起動処理
# =================================================================================
intents = discord.Intents.default()
intents.message_content = True
intents.members = True 
intents.presences = True

class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix='!', intents=intents)

    async def setup_hook(self):
        print("--- [Bot] setup_hook: 準備処理を開始します ---")
        setup_database()
        keep_alive()
        await self.add_cog(RaidTracker(self))
        print("--- [Bot] ✅ Cog 'RaidTracker' を登録しました。 ---")
        await self.add_cog(GameCommands(self))
        print("--- [Bot] ✅ Cog 'GameCommands' を登録しました。 ---")

    async def on_ready(self):
        print("==================================================")
        print(f"ログイン成功: {self.user} (ID: {self.user.id})")
        print("Botは正常に起動し、準備が完了しました。")
        print("==================================================")

bot = MyBot()

@bot.command()
@commands.is_owner()
async def sync(ctx):
    if GUILD_ID_INT == 0:
        await ctx.send("エラー: GUILD_IDが環境変数に設定されていません。")
        return
    guild = discord.Object(id=GUILD_ID_INT)
    try:
        ctx.bot.tree.copy_global_to(guild=guild)
        synced = await ctx.bot.tree.sync(guild=guild)
        await ctx.send(f"{len(synced)}個のコマンドをサーバーに同期しました。")
    except Exception as e:
        await ctx.send(f"コマンドの同期に失敗しました: {e}")

if __name__ == '__main__':
    try:
        print("--- Botの起動を開始します ---")
        bot.run(TOKEN)
    except discord.errors.LoginFailure:
        print("致命的エラー: 不正なトークンです。Renderの環境変数 'DISCORD_TOKEN' を確認してください。")
    except Exception as e:
        print(f"Botの起動中に予期せぬエラーが発生しました: {e}")
