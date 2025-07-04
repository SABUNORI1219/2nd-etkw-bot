import discord
from discord.ext import commands, tasks
from datetime import datetime
import uuid

# libフォルダから専門家たちをインポート
from lib.wynncraft_api import WynncraftAPI
from lib.database_handler import add_raid_records
from lib.raid_logic import RaidLogicHandler
# configから設定をインポート
from config import TRACKING_CHANNEL_ID
# Playerクラスをインポート
from player import Player 

class RaidTrackerCog(commands.Cog):
    """
    レイドクリアの自動検知と通知を担当するCog。
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.wynn_api = WynncraftAPI()
        self.raid_logic = RaidLogicHandler()
        self.previous_state = {}
        self.raid_tracker_task.start()
        print("--- [TrackerCog] レイドトラッカーCogが読み込まれ、タスクが開始されました。")

    def cog_unload(self):
        """Cogがアンロードされるときにタスクを停止する"""
        self.raid_tracker_task.cancel()
        print("--- [TrackerCog] レイドトラッカータスクが停止されました。")

    @tasks.loop(minutes=1.0)
    async def raid_tracker_task(self):
        """
        定期的にギルドデータを取得し、レイドクリアを検知・通知するメインループ。
        """
        print(f"--- [TrackerCog] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - トラッキングチェックを開始...")
        
        guild_data = await self.wynn_api.get_nori_guild_data()
        if not guild_data:
            print("--- [TrackerCog] APIからギルドデータを取得できませんでした。")
            return

        current_state = {}
        online_info = {}
        
        # ▼▼▼【エラー修正箇所】▼▼▼
        # メンバーのデータが辞書(dict)であるかを確認する
        for member_data in guild_data.get("members", []):
            if not isinstance(member_data, dict):
                continue # 文字列の場合はスキップ

            player_uuid = member_data.get("uuid")
            if not player_uuid:
                continue

            player_name = member_data.get("name")
            
            if member_data.get("online", False):
                player = Player(name=player_name, uuid=player_uuid)
                
                # APIから最新のレイド数を取得してセットする
                player_raid_data = await self.wynn_api.get_player_raid_data(player_uuid)
                if player_raid_data:
                    player.set_raid_counts(player_raid_data)
                
                current_state[player_uuid] = player
                online_info[player_uuid] = {
                    "server": member_data.get("server"),
                    "name": player_name
                }
        # ▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲
        
        if not self.previous_state:
            print("--- [TrackerCog] 初回実行のため、現在の状態を保存します。")
            self.previous_state = current_state
            return
            
        changed_players = self.raid_logic.find_changed_players(current_state, self.previous_state)
        if not changed_players:
            print("--- [TrackerCog] レイドクリア数の変化はありませんでした。")
            self.previous_state = current_state
            return
            
        identified_parties = self.raid_logic.identify_parties(changed_players, online_info)
        if not identified_parties:
            print("--- [TrackerCog] 変化はありましたが、4人パーティの成立は確認できませんでした。")
            self.previous_state = current_state
            return

        notification_channel = self.bot.get_channel(TRACKING_CHANNEL_ID)
        if not notification_channel:
            print(f"--- [TrackerCog] エラー: 通知チャンネル(ID: {TRACKING_CHANNEL_ID})が見つかりません。")
            self.previous_state = current_state
            return
            
        for party in identified_parties:
            await self.notify_and_save_party(party, online_info, notification_channel)

        self.previous_state = current_state
        print("--- [TrackerCog] トラッキングチェックを完了しました。")
        
    async def notify_and_save_party(self, party: dict, online_info: dict, channel: discord.TextChannel):
        """パーティのクリア情報を通知し、データベースに保存する"""
        raid_type = party['raid_type']
        player_uuids = party['players']
        
        group_id = str(uuid.uuid4())
        cleared_at = datetime.now()
        
        discord_ids = {uuid: 0 for uuid in player_uuids} 
        
        records_to_add = [
            (group_id, discord_ids[p_uuid], p_uuid, raid_type, cleared_at)
            for p_uuid in player_uuids
        ]
        
        add_raid_records(records_to_add)
        
        player_names = [online_info[p_uuid]['name'] for p_uuid in player_uuids]
        player_list_str = "\n".join(f"- {name}" for name in player_names)
        
        embed = discord.Embed(
            title=f"🎉 レイドクリア検知: {raid_type}",
            description=f"以下のパーティがレイドをクリアしました！\n\n{player_list_str}",
            color=discord.Color.gold(),
            timestamp=cleared_at
        )
        embed.set_footer(text="Raid Tracker")
        
        await channel.send(embed=embed)
        print(f"--- [TrackerCog] {raid_type} のクリアをチャンネルに通知しました。")

    @raid_tracker_task.before_loop
    async def before_tracker_task(self):
        """タスクが開始される前にBotが準備完了するまで待つ"""
        await self.bot.wait_until_ready()

# BotにCogを登録するためのセットアップ関数
async def setup(bot: commands.Bot):
    await bot.add_cog(RaidTrackerCog(bot))
