# config.py
import os

# Wynncraft関連の定数
GUILD_NAME = "Empire of TKW"
GUILD_API_URL = f"https://nori.fish/api/guild/{GUILD_NAME.replace(' ', '%20')}"
PLAYER_API_URL = "https://api.wynncraft.com/v3/player/{}"
RAID_TYPES = ["tna", "tcc", "nol", "nog"]

# Discord関連の定数
EMBED_COLOR_GOLD = 0xFFD700
EMBED_COLOR_GREEN = 0x00FF00
EMBED_COLOR_BLUE = 0x0000FF

# サーバーIDを環境変数から取得
GUILD_ID_INT = int(os.getenv('GUILD_ID', 0))
