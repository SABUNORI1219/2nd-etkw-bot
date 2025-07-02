# database.py

import os
import psycopg2

DATABASE_URL = os.getenv('DATABASE_URL')

def get_db_connection():
    """データベースへの接続を取得する"""
    return psycopg2.connect(DATABASE_URL)

def setup_database():
    """テーブルの初期設定を行う"""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS clear_records (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            user_name VARCHAR(255) NOT NULL,
            content_name VARCHAR(255) NOT NULL,
            cleared_at TIMESTAMP NOT NULL DEFAULT current_timestamp
        );
    """)
    conn.commit()
    cur.close()
    conn.close()
    print("データベースのセットアップが完了しました。")

# 今後、データを追加する関数などもここに追加していく
# def add_clear_record(user_id, user_name, content_name):
#     ...
