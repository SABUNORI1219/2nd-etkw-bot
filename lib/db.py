import os
import logging
import psycopg2
from psycopg2.extras import execute_values
from datetime import datetime, timedelta

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
                raid_name TEXT,
                clear_time TIMESTAMP,
                member TEXT
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
        cur.execute("""
            CREATE TABLE IF NOT EXISTS player_server_log (
                player_name TEXT NOT NULL,
                timestamp TIMESTAMP NOT NULL,
                server TEXT,
                PRIMARY KEY (player_name, timestamp)
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS bot_config (
                key TEXT PRIMARY KEY,
                value TEXT
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

def insert_history(raid_name, clear_time, member):
    sql = """
    INSERT INTO guild_raid_history 
    (raid_name, clear_time, member)
    VALUES (?, ?, ?)
    """
    params = (raid_name, clear_time, member)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(sql, params)
        conn.commit()
    conn.close()

def reset_player_raid_count(player, raid_name, count):
    with sqlite3.connect(DB_PATH) as conn:
        # まず、該当player/raid_nameの履歴を削除
        conn.execute(
            "DELETE FROM guild_raid_history WHERE member=? AND raid_name=?",
            (player, raid_name)
        )
        # 指定回数だけinsert
        for _ in range(count):
            conn.execute(
                "INSERT INTO guild_raid_history (raid_name, clear_time, member) VALUES (?, datetime('now'), ?)",
                (raid_name, player)
            )
        conn.commit()

def fetch_history(raid_name=None, date_from=None):
    """
    ギルドレイド履歴を取得する。
    - raid_name: レイド名で絞り込み（Noneなら全件）
    - date_from: 指定日時以降で絞り込み（Noneなら全期間）。
      'YYYY-MM-DD', 'YYYY-MM', 'YYYY' の文字列も対応。
    戻り値: (id, raid_name, clear_time, member(str)) のリスト
    """
    conn = get_conn()
    with conn.cursor() as cur:
        sql = "SELECT id, raid_name, clear_time, member FROM guild_raid_history WHERE 1=1"
        params = []
        if raid_name:
            sql += " AND raid_name = %s"
            params.append(raid_name)
        if date_from:
            # 年・月単位など柔軟に対応
            if isinstance(date_from, str):
                # YYYY-MM-DD
                if len(date_from) == 10:
                    sql += " AND to_char(clear_time, 'YYYY-MM-DD') = %s"
                    params.append(date_from)
                # YYYY-MM
                elif len(date_from) == 7:
                    sql += " AND to_char(clear_time, 'YYYY-MM') = %s"
                    params.append(date_from)
                # YYYY
                elif len(date_from) == 4:
                    sql += " AND to_char(clear_time, 'YYYY') = %s"
                    params.append(date_from)
                else:
                    # 形式不明→何もしない
                    pass
            else:
                # datetime型もしくはそれ以外（>=検索）
                sql += " AND clear_time >= %s"
                params.append(date_from)
        sql += " ORDER BY clear_time DESC"
        cur.execute(sql, params)
        rows = cur.fetchall()
    conn.close()
    # memberはstr型で返す
    result = []
    for row in rows:
        member = row[3]
        result.append((row[0], row[1], row[2], str(member)))
    return result
    
def insert_server_log(player_name, timestamp, server):
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO player_server_log (player_name, timestamp, server)
            VALUES (%s, %s, %s)
            ON CONFLICT (player_name, timestamp)
            DO UPDATE SET server = EXCLUDED.server
        """, (player_name, timestamp, server))
        conn.commit()
    conn.close()

def get_last_server_before(player_name, event_time):
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("""
            SELECT server FROM player_server_log
            WHERE player_name = %s AND timestamp < %s
            ORDER BY timestamp DESC
            LIMIT 1
        """, (player_name, event_time))
        row = cur.fetchone()
    conn.close()
    return row[0] if row else None

def set_config(key, value):
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO bot_config (key, value)
            VALUES (%s, %s)
            ON CONFLICT (key)
            DO UPDATE SET value = EXCLUDED.value
        """, (key, value))
        conn.commit()
    conn.close()

def get_config(key):
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("SELECT value FROM bot_config WHERE key = %s", (key,))
        row = cur.fetchone()
    conn.close()
    return row[0] if row else None

def cleanup_old_server_logs(minutes=5):
    """player_server_logのminutes分より前のデータを削除"""
    conn = get_conn()
    with conn.cursor() as cur:
        threshold = datetime.utcnow() - timedelta(minutes=minutes)
        cur.execute("DELETE FROM player_server_log WHERE timestamp < %s", (threshold,))
        conn.commit()
    conn.close()
    logger.info(f"{minutes}分より前のplayer_server_logを削除しました")
