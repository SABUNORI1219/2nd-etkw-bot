import discord
from discord.ext import commands, tasks
from datetime import datetime
import uuid # group_idを生成するためにインポート

# libフォルダから専門家たちをインポート
from lib.wynncraft_api import WynncraftAPI
from lib.database_handler import add_raid_records
from lib.raid_logic import RaidLogicHandler
# configから設定をインポート
from config import TRACKING_CHANNEL_ID, TARGET_GUILDS, RAID_TYPES

# Playerクラスをインポート（あとでPlayerの状態を保持するために使います）
from player import Player 

class RaidTrackerCog(commands.Cog):
    """
    レイドクリアの自動検知と通知を担当するCog。
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.wynn_api = WynncraftAPI()
        self.raid_logic = RaidLogicHandler()
        self.previous_state = {} # 前回のプレイヤー状態を保存する辞書
        self.raid_tracker_task.start() # Cogが読み込まれたらタスクを開始
        print("--- [TrackerCog] レイドトラッカーCogが読み込まれ、タスクが開始されました。")

    def cog_unload(self):
        """Cogがアンロードされるときにタスクを停止する"""
        self.raid_tracker_task.cancel()
        print("--- [TrackerCog] レイドトラッカータスクが停止されました。")

    @tasks.loop(minutes=1.0) # 1分ごとに実行
    async def raid_tracker_task(self):
        """
        定期的にギルドデータを取得し、レイドクリアを検知・通知するメインループ。
        """
        print(f"--- [TrackerCog] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - トラッキングチェックを開始...")
        
        # 1. API担当にギルドデータを依頼
        guild_data = await self.wynn_api.get_guild_data()
        if not guild_data:
            print("--- [TrackerCog] APIからギルドデータを取得できませんでした。")
            return

        # 2. 現在のオンラインプレイヤー情報とレイド数を整理
        current_state = {}
        online_info = {}
        
        # Playerクラスを使ってデータを整理
        for member_data in guild_data.get("members", []):
            player_name = member_data.get("name")
            player_uuid = member_data.get("uuid")
            
            # オンラインのメンバーのみを追跡対象とする
            if member_data.get("online", False):
                # Playerオブジェクトを作成して、現在の状態を保存
                player = Player(name=player_name, uuid=player_uuid)
                player.set_raid_counts(member_data.get("raids", {}))
                
                current_state[player_uuid] = player
                online_info[player_uuid] = {
                    "server": member_data.get("server"),
                    "name": player_name
                }
        
        # 3. 初回実行時はprevious_stateを初期化して終了
        if not self.previous_state:
            print("--- [TrackerCog] 初回実行のため、現在の状態を保存します。")
            self.previous_state = current_state
            return
            
        # 4. 分析担当に「変化したプレイヤー」の特定を依頼
        changed_players = self.raid_logic.find_changed_players(current_state, self.previous_state)
        if not changed_players:
            print("--- [TrackerCog] レイドクリア数の変化はありませんでした。")
            self.previous_state = current_state # 状態を更新
            return
            
        # 5. 分析担当に「4人パーティ」の特定を依頼
        identified_parties = self.raid_logic.identify_parties(changed_players, online_info)
        if not identified_parties:
            print("--- [TrackerCog] 変化はありましたが、4人パーティの成立は確認できませんでした。")
            self.previous_state = current_state # 状態を更新
            return

        # 6. 結果を処理（通知とDB保存）
        notification_channel = self.bot.get_channel(TRACKING_CHANNEL_ID)
        if not notification_channel:
            print(f"--- [TrackerCog] エラー: 通知チャンネル(ID: {TRACKING_CHANNEL_ID})が見つかりません。")
            self.previous_state = current_state # 状態を更新
            return
            
        for party in identified_parties:
            await self.notify_and_save_party(party, online_info, notification_channel)

        # 7. 最後に、現在の状態を次回の比較のために保存
        self.previous_state = current_state
        print("--- [TrackerCog] トラッキングチェックを完了しました。")
        
    async def notify_and_save_party(self, party: dict, online_info: dict, channel: discord.TextChannel):
        """パーティのクリア情報を通知し、データベースに保存する"""
        raid_type = party['raid_type']
        player_uuids = party['players']
        
        # group_idを生成
        group_id = str(uuid.uuid4())
        cleared_at = datetime.now()
        
        # DiscordのユーザーIDを取得（ここでは仮で0とします。実際の運用では特定方法が必要）
        # この部分は、UUIDとDiscord IDを紐づける別の仕組みが必要になります。
        discord_ids = {uuid: 0 for uuid in player_uuids} 
        
        # データベース保存用のレコードを作成
        records_to_add = [
            (group_id, discord_ids[p_uuid], p_uuid, raid_type, cleared_at)
            for p_uuid in player_uuids
        ]
        
        # データベース担当に保存を依頼
        add_raid_records(records_to_add)
        
        # 通知メッセージを作成
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
