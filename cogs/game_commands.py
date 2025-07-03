import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timezone
import uuid
import aiohttp
import asyncio

from database import add_raid_records, get_raid_counts

# Wynncraft公式のUUID検索API
UUID_API_URL = "https://api.wynncraft.com/v3/player/{}"

async def get_uuid_from_name(player_name: str):
    """プレイヤー名からハイフン付きのUUIDを取得する。見つからなければNoneを返す。"""
    try:
        # v3 APIはプレイヤー名で検索可能
        async with aiohttp.ClientSession() as session:
            async with session.get(UUID_API_URL.format(player_name)) as response:
                if response.status == 200:
                    data = await response.json()
                    # ハイフン付きUUIDを返す
                    return data.get('uuid')
                else:
                    return None
    except Exception:
        return None

class GameCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="graidcount", description="指定プレイヤーのレイドクリア回数を集計します。")
    @app_commands.describe(player_name="Minecraftのプレイヤー名", since="集計開始日 (YYYY-MM-DD形式)")
    async def raid_count(self, interaction: discord.Interaction, player_name: str, since: str = None):
        await interaction.response.defer()

        if since:
            try:
                since_date = datetime.strptime(since, "%Y-%m-%d")
            except ValueError:
                await interaction.followup.send("日付の形式が正しくありません。`YYYY-MM-DD`形式で入力してください。")
                return
        else:
            since_date = datetime.now() - discord.Timedelta(days=30)

        player_uuid = await get_uuid_from_name(player_name)
        if not player_uuid:
            await interaction.followup.send(f"プレイヤー「{player_name}」が見つかりませんでした。")
            return

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
                raid_type, count = record[0].upper(), record[1]
                embed.add_field(name=raid_type, value=f"{count} 回", inline=True)
                total += count
            embed.set_footer(text=f"合計: {total} 回")

        await interaction.followup.send(embed=embed)

    @app_commands.command(name="raidaddmanual", description="レイドクリア記録を手動で追加します。(MCID指定)")
    @app_commands.checks.has_any_role("MEMBER") # 役職名をギルドに合わせて変更してください
    @app_commands.describe(
        raid_type="レイドの種類 (tna, tcc, nol, nog)",
        player1="プレイヤー1のMCID",
        player2="プレイヤー2のMCID",
        player3="プレイヤー3のMCID",
        player4="プレイヤー4のMCID"
    )
    async def raid_add_manual(self, interaction: discord.Interaction, raid_type: str,
                              player1: str, player2: str, player3: str, player4: str):

        raid_type = raid_type.lower()
        if raid_type not in ["tna", "tcc", "nol", "nog"]:
            await interaction.response.send_message("レイドの種類が正しくありません。", ephemeral=True)
            return

        await interaction.response.defer()

        player_names = [player1, player2, player3, player4]
        group_id = f"manual-{uuid.uuid4()}"
        cleared_at = datetime.now(timezone.utc)
        db_records = []

        # 各プレイヤーのUUIDを非同期で取得
        uuid_tasks = [get_uuid_from_name(name) for name in player_names]
        player_uuids = await asyncio.gather(*uuid_tasks)

        # 見つからなかったプレイヤーをチェック
        not_found_players = [player_names[i] for i, u in enumerate(player_uuids) if not u]
        if not_found_players:
            await interaction.followup.send(f"以下のプレイヤーが見つかりませんでした: {', '.join(not_found_players)}")
            return

        for i, player_uuid in enumerate(player_uuids):
            # Discord IDは不明なので0として保存
            db_records.append((group_id, 0, player_uuid, raid_type, cleared_at))

        add_raid_records(db_records)

        embed = discord.Embed(
            title=f"📝 手動で記録追加 [{raid_type.upper()}]",
            description="以下のメンバーのクリア記録が手動で追加されました。",
            color=discord.Color.green(),
            timestamp=cleared_at
        )
        embed.add_field(name="メンバー", value="\n".join(player_names), inline=False)
        embed.set_footer(text=f"実行者: {interaction.user.display_name}")

        await interaction.followup.send(embed=embed)

    @raid_add_manual.error
    async def on_raid_add_manual_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingAnyRole):
            # Check if the interaction is already responded to
            if not interaction.response.is_done():
                await interaction.response.send_message("このコマンドを実行する権
