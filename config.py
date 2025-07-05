import os

# Wynncraft API関連
NORI_GUILD_API_URL = "https://nori.fish/api/guild/{}"
NORI_PLAYER_API_URL = "https://nori.fish/api/player/{}"
WYNN_PLAYER_API_URL = "https://api.wynncraft.com/v3/player/{}"
WYNN_GUILD_API_URL = "https://api.wynncraft.com/v3/guild/{}" #Guild Name必須

# 追跡対象のレイド名 (APIで使われる内部名)
RAID_TYPES = ["tna", "tcc", "nol", "nog"]

# Discord関連 (環境変数から読み込み)
GUILD_ID_INT = int(os.getenv('GUILD_ID', 0))
TRACKING_CHANNEL_ID = int(os.getenv('NOTIFICATION_CHANNEL_ID', 0))

# Embed用の色設定
EMBED_COLOR_GOLD = 0xFFD700
EMBED_COLOR_GREEN = 0x00FF00
EMBED_COLOR_BLUE = 0x0000FF
