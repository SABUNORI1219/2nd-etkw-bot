import discord
import re
from discord.ext import commands
from collections import Counter
import logging
from collections import defaultdict
from datetime import datetime, timedelta

from config import SPAM_TARGET_USER_IDS

logger = logging.getLogger(__name__)

# スパムと判断する基準
SPAM_MESSAGE_COUNT = 3
SPAM_TIME_WINDOW = timedelta(seconds=0.9)

class SpamDetectorCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.user_message_timestamps = defaultdict(list)
        logger.info(f"--- [Cog] {self.__class__.__name__} が読み込まれました。")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Bot自身のメッセージは無視
        if message.author == self.bot.user:
            return

        # atu関連
        if message.content.strip() == "atu":
            await message.reply("usi")
            return
        if message.content.strip() == "ATU":
            await message.reply("USI")
            return
        if message.content.strip() == "not atu":
            await message.reply("fake usi")
            return
        if message.content.strip() == "NOT ATU":
            await message.reply("FAKE USI")
            return
        if message.content.strip() == "usi":
            await message.reply("atu")
            return
        if message.content.strip() == "USI":
            await message.reply("ATU")
            return
        if message.content.strip() == "fake usi":
            await message.reply("not atu")
            return
        if message.content.strip() == "FAKE USI":
            await message.reply("NOT ATU")
            return
        if message.content.strip() == "attu":
            await message.reply("morph")
            return

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

# セットアップ関数
async def setup(bot: commands.Bot):
    await bot.add_cog(SpamDetectorCog(bot))
