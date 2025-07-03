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

class RaidTracker(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # {player_uuid: Player_Object} の形式で前回の状態を保存
        self.previous_players_state = {}
        self.player_name_cache = {}
        self.raid_check_loop.start()

    def cog_unload(self):
        self.raid_check_loop.cancel()

    @tasks.loop(minutes=1.5)
    async def raid_check_loop(self):
        log_prefix = f"[{datetime.now().strftime('%H:%M:%S')}]"
        print(f"{log_prefix} ➡️ レイド数のチェックを開始...")
        
        async with aiohttp.ClientSession() as session:
            # 1. ギルドデータを取得
            try:
                async with session.get(GUILD_API_URL) as response:
                    if response.status != 200:
                        print(f"{log_prefix} ❌ ギルドAPIエラー: {response.status}")
                        return
                    guild = Guild(await response.json())
            except Exception as e:
                print(f"{log_prefix} ❌ ギルドAPIリクエスト中にエラー: {e}")
                return

            # 2. 全メンバーのプレイヤーデータを並行して取得
            member_uuids = guild.get_all_member_uuids()
            print(f"{log_prefix} ギルドメンバー {len(member_uuids)} 人のデータを取得します...")
            tasks = [self.fetch_player_data(session, uuid) for uuid in member_uuids]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            current_players_state = {}
            for res in results:
                if isinstance(res, Player):
                    current_players_state[res.uuid] = res
                elif res is not None:
                    print(f"{log_prefix} ⚠️ プレイヤーデータ取得中にエラーが発生しました: {res}")

            # 3. 初回実行時は状態を保存して終了
            if not self.previous_players_state:
                print(f"{log_prefix} ✅ 初回実行のため、{len(current_players_state)} 人の現在の状態を保存します。")
                self.previous_players_state = current_players_state
                return

            # 4. 変化を検出
            changed_players = self.find_changed_players(current_players_state)
            if not changed_players:
                print(f"{log_prefix}  zmiany レイド数の変化はありませんでした。")
                self.previous_players_state = current_players_state
                return

            print(f"{log_prefix} 🔥 レイド数が増加したプレイヤーを検出: {changed_players}")

            # 5. オンライン情報を使ってパーティを特定
            online_info = guild.get_online_members_info()
            raid_parties = self.identify_parties(changed_players, online_info)

            if raid_parties:
                print(f"{log_prefix} 🎉 パーティを特定しました: {raid_parties}")
                await self.record_and_notify(raid_parties)
            else:
                print(f"{log_prefix} 🧐 増加は検知しましたが、4人パーティの条件に合致しませんでした。")


            # 6. 今回の状態を次回の比較用に保存
            self.previous_players_state = current_players_state

    async def fetch_player_data(self, session, player_uuid):
        if not player_uuid: return None
        try:
            formatted_uuid = player_uuid.replace('-', '')
            async with session.get(PLAYER_API_URL.format(formatted_uuid)) as response:
                if response.status == 200:
                    data = await response.json()
                    self.player_name_cache[player_uuid] = data.get('username', 'Unknown')
                    return Player(player_uuid, data)
                else:
                    print(f"⚠️ {player_uuid} のデータ取得に失敗。ステータス: {response.status}")
                    return None
        except Exception as e:
            # ここで例外をキャッチして、呼び出し元に情報を返す
            return e

    def find_changed_players(self, current_state):
        changed_players = {}
        for uuid, current_player in current_state.items():
            if uuid in self.previous_players_state:
                previous_player = self.previous_players_state[uuid]
                for raid_type in RAID_TYPES:
                    current_count = current_player.get_raid_count(raid_type)
                    previous_count = previous_player.get_raid_count(raid_type)
                    if current_count > previous_count:
                        if raid_type not in changed_players:
                            changed_players[raid_type] = []
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
        await self.bot.wait_until_ready()
        print("👍 RaidTracker: ループを開始します。")

async def setup(bot):
    await bot.add_cog(RaidTracker(bot))
