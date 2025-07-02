import os
import psycopg2
from datetime import datetime

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
            group_id VARCHAR(255) NOT NULL,
            user_id BIGINT NOT NULL,
            player_uuid VARCHAR(255) NOT NULL,
            raid_type VARCHAR(50) NOT NULL,
            cleared_at TIMESTAMP NOT NULL DEFAULT current_timestamp
        );
    """)
    conn.commit()
    cur.close()
    conn.close()
    print("データベースのセットアップが完了しました。")

def add_raid_records(records):
    """複数のレイド記録をデータベースに追加する"""
    conn = get_db_connection()
    cur = conn.cursor()
    sql = """
        INSERT INTO clear_records (group_id, user_id, player_uuid, raid_type, cleared_at)
        VALUES (%s, %s, %s, %s, %s)
    """
    cur.executemany(sql, records)
    conn.commit()
    cur.close()
    conn.close()

def get_raid_counts(player_uuid, since_date):
    """指定されたプレイヤーのレイドクリア回数を集計する"""
    conn = get_db_connection()
    cur = conn.cursor()
    sql = """
        SELECT raid_type, COUNT(*)
        FROM clear_records
        WHERE player_uuid = %s AND cleared_at >= %s
        GROUP BY raid_type
    """
    cur.execute(sql, (player_uuid, since_date))
    results = cur.fetchall()
    cur.close()
    conn.close()
    return results
