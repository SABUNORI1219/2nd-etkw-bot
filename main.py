import discord
import os

TOKEN = os.getenv('DISCORD_TOKEN')

# ▼▼▼【最重要】この3行を確認・修正してください ▼▼▼
intents = discord.Intents.default()
intents.message_content = True  # メッセージの内容を読むための権限を有効化
client = discord.Client(intents=intents) # clientに設定を渡す
# ▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲

@client.event
async def on_ready():
    # 成功すれば、このメッセージがRenderのログに表示されます
    print(f'ログイン成功: {client.user}')

@client.event
async def on_message(message):
    if message.author == client.user:
        return
    if message.content.startswith('!hello'):
        await message.channel.send('Hello from Render!')

# トークンが設定されているか確認（推奨）
if TOKEN is None:
    print("エラー: 環境変数 'DISCORD_TOKEN' が設定されていません。")
else:
    print("Botを起動します...")
    client.run(TOKEN)
