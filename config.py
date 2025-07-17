import os

# Wynncraft API関連
NORI_GUILD_API_URL = "https://nori.fish/api/guild/{}"
NORI_PLAYER_API_URL = "https://nori.fish/api/player/{}"
WYNN_PLAYER_API_URL = "https://api.wynncraft.com/v3/player/{}"
WYNN_GUILD_BY_NAME_API_URL = "https://api.wynncraft.com/v3/guild/{}"
WYNN_GUILD_BY_PREFIX_API_URL = "https://api.wynncraft.com/v3/guild/prefix/{}"

# Discord関連 (環境変数から読み込み)
GUILD_ID_INT = int(os.getenv('GUILD_ID', 0))
TRACKING_CHANNEL_ID = int(os.getenv('NOTIFICATION_CHANNEL_ID', 0))

# Embed用の色設定
EMBED_COLOR_GOLD = 0xFFD700
EMBED_COLOR_GREEN = 0x00FF00
EMBED_COLOR_BLUE = 0x0000FF

# テリトリーリソースと絵文字の対応表
RESOURCE_EMOJIS = {
    "EMERALD": "<:wynn_emerald:1395325625522458654>",
    "ORE": "<:wynn_ore:1395325664508383262>",
    "WOOD": "<:wynn_wood:1395325681440788621>",
    "FISH": "<:wynn_fish:1395325644899881011>",
    "CROP": "<:wynn_crop:1395325604806656032>"
}
