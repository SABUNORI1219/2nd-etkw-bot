# =================================================================================
# main.py - 全機能統合・最終安定版
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

# --- CONFIG ---
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

# --- KEEP ALIVE SERVER ---
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

# --- DATABASE ---
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

# --- MODELS ---
print("--- [Models] データモデルクラスの準備 ---")
class Player:
    def __init__(self, uuid, api_data):
        self.uuid, self.data = uuid, api_data
    @property
    def username(self) -> str: return self.data.get('username', 'Unknown')
    def get_raid_count(self, name: str) -> int: return self.data.get("guild",{}).get("raids",{}).get(name, 0)

class Guild:
    def __init__(self, api_data): self.data = api_data
    def get_all_member_uuids(self) -> list: return [m['uuid'] for m in self.data.get("members",[]) if isinstance(m, dict) and 'uuid' in m]
    def get_online_members_info(self) -> dict: return {m['uuid']:{'server':m.get('server')} for m in self.data.get("members",[]) if isinstance(m,dict) and m.get('online')}

# --- COGS ---
print("--- [Cog] RaidTrackerクラスの準備 ---")
class RaidTracker(commands.Cog):
    def __init__(self, bot):
        self.bot, self.previous_players_state, self.player_name_cache = bot, {}, {}
        self.raid_check_loop.start()
    def cog_unload(self): self.raid_check_loop.cancel()
    @tasks.loop(minutes=1.5)
    async def raid_check_loop(self):
        log_prefix = f"[{datetime.now().strftime('%H:%M:%S')}]"
        print(f"{log_prefix} ➡️ レイドチェック開始...")
        try:
            async with aiohttp.ClientSession() as s:
                guild_data=await self.fetch_guild_data(s)
                if not guild_data: return
                guild=Guild(guild_data)
                tasks=[self.fetch_player_data(s,uuid) for uuid in guild.get_all_member_uuids()]
                current_players_state={p.uuid: p for r in await asyncio.gather(*tasks,return_exceptions=True) if isinstance(r,Player) and (p:=r)}
                if not self.previous_players_state:
                    print(f"{log_prefix} ✅ 初回実行のため、{len(current_players_state)}人の状態を保存。")
                    self.previous_players_state=current_players_state; return
                changed=self.find_changed_players(current_players_state)
                if changed:
                    print(f"{log_prefix} 🔥 変化を検出: {changed}")
                    parties=self.identify_parties(changed,guild.get_online_members_info())
                    if parties: print(f"{log_prefix} 🎉 パーティ特定: {parties}"); await self.record_and_notify(parties)
                self.previous_players_state=current_players_state
        except Exception as e: print(f"{log_prefix} ❌ ループ内部エラー: {e}")
    @raid_check_loop.before_loop
    async def before_raid_check_loop(self): await self.bot.wait_until_ready(); print("--- [RaidTracker] 待機完了: ループを開始します。 ---")
    async def fetch_guild_data(self,s):
        try:
            async with s.get(GUILD_API_URL) as r:
                if r.status==200: return await r.json()
                print(f"❌ ギルドAPIエラー: {r.status}"); return None
        except Exception as e: print(f"❌ ギルドAPIリクエストエラー: {e}"); return None
    async def fetch_player_data(self,s,uuid):
        if not uuid: return None
        try:
            async with s.get(PLAYER_API_URL.format(uuid.replace('-',''))) as r:
                if r.status==200:
                    d=await r.json(); self.player_name_cache[uuid]=d.get('username','N/A'); return Player(uuid,d)
                return None
        except Exception as e: return e
    def find_changed_players(self,current):
        changed={}; [changed.setdefault(r,[]).append(u) for u,c in current.items() if u in self.previous_players_state for r in RAID_TYPES if c.get_raid_count(r)>self.previous_players_state[u].get_raid_count(r)]; return changed
    def identify_parties(self,changed,online):
        parties=[]; [parties.append({'raid_type':r,'players':w_p}) for r,u in changed.items() for w,w_p in (lambda d: (d.update({online[uuid]['server']:d.get(online[uuid]['server'],[])+[uuid] for uuid in u if uuid in online}),d)[1])({}).items() if len(w_p)==4]; return parties
    async def record_and_notify(self,parties):
        ch=self.bot.get_channel(NOTIFICATION_CHANNEL_ID)
        if not ch: return
        for p in parties:
            gid,cat=str(uuid.uuid4()),datetime.now(timezone.utc); add_raid_records([(gid,0,u,p['raid_type'],cat) for u in p['players']])
            names=[self.player_name_cache.get(u,"?") for u in p['players']]
            e=discord.Embed(title=f"🎉 ギルドレイドクリア！ [{p['raid_type'].upper()}]",description="以下のメンバーがクリアしました！",color=EMBED_COLOR_GOLD,timestamp=cat); e.add_field(name="メンバー",value="\n".join(names),inline=False); await ch.send(embed=e)

