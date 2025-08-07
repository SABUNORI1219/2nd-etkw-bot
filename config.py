import os
import discord

# Wynncraft API関連
NORI_GUILD_API_URL = "https://nori.fish/api/guild/{}"
NORI_PLAYER_API_URL = "https://nori.fish/api/player/{}"
WYNN_PLAYER_API_URL = "https://api.wynncraft.com/v3/player/{}"
WYNN_GUILD_BY_NAME_API_URL = "https://api.wynncraft.com/v3/guild/{}"
WYNN_GUILD_BY_PREFIX_API_URL = "https://api.wynncraft.com/v3/guild/prefix/{}"
GUILD_NAME = "Empire of TKW"

# Discord関連 (環境変数から読み込み)
TRACKING_CHANNEL_ID = int(os.getenv('NOTIFICATION_CHANNEL_ID', 0))

# コマンドの許可ユーザーリスト（IDで管理）
AUTHORIZED_USER_IDS = [1062535250099589120]  # 必要ならここに追加
SPAM_TARGET_USER_IDS = [
    472416402255511555,
    1062535250099589120,
    861793764120330250
]

# Embed用の色設定
EMBED_COLOR_GOLD = 0xFFD700
EMBED_COLOR_GREEN = 0x00FF00
EMBED_COLOR_BLUE = 0x0000FF

# テリトリーリソースと絵文字の対応表
RESOURCE_EMOJIS = {
    "EMERALDS": "<:wynn_emerald:1395325625522458654>",
    "ORE": "<:wynn_ore:1395325664508383262>",
    "WOOD": "<:wynn_wood:1395325681440788621>",
    "FISH": "<:wynn_fish:1395325644899881011>",
    "CROPS": "<:wynn_crop:1395325604806656032>"
}

RESTRICTION = 1132652296635961385

# ここにランク→ロールIDのマッピング
RANK_ROLE_ID_MAP = {
    "Owner": 1240476623090876516,
    "Chief": 1138142855517446144,
    "Strategist": 1166030526214320178,
    "Captain": 1166035741189607494,
    "Recruiter": 1166036063081467914,
    "Recruit": 1166036348050886657,
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
    await interaction.response.send_message(
        f"このコマンドは {mentions} のみ使用できます！",
        ephemeral=True
    )
