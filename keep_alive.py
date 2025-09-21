from flask import Flask
from threading import Thread
import os

app = Flask('')

@app.route('/')
def home():
    """Renderからのアクセスに応答し、サービスをアクティブに保つためのページ"""
    return "I'm alive"

def run():
    """Flaskサーバーを起動する"""
    # Renderが指定するホストとポートで実行
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))

def keep_alive():
    """Webサーバーを別スレッドで起動する"""
    server_thread = Thread(target=run)
    server_thread.start()
