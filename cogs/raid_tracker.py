# cogs/raid_tracker.py

import discord
from discord.ext import tasks, commands
import aiohttp

# ... (APIのURL定義) ...

class RaidTracker(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.previous_raid_counts = {}
        print("✅ RaidTracker Cog: __init__が呼び出されました。") # ⬅️ 追加
        self.raid_check_loop.start()
        print("✅ RaidTracker Cog: ループの開始を試みました。") # ⬅️ 追加

    # ... (cog_unload) ...

    @tasks.loop(minutes=1)
    async def raid_check_loop(self):
        print("➡️ レイド数のチェックを開始します...")
        # ... (ループ内の処理) ...

    @raid_check_loop.before_loop
    async def before_raid_check_loop(self):
        print("⏳ RaidTracker Cog: before_loop - Botの準備を待機します。") # ⬅️ 追加
        await self.bot.wait_until_ready()
        print("👍 RaidTracker Cog: before_loop - Botの準備が完了しました。") # ⬅️ 追加

async def setup(bot):
    print("⚙️ RaidTracker Cog: setup関数が呼び出されました。") # ⬅️ 追加
    await bot.add_cog(RaidTracker(bot))
    print("🎉 RaidTracker Cog: Botに正常に登録されました。") # ⬅️ 追加
