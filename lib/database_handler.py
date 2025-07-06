import os
import psycopg2
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
    """
    データベースに 'clear_records' テーブルが存在しない場合に作成する。
    """
    logger.info("--- [DB Handler] データベースのテーブルをセットアップします...")
    conn = get_db_connection()
    if conn is None:
        return
        
    try:
        with conn.cursor() as cur:
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
        logger.info("--- [DB Handler] テーブルのセットアップが完了しました。")
    except Exception as e:
        logger.error(f"--- [DB Handler] テーブルセットアップ中にエラー: {e}")
    finally:
        if conn:
            conn.close()

def add_raid_records(records: list):
    """
    複数のレイドクリア記録をデータベースに一括で保存する。
    records: (group_id, user_id, player_uuid, raid_type, cleared_at) のタプルのリスト
    """
    sql = "INSERT INTO clear_records (group_id, user_id, player_uuid, raid_type, cleared_at) VALUES (%s, %s, %s, %s, %s)"
    conn = get_db_connection()
    if conn is None:
        return

    try:
        with conn.cursor() as cur:
            cur.executemany(sql, records)
            conn.commit()
        logger.info(f"--- [DB Handler] {len(records)}件のレイド記録をデータベースに保存しました。")
    except Exception as e:
        logger.error(f"--- [DB Handler] レイド記録の保存中にエラー: {e}")
    finally:
        if conn:
            conn.close()

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
