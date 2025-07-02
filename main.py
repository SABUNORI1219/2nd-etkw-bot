import discord
import os
import psycopg2
from flask import Flask
from threading import Thread
from urllib.parse import urlparse

# --- Database Connection ---
DATABASE_URL = os.getenv('DATABASE_URL')

def setup_database():
    # データベースに接続
    conn = psycopg2.connect(DATABASE_URL)
    # カーソル（操作を行うためのもの）を取得
    cur = conn.cursor()
    
    # クリア記録を保存するテーブルがなければ作成するSQL
    cur.execute("""
        CREATE TABLE IF NOT EXISTS clear_records (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            user_name VARCHAR(255) NOT NULL,
            content_name VARCHAR(255) NOT NULL,
            cleared_at TIMESTAMP NOT NULL DEFAULT current_timestamp
        );
    """)
    
    # 変更を確定
    conn.commit()
    # 接続を閉じる
    cur.close()
    conn.close()
    print("データベースのセットアップが完了しました。")

# --- Discord Botの基本設定 ---
TOKEN = os.getenv('DISCORD_TOKEN')

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

@client.event
async def on_ready():
    print(f'ログイン成功: {client.user}')

@client.event
async def on_message(message):
    if message.author == client.user:
        return
    if message.content.startswith('!hello'):
        await message.channel.send('Hello from a 24/7 bot!')

# --- 24時間稼働させるためのWebサーバー設定 ---
app = Flask('')

@app.route('/')
def home():
    return "I'm alive"

def run_web_server():
    # Renderが指定するポートでWebサーバーを起動
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))

def keep_alive():
    # Webサーバーをバックグラウンドで実行
    server_thread = Thread(target=run_web_server)
    server_thread.start()

# --- Botの起動 ---
if TOKEN:
    print("--- Botを起動します ---")
    keep_alive()  # Webサーバーを起動
    client.run(TOKEN) # Botを起動
else:
    print("エラー: DISCORD_TOKENが設定されていません。")
