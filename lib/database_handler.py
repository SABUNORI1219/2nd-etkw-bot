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

            cursor.execute('''
            ALTER TABLE player_raid_history ADD COLUMN IF NOT EXISTS processed BOOLEAN DEFAULT FALSE
            ''')
            logger.info("--- [DB Handler] 'player_raid_history'テーブルのセットアップが完了しました。")

            cursor.execute('''
            CREATE TABLE IF NOT EXISTS bot_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            ''')
            logger.info("--- [DB Handler] 'bot_settings'テーブルのセットアップが完了しました。")

            conn.commit()
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
            conn.commit()
    except Exception as e:
        logger.error(f"[DB Handler] 設定の保存に失敗: {e}")
    finally:
        conn.close()

def get_setting(key: str) -> str | None:
    """設定情報をbot_settingsテーブルから取得します。"""
    sql = "SELECT value FROM bot_settings WHERE key = %s"
    conn = get_db_connection()
    if conn is None:
        return None

    result = None
    try:
        with conn.cursor() as cur:
            cur.execute(sql, (key,))
            # fetchone()は、結果がなければNone、あれば(値,)というタプルを返す
            record = cur.fetchone()
            if record:
                result = record[0]
    except Exception as e:
        logger.error(f"[DB Handler] 設定の取得に失敗: {e}")
    finally:
        if conn:
            conn.close()
    
    return result

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

def get_unprocessed_raid_history() -> list:
    """まだ処理・通知されていないレイド履歴を取得する"""
    sql = "SELECT id, player_uuid, player_name, raid_name, server, timestamp FROM player_raid_history WHERE processed = FALSE ORDER BY timestamp ASC"
    conn = get_db_connection()
    if conn is None: return []
    results = []
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
            results = cur.fetchall()
    except Exception as e:
        logger.error(f"--- [DB Handler] 未処理レイド履歴の取得中にエラー: {e}")
    finally:
        if conn: conn.close()
    return results

def mark_raid_history_as_processed(ids: list):
    """指定されたIDのレイド履歴を「処理済み」としてマークする"""
    if not ids: return
    # executemanyで使うために、リストの各要素をタプルに変換
    id_tuples = [(id,) for id in ids]
    sql = "UPDATE player_raid_history SET processed = TRUE WHERE id = %s"
    conn = get_db_connection()
    if conn is None: return
    try:
        with conn.cursor() as cur:
            cur.executemany(sql, id_tuples)
            conn.commit()
            logger.info(f"--- [DB Handler] {len(ids)}件のレイド履歴を処理済みにマークしました。")
    except Exception as e:
        logger.error(f"--- [DB Handler] レイド履歴の更新中にエラー: {e}")
    finally:
        if conn: conn.close()

def get_raid_history_page(page: int = 1, per_page: int = 10) -> tuple[list, int]:
    """
    player_raid_historyテーブルから、ページ指定で履歴を取得する。
    戻り値は (履歴のリスト, 総ページ数)。
    """
    offset = (page - 1) * per_page
    conn = get_db_connection()
    if conn is None:
        return [], 0

    results = []
    total_count = 0
    try:
        with conn.cursor() as cur:
            # まず、総件数を取得
            cur.execute("SELECT COUNT(DISTINCT timestamp) FROM player_raid_history")
            count_result = cur.fetchone()
            if count_result:
                total_count = count_result[0]

            # 1ページ分のデータを取得 (タイムスタンプでグループ化し、最新のものから)
            sql = """
            SELECT raid_name, timestamp, STRING_AGG(player_name, ', ')
            FROM player_raid_history
            GROUP BY raid_name, timestamp
            ORDER BY timestamp DESC
            LIMIT %s OFFSET %s
            """
            cur.execute(sql, (per_page, offset))
            results = cur.fetchall()
            
    except Exception as e:
        logger.error(f"[DB Handler] レイド履歴のページ取得に失敗: {e}")
    finally:
        if conn:
            conn.close()
    
    total_pages = (total_count + per_page - 1) // per_page
    return results, total_pages