print("--- [Cog] GameCommandsクラスの準備 ---")
class GameCommands(commands.Cog):
    def __init__(self, bot: commands.Bot): self.bot=bot
    async def get_uuid_from_name(self,name:str):
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(PLAYER_API_URL.format(name)) as r: return (await r.json()).get('uuid') if r.status==200 else None
        except Exception: return None
    @app_commands.command(name="graidcount",description="レイドクリア回数を集計します。")
    @app_commands.describe(player_name="Minecraftのプレイヤー名",since="集計開始日 (YYYY-MM-DD)")
    async def raid_count(self,ix:discord.Interaction,player_name:str,since:str=None):
        await ix.response.defer()
        s_date=datetime.now()-timedelta(days=30)
        if since:
            try: s_date=datetime.strptime(since,"%Y-%m-%d")
            except ValueError: await ix.followup.send("日付形式が不正です。`YYYY-MM-DD`で入力してください。"); return
        uuid=await self.get_uuid_from_name(player_name)
        if not uuid: await ix.followup.send(f"プレイヤー「{player_name}」が見つかりません。"); return
        recs=get_raid_counts(uuid,s_date)
        e=discord.Embed(title=f"{player_name}のレイドクリア回数",description=f"{s_date.strftime('%Y年%m月%d日')}以降の記録",color=EMBED_COLOR_BLUE)
        if not recs: e.description+="\n\nクリア記録はありません。"
        else: e.set_footer(text=f"合計: {sum(r[1] for r in recs)} 回"); [e.add_field(name=r[0].upper(),value=f"{r[1]} 回",inline=True) for r in recs]
        await ix.followup.send(embed=e)
    @app_commands.command(name="raidaddmanual",description="レイド記録を手動追加します。(MCID指定)")
    @app_commands.checks.has_any_role("Admin","Officer")
    @app_commands.choices(raid_type=[app_commands.Choice(name=n.upper(),value=n) for n in RAID_TYPES])
    @app_commands.describe(raid_type="レイドの種類",player1="MCID 1",player2="MCID 2",player3="MCID 3",player4="MCID 4")
    async def raid_add_manual(self,ix:discord.Interaction,raid_type:app_commands.Choice[str],p1:str,p2:str,p3:str,p4:str):
        await ix.response.defer()
        names=[p1,p2,p3,p4]; uuids=await asyncio.gather(*[self.get_uuid_from_name(n) for n in names])
        not_found=[names[i] for i,u in enumerate(uuids) if not u]
        if not_found: await ix.followup.send(f"プレイヤーが見つかりません: {', '.join(not_found)}"); return
        gid,cat=f"manual-{uuid.uuid4()}",datetime.now(timezone.utc); add_raid_records([(gid,0,u,raid_type.value,cat) for u in uuids])
        e=discord.Embed(title=f"📝 手動で記録追加 [{raid_type.name}]",description="クリア記録が手動で追加されました。",color=EMBED_COLOR_GREEN,timestamp=cat)
        e.add_field(name="メンバー",value="\n".join(names),inline=False); e.set_footer(text=f"実行者: {ix.user.display_name}"); await ix.followup.send(embed=e)
    @raid_add_manual.error
    async def on_raid_add_manual_error(self,ix:discord.Interaction,error:app_commands.AppCommandError):
        if not ix.response.is_done(): await ix.response.send_message("権限がありません。" if isinstance(error,app_commands.MissingAnyRole) else f"エラー: {error}",ephemeral=True)

# --- BOTのメインクラスと起動処理 ---
intents = discord.Intents.default(); intents.message_content=True; intents.members=True; intents.presences=True
class MyBot(commands.Bot):
    def __init__(self): super().__init__(command_prefix='!', intents=intents)
    async def setup_hook(self):
        print("--- [Bot] 準備処理を開始します ---")
        setup_database(); keep_alive()
        await self.add_cog(RaidTracker(self)); print("--- [Bot] ✅ Cog 'RaidTracker' を登録しました。 ---")
        await self.add_cog(GameCommands(self)); print("--- [Bot] ✅ Cog 'GameCommands' を登録しました。 ---")
    async def on_ready(self): print(f"=================\nログイン成功: {self.user}\n=================")
bot = MyBot()
@bot.command()
@commands.is_owner()
async def sync(ctx):
    if GUILD_ID_INT==0: await ctx.send("エラー: GUILD_IDが未設定です。"); return
    guild=discord.Object(id=GUILD_ID_INT)
    try:
        ctx.bot.tree.copy_global_to(guild=guild); synced=await ctx.bot.tree.sync(guild=guild)
        await ctx.send(f"{len(synced)}個のコマンドを同期しました。")
    except Exception as e: await ctx.send(f"同期に失敗: {e}")
if __name__ == '__main__':
    try: print("--- Botの起動を開始します ---"); bot.run(TOKEN)
    except Exception as e: print(f"致命的エラー: {e}"); sys.exit(1)
