import os
import psycopg2
import sqlite3
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

# 環境変数からデータベースURLを取得
DATABASE_URL = os.getenv('DATABASE_URL')

def get_db_connection():
    """データベースへの接続を確立して返す"""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    except psycopg2.OperationalError as e:
        logger.error(f"データベース接続エラー: {e}")
        return None

def setup_database():
    """データベースとテーブルをセットアップする"""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            # 既存のテーブル (もしあれば)
            # cursor.execute('''CREATE TABLE IF NOT EXISTS ...''')

            # ▼▼▼【新しいテーブルを追加】▼▼▼
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS player_raid_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                player_uuid TEXT NOT NULL,
                player_name TEXT NOT NULL,
                raid_name TEXT NOT NULL,
                new_raid_count INTEGER NOT NULL,
                server TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            ''')
            logger.info("--- [DB Handler] 'player_raid_history'テーブルのセットアップが完了しました。")
    except Exception as e:
        logger.error(f"--- [DB Handler] データベースのセットアップ中にエラー: {e}")

def add_raid_history(history_entries: list):
    """複数のレイドクリア履歴をデータベースに一括で追加する"""
    if not history_entries: return
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.executemany('''
            INSERT INTO player_raid_history (player_uuid, player_name, raid_name, new_raid_count, server)
            VALUES (?, ?, ?, ?, ?)
            ''', history_entries)
            conn.commit()
            logger.info(f"--- [DB Handler] {len(history_entries)}件のレイド履歴をデータベースに追加しました。")
    except Exception as e:
        logger.error(f"--- [DB Handler] レイド履歴の追加中にエラー: {e}")

def get_raid_counts(player_uuid: str, since_date: datetime) -> list:
    """
    指定されたプレイヤーの、指定された日付以降のレイドクリア回数を集計して返す。
    """
    sql = "SELECT raid_type, COUNT(*) FROM clear_records WHERE player_uuid = %s AND cleared_at >= %s GROUP BY raid_type"
    conn = get_db_connection()
    if conn is None:
        return []

    results = []
    try:
        with conn.cursor() as cur:
            cur.execute(sql, (player_uuid, since_date))
            results = cur.fetchall()
    except Exception as e:
        logger.error(f"--- [DB Handler] レイド回数の取得中にエラー: {e}")
    finally:
        if conn:
            conn.close()
    return results
