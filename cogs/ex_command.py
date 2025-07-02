# cogs/game_commands.py

import discord
from discord.ext import commands
# database.pyから関数をインポート
# from database import add_clear_record

class GameCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # 'add'という名前のコマンドを定義
    @commands.command(name='add')
    async def add_clear(self, ctx, *, content: str):
        """クリアしたコンテンツを記録します。例: !add ボスA"""
        user = ctx.author
        # ここにデータベースへ記録を追加する処理を書く
        # add_clear_record(user.id, user.name, content)
        
        await ctx.send(f'{user.mention}さん、「{content}」のクリア記録を追加しました！')

async def setup(bot):
    """CogをBotに登録するための必須の関数"""
    await bot.add_cog(GameCommands(bot))
