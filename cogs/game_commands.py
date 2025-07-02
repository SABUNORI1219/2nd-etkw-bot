import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timezone
import uuid

# 他のファイルから関数をインポート
from database import add_raid_records, get_raid_counts

# APIからプレイヤーのUUIDを取得するヘルパー関数
async def get_uuid_from_name(player_name):
    # Nori APIや他のAPIを使って名前からUUIDを取得する
    # 今回は仮の関数として定義
    # 例: return "f1b5d3c8-9b8a-4b0e-8b0a-9b8d3c8b0a9b"
    # 実際にはaiohttpを使ったAPIリクエストが必要
    # この機能は後で実装
    return None 

class GameCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="graidcount", description="指定プレイヤーのレイドクリア回数を集計します。")
    @app_commands.describe(player_name="Minecraftのプレイヤー名", since="集計開始日 (YYYY-MM-DD形式)")
    async def raid_count(self, interaction: discord.Interaction, player_name: str, since: str = None):
        await interaction.response.defer() # 処理に時間がかかることを通知

        # 日付の処理
        if since:
            try:
                since_date = datetime.strptime(since, "%Y-%m-%d")
            except ValueError:
                await interaction.followup.send("日付の形式が正しくありません。`YYYY-MM-DD`形式で入力してください。")
                return
        else:
            # 指定がない場合は1ヶ月前から
            since_date = datetime.now() - discord.Timedelta(days=30)
            
        # プレイヤーUUIDの取得（後で実装）
        player_uuid = await get_uuid_from_name(player_name)
        if not player_uuid:
            # 仮実装：今はUUIDを直接入力
            player_uuid = player_name 

        # データベースから記録を取得
        records = get_raid_counts(player_uuid, since_date)

        embed = discord.Embed(
            title=f"{player_name}のレイドクリア回数",
            description=f"{since_date.strftime('%Y年%m月%d日')}以降の記録",
            color=discord.Color.blue()
        )

        if not records:
            embed.description += "\n\nクリア記録はありませんでした。"
        else:
            total = 0
            for record in records:
                raid_type = record[0].upper()
                count = record[1]
                embed.add_field(name=raid_type, value=f"{count} 回", inline=True)
                total += count
            embed.set_footer(text=f"合計: {total} 回")

        await interaction.followup.send(embed=embed)

    # 権限設定（例：'Admin' or 'Officer' の役職を持つ人のみ実行可能）
    @app_commands.command(name="raidaddmanual", description="レイドクリア記録を手動で追加します。")
    @app_commands.checks.has_any_role("Admin", "Officer") # 役職名をギルドに合わせて変更してください
    @app_commands.describe(
        raid_type="レイドの種類 (tna, tcc, nol, nog)",
        member1="メンバー1", member2="メンバー2", member3="メンバー3", member4="メンバー4"
    )
    async def raid_add_manual(self, interaction: discord.Interaction, raid_type: str, 
                              member1: discord.User, member2: discord.User, member3: discord.User, member4: discord.User):
        
        raid_type = raid_type.lower()
        if raid_type not in ["tna", "tcc", "nol", "nog"]:
            await interaction.response.send_message("レイドの種類が正しくありません。", ephemeral=True)
            return
            
        await interaction.response.defer()

        members = [member1, member2, member3, member4]
        group_id = f"manual-{uuid.uuid4()}"
        cleared_at = datetime.now(timezone.utc)
        db_records = []
        player_uuids = [] # UUID取得は後で実装

        for member in members:
            # 仮実装：今はDiscord IDをUUIDとして保存
            player_uuid = str(member.id) 
            player_uuids.append(player_uuid)
            db_records.append((group_id, member.id, player_uuid, raid_type, cleared_at))

        add_raid_records(db_records)

        embed = discord.Embed(
            title=f"📝 手動で記録追加 [{raid_type.upper()}]",
            description="以下のメンバーのクリア記録が手動で追加されました。",
            color=discord.Color.green(),
            timestamp=cleared_at
        )
        embed.add_field(name="メンバー", value="\n".join([m.mention for m in members]), inline=False)
        embed.set_footer(text=f"実行者: {interaction.user.display_name}")
        
        await interaction.followup.send(embed=embed)
        
    @raid_add_manual.error
    async def on_raid_add_manual_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingAnyRole):
            await interaction.response.send_message("このコマンドを実行する権限がありません。", ephemeral=True)
        else:
            await interaction.response.send_message(f"エラーが発生しました: {error}", ephemeral=True)


async def setup(bot):
    await bot.add_cog(GameCommands(bot))
