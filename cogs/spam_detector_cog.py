import discord
from discord.ext import commands
import logging
from collections import defaultdict
from datetime import datetime, timedelta

# configから設定をインポート
from config import SPAM_TARGET_USER_IDS

logger = logging.getLogger(__name__)

# スパムと判断する基準
SPAM_MESSAGE_COUNT = 3  # この回数以上投稿したら
SPAM_TIME_WINDOW = timedelta(seconds=2) # この秒数以内に

class SpamDetectorCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # {user_id: [message_timestamp, ...]} の形でメッセージ時刻を記録
        self.user_message_timestamps = defaultdict(list)
        logger.info(f"--- [Cog] {self.__class__.__name__} が読み込まれました。")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Bot自身のメッセージは無視
        if message.author == self.bot.user:
            return

        # 監視対象のユーザーでなければ、何もしない
        if message.author.id not in SPAM_TARGET_USER_IDS:
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

# BotにCogを登録するためのセットアップ関数
async def setup(bot: commands.Bot):
    await bot.add_cog(SpamDetectorCog(bot))
