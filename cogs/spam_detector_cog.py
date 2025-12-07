import discord
import re
from discord.ext import commands
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

logger = logging.getLogger(__name__)

# スパムと判断する基準
SPAM_MESSAGE_COUNT = 3
SPAM_TIME_WINDOW = timedelta(seconds=0.95)
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
