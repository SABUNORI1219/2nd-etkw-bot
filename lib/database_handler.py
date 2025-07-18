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
        conn = get_db_connection()
        if conn is None:
            return
        with conn.cursor() as cursor:
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS player_raid_history (
                id SERIAL PRIMARY KEY,
                player_uuid TEXT NOT NULL,
                player_name TEXT NOT NULL,
                raid_name TEXT NOT NULL,
                new_raid_count INTEGER NOT NULL,
                server TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            ''')
            conn.commit()
            logger.info("--- [DB Handler] 'player_raid_history'テーブルのセットアップが完了しました。")
    except Exception as e:
        logger.error(f"--- [DB Handler] データベースのセットアップ中にエラー: {e}")
    finally:
        if conn:
            conn.close()

def set_setting(key: str, value: str):
    """
    設定情報をbot_settingsテーブルに保存します（存在すれば更新）。
    """
    sql = """
    INSERT INTO bot_settings (key, value)
    VALUES (%s, %s)
    ON CONFLICT (key) DO UPDATE
    SET value = EXCLUDED.value
    """
    conn = get_db_connection()
    if conn is None:
        return
    try:
        with conn.cursor() as cur:
            cur.execute(sql, (key, value))
            CREATE TABLE IF NOT EXISTS bot_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            conn.commit()
    except Exception as e:
        logger.error(f"[DB Handler] 設定の保存に失敗: {e}")
    finally:
        conn.close()

def add_raid_history(history_entries: list):
    """複数のレイドクリア履歴をデータベースに一括で追加する"""
    if not history_entries: return
    try:
        conn = get_db_connection()
        if conn is None:
            return
        with conn.cursor() as cursor:
            cursor.executemany('''
            INSERT INTO player_raid_history (player_uuid, player_name, raid_name, new_raid_count, server)
            VALUES (%s, %s, %s, %s, %s)
            ''', history_entries)
            conn.commit()
            logger.info(f"--- [DB Handler] {len(history_entries)}件のレイド履歴をデータベースに追加しました。")
    except Exception as e:
        logger.error(f"--- [DB Handler] レイド履歴の追加中にエラー: {e}")
    finally:
        if conn:
            conn.close()

def get_raid_counts(player_uuid: str, since_date: datetime) -> list:
    """
    指定されたプレイヤーの、指定された日付以降のレイドクリア回数を集計して返す。
    """
    sql = "SELECT raid_name, COUNT(*) FROM player_raid_history WHERE player_uuid = %s AND timestamp >= %s GROUP BY raid_name"
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
