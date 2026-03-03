import os
import discord

from lib.utils import create_embed

WYNNCRAFT_API_TOKEN = os.getenv('WYNN_API_TOKEN')

# コマンドの許可ユーザーリスト
AUTHORIZED_USER_IDS = [
    1062535250099589120,
    1074666910496600174
    ]  # 必要ならここに追加

# サーバーID（スキン頭絵文字用）
SKIN_EMOJI_SERVER_ID = 1158535340110381157

# テリトリーリソースと絵文字の対応表
RESOURCE_EMOJIS = {
    "EMERALDS": "<:wynn_emerald:1395325625522458654>",
    "ORE": "<:wynn_ore:1395325664508383262>",
    "WOOD": "<:wynn_wood:1395325681440788621>",
    "FISH": "<:wynn_fish:1395325644899881011>",
    "CROPS": "<:wynn_crop:1395325604806656032>"
}

async def send_authorized_only_message(interaction: discord.Interaction, user_ids=None):
    """
    指定ユーザー以外がコマンド実行時に警告メッセージを返す共通関数。
    user_ids: 許可ユーザーIDリスト（Noneの場合はAUTHORIZED_USER_IDS）
    """
    if user_ids is None:
        user_ids = AUTHORIZED_USER_IDS
    # mention形式のユーザー名リストを作る
    mentions = ", ".join([f"<@{uid}>" for uid in user_ids])
    embed = create_embed(description=f"このコマンドは現在 {mentions} のみ使用できます！", title="🔴 エラーが発生しました", color=discord.Color.red(), footer_text=f"Config | Onyx")
    await interaction.response.send_message(embed=embed)
