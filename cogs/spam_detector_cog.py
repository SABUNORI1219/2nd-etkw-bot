import discord
import re
from discord.ext import commands
from collections import Counter
import logging
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

logger = logging.getLogger(__name__)

# スパムと判断する基準
SPAM_MESSAGE_COUNT = 3
SPAM_TIME_WINDOW = timedelta(seconds=0.95)

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
    "Harpy's Haunt North", "Harpy's Haunt South", "Elepholk Stomping Grounds", 
    "Fleris Cranny", "Perilous Passage", "Wayward Split", "Cascading Basins", 
    "Cycrospordial Hazard", "Turncoat Turnabout", "Winding Waters", 
    "Parasitic Slime Mine", "Panda Kingdom", "Panda Path", "Troll Tower", 
    "Featherfall Cliffs", "Protector's Pathway", "Kandon-Beda", "Housing Crisis", 
    "Canyon Dropoff", "Rocky Bend"
}

class SpamDetectorCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.user_message_timestamps = defaultdict(list)
        self.vc_join_times = {}  # ユーザーのVC参加時間を記録
        logger.info(f"--- [Cog] {self.__class__.__name__} が読み込まれました。")

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
            
            # 正規表現で奪取ギルドを抽出
            attacker_match = re.search(r'.*->\s*([^(]+?)\s*\(\d+\s*->\s*\d+\)', field_value)
            
            if not attacker_match:
                logger.warning(f"--- [TerritoryLoss] 領地奪取情報の解析に失敗: {field_value}")
                return
            
            attacker_guild = attacker_match.group(1).strip()
            
            # 通知用チャンネルを取得
            notification_channel = self.bot.get_channel(TERRITORY_LOSS_NOTIFICATION_CHANNEL)
            if not notification_channel:
                logger.error(f"--- [TerritoryLoss] 通知チャンネルが見つかりません: {TERRITORY_LOSS_NOTIFICATION_CHANNEL}")
                return
            
            # メンション文字列を作成
            mentions = " ".join([f"<@{user_id}>" for user_id in TERRITORY_LOSS_MENTION_USERS])
            
            # 通知用Embedを作成
            notification_embed = create_embed(
                title="領地が奪われたよ！起きよう！",
                description=f"**{territory_name}**が**{attacker_guild}**に奪われたよ！",
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
                logger.info(f"--- [TerritoryLoss] 通知送信試行中...")
                await notification_channel.send(content=mentions, embed=notification_embed)
                logger.info(f"--- [TerritoryLoss] 通知送信完了: {territory_name} -> {attacker_guild}")
            except Exception as e:
                logger.error(f"--- [TerritoryLoss] 通知送信エラー: {e}")
                
        except Exception as e:
            logger.error(f"--- [TerritoryLoss] _check_territory_loss で予期しない例外: {e}", exc_info=True)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        # ETKW_SERVERでない場合は無視
        if member.guild.id != ETKW_SERVER:
            return
        
        current_time = datetime.utcnow()
        
        # VC参加の場合
        if before.channel is None and after.channel is not None:
            # 参加時間を記録
            self.vc_join_times[member.id] = current_time
            
            # 緑色のEmbed作成
            embed = create_embed(
                title=member.display_name,
                description=f"Joined `{after.channel.name}`",
                color=discord.Color.green(),
                footer_text=f"現在のメンバー数: {len(after.channel.members)}/{after.channel.user_limit if after.channel.user_limit else '∞'}"
            )
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.timestamp = current_time
            
            # そのVCのチャットに送信
            try:
                await after.channel.send(embed=embed)
                logger.info(f"--- [VCNotify] {member.display_name} が {after.channel.name} に参加 -> VCチャットに通知送信")
            except discord.Forbidden:
                logger.warning(f"--- [VCNotify] {after.channel.name} のVCチャットに送信権限がありません")
            except Exception as e:
                logger.error(f"--- [VCNotify] 通知送信エラー: {e}")
        
        # VC退室の場合
        elif before.channel is not None and after.channel is None:
            # 接続時間を計算
            connection_time = ""
            if member.id in self.vc_join_times:
                duration = current_time - self.vc_join_times[member.id]
                minutes = int(duration.total_seconds() // 60)
                seconds = int(duration.total_seconds() % 60)
                if minutes > 0:
                    connection_time = f" (接続時間: {minutes}分{seconds}秒)"
                else:
                    connection_time = f" (接続時間: {seconds}秒)"
                # 記録を削除
                del self.vc_join_times[member.id]
            
            # 赤色のEmbed作成
            embed = create_embed(
                title=member.display_name,
                description=f"Left `{before.channel.name}`{connection_time}",
                color=discord.Color.red(),
                footer_text=f"現在のメンバー数: {len(before.channel.members)}/{before.channel.user_limit if before.channel.user_limit else '∞'}"
            )
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.timestamp = current_time
            
            # そのVCのチャットに送信
            try:
                await before.channel.send(embed=embed)
                logger.info(f"--- [VCNotify] {member.display_name} が {before.channel.name} から退室 -> VCチャットに通知送信")
            except discord.Forbidden:
                logger.warning(f"--- [VCNotify] {before.channel.name} のVCチャットに送信権限がありません")
            except Exception as e:
                logger.error(f"--- [VCNotify] 通知送信エラー: {e}")
        
        # VC移動の場合（参加→別のVCに移動）
        elif before.channel is not None and after.channel is not None and before.channel != after.channel:
            # 移動時間を計算
            connection_time = ""
            if member.id in self.vc_join_times:
                duration = current_time - self.vc_join_times[member.id]
                minutes = int(duration.total_seconds() // 60)
                seconds = int(duration.total_seconds() % 60)
                if minutes > 0:
                    connection_time = f" (滞在時間: {minutes}分{seconds}秒)"
                else:
                    connection_time = f" (滞在時間: {seconds}秒)"
            
            # 新しいVCの参加時間を記録
            self.vc_join_times[member.id] = current_time
            
            # 青色のEmbed作成（移動を示す）
            embed = create_embed(
                title=member.display_name,
                description=f"Moved from `{before.channel.name}` to `{after.channel.name}`{connection_time}",
                color=discord.Color.blue(),
                footer_text=f"移動先メンバー数: {len(after.channel.members)}/{after.channel.user_limit if after.channel.user_limit else '∞'}"
            )
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.timestamp = current_time
            
            # 移動先VCのチャットに送信
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
