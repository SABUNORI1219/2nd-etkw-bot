import discord
import re
from discord.ext import commands, tasks
from collections import Counter
import logging
import asyncio
from collections import defaultdict
from datetime import datetime, timedelta

from config import (
    SPAM_TARGET_USER_IDS, 
    ETKW_SERVER, 
    TERRITORY_LOSS_NOTIFICATION_CHANNEL,
    TERRITORY_LOSS_MENTION_USERS,
    TERRITORY_MONITOR_CHANNEL
)
from lib.utils import create_embed
from lib.db import get_all_linked_members
from lib.api_stocker import WynncraftAPI

logger = logging.getLogger(__name__)

# スパムと判断する基準
SPAM_MESSAGE_COUNT = 3
SPAM_TIME_WINDOW = timedelta(seconds=0.95)

# オフシーズン判定フラグ
is_offseason = False

# 監視対象の領地リスト（ETKWが保持している領地）
MONITORED_TERRITORIES = {
    "Dragonbone Graveyard", "Pyroclastic Flow", "Freezing Heights", "Dogun Ritual Site", 
    "Lava Lakes", "Crater Descent", "Rodoroc", "Entrance to Molten Heights", "Eltom", 
    "Ranol's Farm", "Thesead Suburbs", "Cherry Blossom Grove", "Displaced Housing", 
    "Thesead", "Entrance to Thesead", "Path to the Dojo", "Canyon High Path", 
    "The Hive", "Wanderer's Way", "Thanos Exit", "Illuminant Path", "Workshop Glade", 
    "Bandit's Toll", "Canyon Walkway", "Molten Passage", "Path to Ozoth's Spire", 
    "Secluded Ponds", "Burning Airship", "Bandit Cave", "Wizard's Warning", 
    "Perilous Grotto", "Inhospitable Mountain", "Wizard Tower", "Thesead Underpass", 
    "Cliffside Passage North", "Cliffside Passage South", "Elephelk Trail", 
    "Bantisu Approach", "Bantisu Air Temple", "Krolton's Cave", "Hobgoblin's Hoard", 
    "Harpy's Haunt North", "Harpy's Haunt South", "Elefolk Stomping Grounds", 
    "Fleris Cranny", "Perilous Passage", "Wayward Split", "Cascading Basins", 
    "Cyclospordial Hazard", "Turncoat Turnabout", "Winding Waters", 
    "Parasitic Slime Mine", "Panda Kingdom", "Panda Path", "Troll Tower", 
    "Featherfall Cliffs", "Protector's Pathway", "Kandon-Beda", "Housing Crisis", 
    "Canyon Dropoff", "Rocky Bend"
}

class SpamDetectorCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.user_message_timestamps = defaultdict(list)
        self.vc_join_times = {}  # ユーザーのVC参加時間を記録
        self.api = WynncraftAPI()  # シーズンチェック用API
        logger.info(f"--- [Cog] {self.__class__.__name__} が読み込まれました。")
        # シーズンチェックタスクを開始
        self.season_check_task.start()

    def cog_unload(self):
        self.season_check_task.cancel()

    @tasks.loop(minutes=1)
    async def season_check_task(self):
        """1分おきにシーズン状態をチェック"""
        try:
            global is_offseason
            seq_data = await self.api.get_seq_guild_for_season_check()
            if not seq_data or 'seasonRanks' not in seq_data:
                logger.warning("[SeasonCheck] SEQギルドのseasonRanksデータ取得失敗")
                return
                
            season_ranks = seq_data['seasonRanks']
            if not season_ranks:
                logger.warning("[SeasonCheck] seasonRanksが空です")
                return
                
            # 最新シーズンを取得（シーズン番号でソート）
            latest_season_key = max(season_ranks.keys(), key=int)
            latest_season = season_ranks[latest_season_key]
            
            # finalTerritoriesの存在でオフシーズン判定
            new_offseason_status = 'finalTerritories' in latest_season
            
            if new_offseason_status != is_offseason:
                is_offseason = new_offseason_status
                status_msg = "オフシーズン" if is_offseason else "シーズン中"
                logger.info(f"[SeasonCheck] シーズン状態変更: {status_msg} (シーズン{latest_season_key})")
            
        except Exception as e:
            logger.error(f"[SeasonCheck] シーズンチェックで例外: {e}", exc_info=True)

    @season_check_task.before_loop
    async def before_season_check_task(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        try:
            # Bot自身のメッセージは無視
            if message.author == self.bot.user:
                return
            
            # 領地奪取監視機能（簡易版テスト）
            await self._check_territory_loss(message)

            # 以下は既存のスパム検知機能
            # 監視対象のユーザーでなければ、何もしない
            if message.author.id not in SPAM_TARGET_USER_IDS:
                return

            # 全てのユーザーメンションをcontentから抽出
            mention_pattern = r"<@!?(\d+)>"
            all_mentions = re.findall(mention_pattern, message.content)

            all_mentions_int = [int(user_id) for user_id in all_mentions]

            # 各ユーザーIDのメンション回数をカウント
            other_mentions = [user_id for user_id in all_mentions_int if int(user_id) != message.author.id]
            mention_counts = Counter(other_mentions)

            # 2回以上メンションされたユーザーを抽出
            multi_mentioned_users = [user_id for user_id, count in mention_counts.items() if count >= 2]
            if multi_mentioned_users:
                logger.info(f"--- [SpamDetector] ユーザー'{message.author.name}'が同一ユーザーを複数回メンションしました: {multi_mentioned_users}")
                await message.reply("tkbad!")
                return

            user_id = message.author.id
            current_time = datetime.utcnow()

            # タイムウィンドウより古いタイムスタンプを履歴から削除
            self.user_message_timestamps[user_id] = [
                t for t in self.user_message_timestamps[user_id]
                if current_time - t < SPAM_TIME_WINDOW
            ]

            # 新しいメッセージのタイムスタンプを追加
            self.user_message_timestamps[user_id].append(current_time)

            # タイムウィンドウ内のメッセージ数が閾値を超えたかチェック
            if len(self.user_message_timestamps[user_id]) >= SPAM_MESSAGE_COUNT:
                logger.info(f"--- [SpamDetector] ユーザー'{message.author.name}'によるスパムを検知！")
                
                # 応答メッセージを送信
                await message.reply("tkbad!")
                
                # 一度応答したら、そのユーザーの履歴をリセット
                self.user_message_timestamps[user_id] = []
                
        except Exception as e:
            logger.error(f"--- [SpamDetector] on_message で予期しない例外: {e}", exc_info=True)
    
    async def _check_territory_loss(self, message: discord.Message):
        """領地奪取監視機能"""
        try:
            # オフシーズンチェック（raid_tracker_taskのseasonRanksデータを参照）
            from tasks.raid_tracker_task import current_season_ranks
            if current_season_ranks:
                try:
                    # 最新シーズンを取得
                    latest_season_key = max(current_season_ranks.keys(), key=int)
                    latest_season = current_season_ranks[latest_season_key]
                    # finalTerritoriesが存在すればオフシーズン
                    if 'finalTerritories' in latest_season:
                        logger.debug(f"[TerritoryLoss] オフシーズンのため領地監視機能は停止中 (シーズン{latest_season_key})")
                        return
                except (ValueError, KeyError) as e:
                    logger.warning(f"[TerritoryLoss] seasonRanks解析エラー: {e}")
                
            # 指定されたチャンネルでなければ無視
            if message.channel.id != TERRITORY_MONITOR_CHANNEL:
                return
            
            # Botのメッセージに限定（別Botの通知）
            if not message.author.bot:
                return
            
            # Embedがない場合は無視
            if not message.embeds:
                return
            
            embed = message.embeds[0]
            
            # タイトルが"Territory Lost"を含むかチェック（**も考慮）
            if not embed.title or "Territory Lost" not in embed.title:
                return
            
            # フィールドから情報を抽出
            if not embed.fields:
                return
            
            territory_name = embed.fields[0].name if embed.fields[0].name else "不明"
            field_value = embed.fields[0].value if embed.fields[0].value else ""
            
            # 監視対象の領地かどうかをチェック
            if territory_name not in MONITORED_TERRITORIES:
                return
            
            # "-> " の後ろにあって、その後の " (" までの文字を抜き出す
            # 最も確実なパターン：数字の矢印パターンの後の矢印を対象とする
            attacker_match = re.search(r'\(\d+\s*->\s*\d+\)\s*->\s*(.+?)\s*\(', field_value)
            
            if attacker_match:
                attacker_guild = attacker_match.group(1).strip()
                # 指定ギルドに奪われた場合はスルー
                SKIP_GUILDS = {"The Nameless Samurai", "JFZN JAPAN", "wasting consumables", "Nobody"}
                if attacker_guild in SKIP_GUILDS:
                    return
            else:
                logger.warning(f"--- [RegexFail] 抽出失敗。原文: {field_value}")
                return
            
            # 通知用チャンネルを取得
            notification_channel = self.bot.get_channel(TERRITORY_LOSS_NOTIFICATION_CHANNEL)
            if not notification_channel:
                return
            
            # Ping対象：config指定ユーザーの中でオンライン＋最近アクティブでない人のみ抽出
            from tasks.raid_tracker_task import current_tracking_members
            linked_members = get_all_linked_members()
            target_set = set(TERRITORY_LOSS_MENTION_USERS or [])
            # mcid->discord_id のマップ（config指定ユーザーのみ）
            mcid_to_discord = {m["mcid"]: m.get("discord_id") for m in linked_members if m.get("discord_id") in target_set}
            # オンライン＋最近アクティブなMCIDセットを作成
            active_mcids = set()
            for member in current_tracking_members:
                mcid = member.get("name")
                if mcid:
                    active_mcids.add(mcid)
            # config指定ユーザーの中で、オンライン＋最近アクティブでない人を抽出
            ping_user_ids = []
            for mcid, discord_id in mcid_to_discord.items():
                if mcid not in active_mcids:  # オンライン＋最近アクティブでない人
                    ping_user_ids.append(discord_id)
            
            # 重複除去
            ping_user_ids = sorted(set(ping_user_ids))
            mentions = " ".join([f"<@{uid}>" for uid in ping_user_ids]) if ping_user_ids else None
            
            # 通知用Embedを作成
            notification_embed = create_embed(
                title="領地が奪われたよ！起きよう！",
                description="",
                color=discord.Color.red(),
                footer_text="Territory Monitor | Minister Chikuwa"
            )
            notification_embed.add_field(
                name="どの領地！？",
                value=f"`{territory_name}`",
                inline=False
            )
            notification_embed.add_field(
                name="どこのギルド！？",
                value=f"`{attacker_guild}`",
                inline=False
            )
            notification_embed.add_field(
                name="いつ！？",
                value=f"<t:{int(datetime.utcnow().timestamp())}:R>",
                inline=False
            )
            notification_embed.timestamp = datetime.utcnow()
            
            try:
                await asyncio.wait_for(
                    notification_channel.send(
                        content=mentions,
                        embed=notification_embed,
                        allowed_mentions=discord.AllowedMentions(roles=False, users=True, everyone=False)
                    ),
                    timeout=7.0
                )
            except asyncio.TimeoutError:
                logger.warning("--- [TerritoryLoss] 通知送信がタイムアウトしました")
                
        except Exception as e:
            logger.error(f"--- [TerritoryLoss] _check_territory_loss で予期しない例外: {e}", exc_info=True)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        # ETKW_SERVERでない場合は無視
        if member.guild.id != ETKW_SERVER:
            return

        current_time = datetime.utcnow()

        # VC参加
        if before.channel is None and after.channel is not None:
            self.vc_join_times[member.id] = current_time

            embed = create_embed(
                title=member.display_name,
                description=f"Joined `{after.channel.name}`",
                color=discord.Color.green(),
                footer_text=f"現在のメンバー数: {len(after.channel.members)}/{after.channel.user_limit if after.channel.user_limit else '∞'}"
            )
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.timestamp = current_time

            try:
                await after.channel.send(embed=embed)
                logger.info(f"--- [VCNotify] {member.display_name} が {after.channel.name} に参加 -> VCチャットに通知送信")
            except discord.Forbidden:
                logger.warning(f"--- [VCNotify] {after.channel.name} のVCチャットに送信権限がありません")
            except Exception as e:
                logger.error(f"--- [VCNotify] 通知送信エラー: {e}", exc_info=True)

        # VC退出
        elif before.channel is not None and after.channel is None:
            # 接続時間の計算
            connection_time = ""
            if member.id in self.vc_join_times:
                duration = current_time - self.vc_join_times[member.id]
                minutes = int(duration.total_seconds() // 60)
                seconds = int(duration.total_seconds() % 60)
                connection_time = f" (滞在時間: {minutes}分{seconds}秒)" if minutes > 0 else f" (滞在時間: {seconds}秒)"
                self.vc_join_times.pop(member.id, None)

            embed = create_embed(
                title=member.display_name,
                description=f"Left `{before.channel.name}`{connection_time}",
                color=discord.Color.red(),
                footer_text=f"現在のメンバー数: {len(before.channel.members)}/{before.channel.user_limit if before.channel.user_limit else '∞'}"
            )
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.timestamp = current_time

            try:
                await before.channel.send(embed=embed)
                logger.info(f"--- [VCNotify] {member.display_name} が {before.channel.name} から退室 -> VCチャットに通知送信")
            except discord.Forbidden:
                logger.warning(f"--- [VCNotify] {before.channel.name} のVCチャットに送信権限がありません")
            except Exception as e:
                logger.error(f"--- [VCNotify] 通知送信エラー: {e}")

        # VC移動（別のVCへ）
        elif before.channel is not None and after.channel is not None and before.channel != after.channel:
            connection_time = ""
            if member.id in self.vc_join_times:
                duration = current_time - self.vc_join_times[member.id]
                minutes = int(duration.total_seconds() // 60)
                seconds = int(duration.total_seconds() % 60)
                connection_time = f" (滞在時間: {minutes}分{seconds}秒)" if minutes > 0 else f" (滞在時間: {seconds}秒)"

            # 新しいVCでの参加時間を記録
            self.vc_join_times[member.id] = current_time

            embed = create_embed(
                title=member.display_name,
                description=f"Moved from `{before.channel.name}` to `{after.channel.name}`{connection_time}",
                color=discord.Color.blue(),
                footer_text=f"移動先メンバー数: {len(after.channel.members)}/{after.channel.user_limit if after.channel.user_limit else '∞'}"
            )
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.timestamp = current_time

            try:
                await after.channel.send(embed=embed)
                logger.info(f"--- [VCNotify] {member.display_name} が {before.channel.name} から {after.channel.name} に移動 -> 移動先VCチャットに通知送信")
            except discord.Forbidden:
                logger.warning(f"--- [VCNotify] {after.channel.name} のVCチャットに送信権限がありません")
            except Exception as e:
                logger.error(f"--- [VCNotify] 通知送信エラー: {e}")

# セットアップ関数
async def setup(bot: commands.Bot):
    await bot.add_cog(SpamDetectorCog(bot))
