import discord
from discord.ext import tasks, commands
import aiohttp
import asyncio
from datetime import datetime, timezone
import uuid

from database import add_raid_records

GUILD_API_URL = "https://nori.fish/api/guild/Empire%20of%20TKW"
PLAYER_API_URL = "https://api.wynncraft.com/v3/player/{}"
RAID_TYPES = ["tna", "tcc", "nol", "nog"]

class RaidTracker(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.previous_raid_counts = {}
        self.raid_check_loop.start()

    def cog_unload(self):
        self.raid_check_loop.cancel()

    @tasks.loop(minutes=1.5)
    async def raid_check_loop(self):
        print(f"[{datetime.now()}] ➡️ レイド数のチェックを開始...")
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(GUILD_API_URL) as response:
                    if response.status != 200:
                        print(f"❌ ギルドAPIエラー: {response.status}")
                        return
                    guild_data = await response.json()
            except Exception as e:
                print(f"❌ ギルドAPIリクエスト中にエラー: {e}")
                return

            all_members_data = guild_data.get("members", [])
            if not all_members_data:
                print("⚠️ ギルドメンバーが見つかりませんでした。")
                return

            # ▼▼▼【エラー修正箇所】▼▼▼
            online_member_info = {m['uuid']: m['server'] for m in all_members_data if isinstance(m, dict) and m.get('online')}
            all_member_uuids = [m['uuid'] for m in all_members_data if isinstance(m, dict)]
            # ▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲

            current_raid_counts = {}
            tasks = [self.fetch_player_raids(session, uuid) for uuid in all_member_uuids]
            player_raid_data_list = await asyncio.gather(*tasks)

            for player_data in player_raid_data_list:
                if player_data:
                    current_raid_counts[player_data['uuid']] = player_data['raids']

            if not self.previous_raid_counts:
                print("初回実行のため、現在のレイド数を保存して終了します。")
                self.previous_raid_counts = current_raid_counts
                return

            changed_players = self.find_changed_players(current_raid_counts)
            if not changed_players:
                self.previous_raid_counts = current_raid_counts
                return

            print(f"🔥 レイド数が増加したプレイヤー: {changed_players}")
            raid_parties = self.identify_parties(changed_players, online_member_info)

            if raid_parties:
                print(f"🎉 パーティを特定しました: {raid_parties}")
                await self.record_and_notify(raid_parties)

            self.previous_raid_counts = current_raid_counts

    async def fetch_player_raids(self, session, player_uuid):
        if not player_uuid: return None
        try:
            formatted_uuid = player_uuid.replace('-', '')
            async with session.get(PLAYER_API_URL.format(formatted_uuid)) as response:
                if response.status == 200:
                    player_data = await response.json()
                    raids = player_data.get("guild", {}).get("raids", {})
                    raid_counts = {raid: raids.get(raid, 0) for raid in RAID_TYPES}
                    return {'uuid': player_uuid, 'raids': raid_counts}
                return None
        except Exception:
            return None

    def find_changed_players(self, current_counts):
        changed_players = {}
        for player_uuid, current_raids in current_counts.items():
            if player_uuid in self.previous_raid_counts:
                previous_raids = self.previous_raid_counts[player_uuid]
                for raid_type in RAID_TYPES:
                    if current_raids.get(raid_type, 0) > previous_raids.get(raid_type, 0):
                        if raid_type not in changed_players: changed_players[raid_type] = []
                        changed_players[raid_type].append(player_uuid)
        return changed_players

    def identify_parties(self, changed_players, online_info):
        parties = []
        for raid_type, players in changed_players.items():
            worlds = {}
            for player_uuid in players:
                if player_uuid in online_info:
                    world = online_info[player_uuid]
                    if world not in worlds: worlds[world] = []
                    worlds[world].append(player_uuid)
            
            for world, world_players in worlds.items():
                if len(world_players) == 4:
                    parties.append({'raid_type': raid_type, 'players': world_players})
        return parties

    async def record_and_notify(self, raid_parties):
        channel_id = int(os.getenv('NOTIFICATION_CHANNEL_ID', 0))
        channel = self.bot.get_channel(channel_id)
        if not channel:
            print(f"⚠️ 通知チャンネル(ID: {channel_id})が見つかりません。")
            return
            
        for party in raid_parties:
            group_id = str(uuid.uuid4())
            cleared_at = datetime.now(timezone.utc)
            db_records = []
            # ここではプレイヤーのUUIDから名前を取得する処理が必要ですが、今回はUUIDをそのまま表示します
            player_display_names = [p_uuid.replace('-', '') for p_uuid in party['players']]
            
            for player_uuid in party['players']:
                # 本来はUUIDからDiscord IDを引く必要がありますが、今回は0として保存します
                db_records.append((group_id, 0, player_uuid, party['raid_type'], cleared_at))

            add_raid_records(db_records)

            embed = discord.Embed(
                title=f"🎉 ギルドレイドクリア！ [{party['raid_type'].upper()}]",
                description="以下のメンバーがクリアしました！",
                color=discord.Color.gold(),
                timestamp=cleared_at
            )
            embed.add_field(name="メンバー", value="\n".join(player_display_names), inline=False)
            await channel.send(embed=embed)

    @raid_check_loop.before_loop
    async def before_raid_check_loop(self):
        await self.bot.wait_until_ready()
        print("👍 RaidTracker: ループを開始します。")

async def setup(bot):
    await bot.add_cog(RaidTracker(bot))
