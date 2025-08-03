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
        cur.execute('''
            CREATE TABLE IF NOT EXISTS linked_members (
                mcid TEXT PRIMARY KEY,
                discord_id BIGINT,
                ingame_rank TEXT NOT NULL
            );
        ''')
        conn.commit()
    conn.close()
    logger.info("guild_raid_historyテーブルを作成/確認しました")

def insert_history(raid_name, clear_time, member):
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO guild_raid_history (raid_name, clear_time, member)
                VALUES (%s, %s, %s)
            """, (raid_name, clear_time, member))
            conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"insert_history failed: {raid_name}, {clear_time}, {member}, error={e}")
    
def reset_player_raid_count(player, raid_name, count):
    conn = get_conn()
    with conn.cursor() as cur:
        # まず、該当player/raid_nameの履歴を削除
        cur.execute(
            "DELETE FROM guild_raid_history WHERE member=%s AND raid_name=%s",
            (player, raid_name)
        )
        now = datetime.utcnow()
        # 指定回数だけinsert
        if count > 0:
            execute_values(
                cur,
                "INSERT INTO guild_raid_history (raid_name, clear_time, member) VALUES %s",
                [(raid_name, now, player)] * count
            )
        conn.commit()
    conn.close()

from datetime import datetime

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
            dt = None
            if isinstance(date_from, str):
                if len(date_from) == 10:  # YYYY-MM-DD
                    try:
                        dt = datetime.strptime(date_from, "%Y-%m-%d")
                    except Exception:
                        pass
                elif len(date_from) == 7:  # YYYY-MM
                    try:
                        dt = datetime.strptime(date_from, "%Y-%m")
                    except Exception:
                        pass
                elif len(date_from) == 4:  # YYYY
                    try:
                        dt = datetime.strptime(date_from, "%Y")
                    except Exception:
                        pass
                # 不正な形式は無視
            elif isinstance(date_from, datetime):
                dt = date_from
            # datetime型に変換できた場合だけフィルタ
            if dt is not None:
                sql += " AND clear_time >= %s"
                params.append(dt)
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

def add_member(mcid: str, discord_id: int, rank: str) -> bool:
    """新しいメンバーを登録する"""
    sql = "INSERT INTO linked_members (mcid, discord_id, ingame_rank) VALUES (%s, %s, %s) ON CONFLICT(mcid) DO UPDATE SET discord_id = EXCLUDED.discord_id, ingame_rank = EXCLUDED.ingame_rank"
    conn = get_conn()
    if conn is None: return False
    try:
        with conn.cursor() as cur:
            cur.execute(sql, (mcid, discord_id, rank))
            conn.commit()
        return True
    except Exception as e:
        logger.error(f"[DB Handler] メンバーの追加/更新に失敗: {e}")
        return False
    finally:
        if conn: conn.close()

def remove_member(mcid: str = None, discord_id: int = None) -> bool:
    """メンバーを登録解除する"""
    if not mcid and not discord_id: return False
    
    sql = "DELETE FROM linked_members WHERE "
    params = []
    if mcid:
        sql += "mcid = %s"
        params.append(mcid)
    else:
        sql += "discord_id = %s"
        params.append(discord_id)
        
    conn = get_conn()
    if conn is None: return False
    try:
        with conn.cursor() as cur:
            cur.execute(sql, tuple(params))
            conn.commit()
        return cur.rowcount > 0 # 1行以上削除されたらTrue
    except Exception as e:
        logger.error(f"[DB Handler] メンバーの削除に失敗: {e}")
        return False
    finally:
        if conn: conn.close()

def get_member(mcid: str = None, discord_id: int = None) -> dict | None:
    """単一のメンバー情報を取得する"""
    if not mcid and not discord_id: return None
    sql = "SELECT mcid, discord_id, ingame_rank FROM linked_members WHERE "
    params = []
    if mcid:
        sql += "mcid = %s"
        params.append(mcid)
    else:
        sql += "discord_id = %s"
        params.append(discord_id)
        
    conn = get_conn()
    if conn is None: return None
    try:
        with conn.cursor() as cur:
            cur.execute(sql, tuple(params))
            record = cur.fetchone()
            if record:
                return {"mcid": record[0], "discord_id": record[1], "rank": record[2]}
            return None
    except Exception as e:
        logger.error(f"[DB Handler] メンバーの取得に失敗: {e}")
        return None
    finally:
        if conn: conn.close()

def get_linked_members_page(page: int = 1, per_page: int = 10, rank_filter: str = None) -> tuple[list, int]:
    """登録済みメンバーのリストをページ指定で取得する"""
    offset = (page - 1) * per_page
    conn = get_conn()
    if conn is None: return [], 0

    base_sql = "FROM linked_members"
    params = []
    if rank_filter:
        base_sql += " WHERE ingame_rank = %s"
        params.append(rank_filter)

    count_sql = "SELECT COUNT(*) " + base_sql
    data_sql = "SELECT mcid, discord_id, ingame_rank " + base_sql + " ORDER BY ingame_rank, mcid LIMIT %s OFFSET %s"
    params.extend([per_page, offset])
    
    results, total_count = [], 0
    try:
        with conn.cursor() as cur:
            cur.execute(count_sql, [rank_filter] if rank_filter else [])
            total_count = cur.fetchone()[0]
            
            cur.execute(data_sql, params)
            results = [{"mcid": r[0], "discord_id": r[1], "rank": r[2]} for r in cur.fetchall()]
    except Exception as e:
        logger.error(f"[DB Handler] メンバーリストの取得に失敗: {e}")
    finally:
        if conn: conn.close()
        
    total_pages = (total_count + per_page - 1) // per_page
    return results, total_pages

def get_all_linked_members(rank_filter: str = None) -> list:
    conn = get_conn()
    if conn is None: return []
    base_sql = "FROM linked_members"
    params = []
    if rank_filter:
        base_sql += " WHERE ingame_rank = %s"
        params.append(rank_filter)
    data_sql = "SELECT mcid, discord_id, ingame_rank " + base_sql + " ORDER BY ingame_rank, mcid"
    try:
        with conn.cursor() as cur:
            cur.execute(data_sql, params)
            results = [{"mcid": r[0], "discord_id": r[1], "rank": r[2]} for r in cur.fetchall()]
    except Exception as e:
        logger.error(f"[DB Handler] 全件メンバーリスト取得に失敗: {e}")
        return []
    finally:
        if conn: conn.close()
    return results
