import discord
from discord.ext import tasks, commands
import aiohttp
import asyncio
from datetime import datetime, timezone
import uuid

# 他のファイルから必要なものをインポート
from models import Player, Guild
from config import GUILD_API_URL, PLAYER_API_URL, RAID_TYPES, EMBED_COLOR_GOLD
from database import add_raid_records

print("--- [raid_tracker.py] ファイルが読み込まれました ---")

class RaidTracker(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        print("--- [RaidTracker Cog] 1. __init__ メソッドが開始されました ---")
        self.previous_players_state = {} # {player_uuid: Player_Object}
        self.player_name_cache = {}
        print("--- [RaidTracker Cog] 2. ループの開始を試みます... ---")
        self.raid_check_loop.start()
        print("--- [RaidTracker Cog] 3. ループの開始命令が完了しました ---")

    def cog_unload(self):
        self.raid_check_loop.cancel()

    # 診断しやすいようにループ間隔を1分に変更
    @tasks.loop(minutes=1.0)
    async def raid_check_loop(self):
        log_prefix = f"[{datetime.now().strftime('%H:%M:%S')}]"
        print(f"{log_prefix} ➡️➡️➡️ ループ処理が実行されました！ ⬅️⬅️⬅️")
        
        async with aiohttp.ClientSession() as session:
            # (以下、実際の処理ロジック)
            try:
                async with session.get(GUILD_API_URL) as response:
                    if response.status != 200:
                        print(f"{log_prefix} ❌ ギルドAPIエラー: {response.status}")
                        return
                    guild = Guild(await response.json())
            except Exception as e:
                print(f"{log_prefix} ❌ ギルドAPIリクエスト中にエラー: {e}")
                return

            member_uuids = guild.get_all_member_uuids()
            tasks = [self.fetch_player_data(session, uuid) for uuid in member_uuids]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            current_players_state = {}
            for res in results:
                if isinstance(res, Player):
                    current_players_state[res.uuid] = res
            
            if not self.previous_players_state:
                print(f"{log_prefix} ✅ 初回実行のため、{len(current_players_state)} 人の現在の状態を保存します。")
                self.previous_players_state = current_players_state
                return

            changed_players = self.find_changed_players(current_players_state)
            if not changed_players:
                print(f"{log_prefix} 変化はありませんでした。")
            else:
                print(f"{log_prefix} 🔥 レイド数が増加したプレイヤーを検出: {changed_players}")
                online_info = guild.get_online_members_info()
                raid_parties = self.identify_parties(changed_players, online_info)
                if raid_parties:
                    print(f"{log_prefix} 🎉 パーティを特定しました: {raid_parties}")
                    await self.record_and_notify(raid_parties)

            self.previous_players_state = current_players_state

    # (fetch_player_data, find_changed_players, identify_parties, record_and_notify は変更なし)
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
        changed_players = {}
        for uuid, current_player in current_state.items():
            if uuid in self.previous_players_state:
                previous_player = self.previous_players_state[uuid]
                for raid_type in RAID_TYPES:
                    if current_player.get_raid_count(raid_type) > previous_player.get_raid_count(raid_type):
                        if raid_type not in changed_players: changed_players[raid_type] = []
                        changed_players[raid_type].append(uuid)
        return changed_players

    def identify_parties(self, changed_players, online_info):
        parties = []
        for raid_type, player_uuids in changed_players.items():
            worlds = {}
            for uuid in player_uuids:
                if uuid in online_info:
                    world = online_info[uuid]['server']
                    if world not in worlds: worlds[world] = []
                    worlds[world].append(uuid)
            for world_players in worlds.values():
                if len(world_players) == 4:
                    parties.append({'raid_type': raid_type, 'players': world_players})
        return parties

    async def record_and_notify(self, raid_parties):
        channel_id = int(os.getenv('NOTIFICATION_CHANNEL_ID', 0))
        channel = self.bot.get_channel(channel_id)
        if not channel: return
        for party in raid_parties:
            group_id = str(uuid.uuid4())
            cleared_at = datetime.now(timezone.utc)
            db_records = [(group_id, 0, uuid, party['raid_type'], cleared_at) for uuid in party['players']]
            add_raid_records(db_records)
            player_names = [self.player_name_cache.get(uuid, "Unknown") for uuid in party['players']]
            embed = discord.Embed(
                title=f"🎉 ギルドレイドクリア！ [{party['raid_type'].upper()}]",
                description="以下のメンバーがクリアしました！",
                color=EMBED_COLOR_GOLD,
                timestamp=cleared_at
            )
            embed.add_field(name="メンバー", value="\n".join(player_names), inline=False)
            await channel.send(embed=embed)


    @raid_check_loop.before_loop
    async def before_raid_check_loop(self):
        print("--- [RaidTracker Cog] 4. before_loop - Botの準備完了を待機します... ---")
        await self.bot.wait_until_ready()
        print("--- [RaidTracker Cog] 5. before_loop - Botの準備が完了しました！ループを開始できます。 ---")

async def setup(bot):
    print("--- [raid_tracker.py] setup関数が呼び出されました ---")
    await bot.add_cog(RaidTracker(bot))
