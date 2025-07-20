import os
import logging
import psycopg2
from psycopg2.extras import execute_values
from datetime import datetime

logger = logging.getLogger(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL")  # Renderの環境変数利用

def get_conn():
    return psycopg2.connect(DATABASE_URL, sslmode='require')

def create_table():
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS guild_raid_history (
                id SERIAL PRIMARY KEY,
                raid_name TEXT NOT NULL,
                clear_time TIMESTAMP NOT NULL,
                party_members TEXT[] NOT NULL,
                server_name TEXT NOT NULL,
                trust_score INTEGER NOT NULL
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS raid_clear_cache (
                player_name TEXT NOT NULL,
                raid_name TEXT NOT NULL,
                clear_count INTEGER NOT NULL,
                PRIMARY KEY (player_name, raid_name)
            );
        """)
        conn.commit()
    conn.close()
    logger.info("guild_raid_historyテーブルを作成/確認しました")

def get_prev_count(player_name, raid_name):
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT clear_count FROM raid_clear_cache WHERE player_name = %s AND raid_name = %s",
            (player_name, raid_name)
        )
        row = cur.fetchone()
    conn.close()
    return row[0] if row else None

def set_prev_count(player_name, raid_name, count):
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO raid_clear_cache (player_name, raid_name, clear_count)
            VALUES (%s, %s, %s)
            ON CONFLICT (player_name, raid_name)
            DO UPDATE SET clear_count = EXCLUDED.clear_count
        """, (player_name, raid_name, count))
        conn.commit()
    conn.close()

def insert_history(raid_name, clear_time, party_members, server_name, trust_score):
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO guild_raid_history (raid_name, clear_time, party_members, server_name, trust_score)
            VALUES (%s, %s, %s, %s, %s)
        """, (raid_name, clear_time, party_members, server_name, trust_score))
        conn.commit()
    conn.close()
    logger.info(f"履歴保存: {raid_name} {clear_time} Party: {party_members}")

def fetch_history(raid_name=None, date_from=None):
    conn = get_conn()
    with conn.cursor() as cur:
        sql = "SELECT * FROM guild_raid_history WHERE 1=1"
        params = []
        if raid_name:
            sql += " AND raid_name = %s"
            params.append(raid_name)
        if date_from:
            sql += " AND clear_time >= %s"
            params.append(date_from)
        cur.execute(sql, params)
        rows = cur.fetchall()
    conn.close()
    return rows
