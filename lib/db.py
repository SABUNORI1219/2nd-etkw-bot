import os
import logging
import psycopg2
from psycopg2.extras import execute_values
from datetime import datetime, timedelta
from collections import defaultdict

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
        
        # uuid カラムを追加（既存の場合はスキップ）
        cur.execute('''
            ALTER TABLE linked_members 
            ADD COLUMN IF NOT EXISTS uuid TEXT;
        ''')
        
        cur.execute('''
            CREATE TABLE IF NOT EXISTS last_join_cache (
                mcid TEXT PRIMARY KEY,
                last_join TEXT
            );
        ''')
        cur.execute('''
            CREATE TABLE IF NOT EXISTS guild_territory_state (
                guild_prefix TEXT,
                territory_name TEXT,
                acquired TIMESTAMP,
                lost TIMESTAMP,
                from_guild TEXT,
                to_guild TEXT,
                PRIMARY KEY (guild_prefix, territory_name)
            );
        ''')
        cur.execute('''
            CREATE TABLE IF NOT EXISTS applications (
                id SERIAL PRIMARY KEY,
                mcid TEXT NOT NULL,
                discord_id BIGINT NOT NULL,
                channel_id BIGINT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        ''')
        cur.execute('''
            CREATE TABLE IF NOT EXISTS playtime_cache (
                mcid TEXT PRIMARY KEY,
                playtime REAL NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        ''')
        conn.commit()
    conn.close()
    logger.info("全テーブルを作成/確認しました")

def upsert_guild_territory_state(guild_territory_history):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            rows = []
            for g, tdict in guild_territory_history.items():
                for t, info in tdict.items():
                    acquired = info.get("acquired")
                    lost = info.get("lost")
                    from_guild = info.get("from_guild")
                    to_guild = info.get("to_guild")
                    rows.append((
                        g, t,
                        acquired if isinstance(acquired, datetime) else None,
                        lost if isinstance(lost, datetime) else None,
                        from_guild, to_guild
                    ))
            if rows:
                execute_values(
                    cur,
                    """
                    INSERT INTO guild_territory_state (guild_prefix, territory_name, acquired, lost, from_guild, to_guild)
                    VALUES %s
                    ON CONFLICT (guild_prefix, territory_name)
                    DO UPDATE SET acquired = EXCLUDED.acquired, lost = EXCLUDED.lost, from_guild = EXCLUDED.from_guild, to_guild = EXCLUDED.to_guild
                    """,
                    rows
                )
            conn.commit()
    except Exception as e:
        logger.error(f"upsert_guild_territory_state failed: {e}")
    finally:
        if conn: conn.close()

def get_guild_territory_state():
    conn = get_conn()
    result = defaultdict(dict)
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT guild_prefix, territory_name, acquired, lost, from_guild, to_guild FROM guild_territory_state
            """)
            for g, t, acq, lost, from_guild, to_guild in cur.fetchall():
                result[g][t] = {
                    "acquired": acq,
                    "lost": lost,
                    "from_guild": from_guild,
                    "to_guild": to_guild
                }
    except Exception as e:
        logger.error(f"get_guild_territory_state failed: {e}")
    finally:
        if conn: conn.close()
    return result

def insert_history(raid_name, clear_time, member):
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            # レイド履歴を挿入
            cur.execute("""
                INSERT INTO guild_raid_history (raid_name, clear_time, member)
                VALUES (%s, %s, %s)
            """, (raid_name, clear_time, member))
            
            # 2ヶ月以上前のデータを削除（メモリ効率を考慮してLIMIT付きで分割削除）
            two_months_ago = datetime.utcnow() - timedelta(days=60)
            cur.execute("""
                DELETE FROM guild_raid_history 
                WHERE clear_time < %s
            """, (two_months_ago,))
            
            deleted_count = cur.rowcount
            if deleted_count > 0:
                logger.info(f"[DB Cleanup] 2ヶ月以上前のレイド履歴を{deleted_count}件削除しました")
            
            conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"insert_history failed: {raid_name}, {clear_time}, {member}, error={e}")

def adjust_player_raid_count(player, raid_name, count):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            if count > 0:
                now = datetime.utcnow()
                from psycopg2.extras import execute_values
                execute_values(
                    cur,
                    "INSERT INTO guild_raid_history (raid_name, clear_time, member) VALUES %s",
                    [(raid_name, now, player)] * count
                )
                
                # データ追加時にクリーンアップを実行
                two_months_ago = now - timedelta(days=60)
                cur.execute("""
                    DELETE FROM guild_raid_history 
                    WHERE clear_time < %s
                """, (two_months_ago,))
                
                deleted_count = cur.rowcount
                if deleted_count > 0:
                    logger.info(f"[DB Cleanup] 2ヶ月以上前のレイド履歴を{deleted_count}件削除しました")
                    
            elif count < 0:
                cur.execute(
                    """
                    DELETE FROM guild_raid_history
                    WHERE id IN (
                        SELECT id FROM guild_raid_history
                        WHERE raid_name = %s AND member = %s
                        ORDER BY clear_time DESC
                        LIMIT %s
                    )
                    """,
                    (raid_name, player, abs(count))
                )
            conn.commit()
    finally:
        if conn:
            conn.close()

def fetch_history(raid_name=None, date_from=None, date_to=None):
    conn = get_conn()
    with conn.cursor() as cur:
        sql = "SELECT id, raid_name, clear_time, member FROM guild_raid_history WHERE 1=1"
        params = []
        if raid_name:
            sql += " AND raid_name = %s"
            params.append(raid_name)
        if date_from:
            dt = None
            if isinstance(date_from, str):
                if len(date_from) == 10:
                    try:
                        dt = datetime.strptime(date_from, "%Y-%m-%d")
                    except Exception:
                        pass
                elif len(date_from) == 7:
                    try:
                        dt = datetime.strptime(date_from, "%Y-%m")
                    except Exception:
                        pass
                elif len(date_from) == 4:
                    try:
                        dt = datetime.strptime(date_from, "%Y")
                    except Exception:
                        pass
            elif isinstance(date_from, datetime):
                dt = date_from
            if dt is not None:
                sql += " AND clear_time >= %s"
                params.append(dt)
        if date_to:
            dt_to = None
            if isinstance(date_to, str):
                if len(date_to) == 10:
                    try:
                        dt_to = datetime.strptime(date_to, "%Y-%m-%d")
                    except Exception:
                        pass
                elif len(date_to) == 7:
                    try:
                        dt_to = datetime.strptime(date_to, "%Y-%m")
                    except Exception:
                        pass
                elif len(date_to) == 4:
                    try:
                        dt_to = datetime.strptime(date_to, "%Y")
                    except Exception:
                        pass
            elif isinstance(date_to, datetime):
                dt_to = date_to
            if dt_to is not None:
                sql += " AND clear_time < %s"
                params.append(dt_to)
        sql += " ORDER BY clear_time DESC"
        cur.execute(sql, params)
        rows = cur.fetchall()
    conn.close()
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
    conn = get_conn()
    with conn.cursor() as cur:
        threshold = datetime.utcnow() - timedelta(minutes=minutes)
        cur.execute("DELETE FROM player_server_log WHERE timestamp < %s", (threshold,))
        conn.commit()
    conn.close()
    logger.info(f"{minutes}分より前のplayer_server_logを削除しました")

def cleanup_old_raid_history(days=60):
    """
    指定した日数より古いレイド履歴を削除する関数
    デフォルトは60日（2ヶ月）
    """
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            threshold = datetime.utcnow() - timedelta(days=days)
            cur.execute("DELETE FROM guild_raid_history WHERE clear_time < %s", (threshold,))
            deleted_count = cur.rowcount
            conn.commit()
            logger.info(f"[DB Cleanup] {days}日より前のレイド履歴を{deleted_count}件削除しました")
            return deleted_count
    except Exception as e:
        logger.error(f"[DB Cleanup] cleanup_old_raid_history failed: {e}")
        return 0
    finally:
        if conn:
            conn.close()

def add_member(mcid: str, discord_id: int, rank: str) -> bool:
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
        return cur.rowcount > 0
    except Exception as e:
        logger.error(f"[DB Handler] メンバーの削除に失敗: {e}")
        return False
    finally:
        if conn: conn.close()

def get_member(mcid: str = None, discord_id: int = None) -> dict | None:
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

def set_discord_id_null(mcid: str = None, discord_id: int = None) -> bool:
    if not mcid and not discord_id:
        return False
    sql = "UPDATE linked_members SET discord_id = NULL WHERE "
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
        return cur.rowcount > 0
    except Exception as e:
        logger.error(f"[DB Handler] discord_id NULL化に失敗: {e}")
        return False
    finally:
        if conn: conn.close()

def upsert_last_join_cache(last_join_list):
    if not last_join_list:
        return
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            execute_values(
                cur,
                """
                INSERT INTO last_join_cache (mcid, last_join)
                VALUES %s
                ON CONFLICT (mcid) DO UPDATE SET last_join = EXCLUDED.last_join
                """,
                last_join_list
            )
            conn.commit()
    except Exception as e:
        logger.error(f"[DB Handler] upsert_last_join_cache failed: {e}")
    finally:
        if conn:
            conn.close()

def get_last_join_cache_for_members(mcid_list):
    """
    指定したmcidリストについてlast_join_cacheからデータを取得
    戻り値: {mcid: last_join}
    """
    if not mcid_list:
        return {}
    conn = get_conn()
    result = {}
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT mcid, last_join FROM last_join_cache
                WHERE last_join IS NOT NULL AND mcid = ANY(%s)
            """, (mcid_list,))
            for mcid, last_join in cur.fetchall():
                result[mcid] = last_join
    except Exception as e:
        logger.error(f"[DB Handler] get_last_join_cache_for_members failed: {e}")
    finally:
        if conn: conn.close()
    return result

def get_recently_active_members(minutes_threshold=20):
    """
    最終ログインから指定分数以内のメンバーのMCIDとUUIDを取得
    戻り値: [(mcid, uuid), ...]
    """
    conn = get_conn()
    result = []
    try:
        with conn.cursor() as cur:
            # last_joinが文字列として保存されていると仮定して、現在時刻からminutes_threshold分前を計算
            threshold_time = datetime.utcnow() - timedelta(minutes=minutes_threshold)
            threshold_str = threshold_time.strftime('%Y-%m-%dT%H:%M:%S.%fZ')
            
            cur.execute("""
                SELECT lm.mcid, lm.uuid 
                FROM linked_members lm
                JOIN last_join_cache ljc ON lm.mcid = ljc.mcid
                WHERE ljc.last_join IS NOT NULL 
                AND ljc.last_join >= %s
            """, (threshold_str,))
            
            for mcid, uuid in cur.fetchall():
                result.append((mcid, uuid))
                
        logger.debug(f"[DB] 最近アクティブなメンバー {len(result)}人を取得（{minutes_threshold}分以内）")
    except Exception as e:
        logger.error(f"[DB Handler] get_recently_active_members failed: {e}")
    finally:
        if conn: conn.close()
    return result

def update_member_uuid(mcid: str, uuid: str):
    """linked_membersテーブルのUUIDを更新"""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE linked_members 
                SET uuid = %s 
                WHERE mcid = %s
            """, (uuid, mcid))
            conn.commit()
            if cur.rowcount > 0:
                logger.debug(f"[DB] UUID更新: {mcid} -> {uuid}")
    except Exception as e:
        logger.error(f"[DB Handler] update_member_uuid failed: {e}")
    finally:
        if conn: conn.close()

def update_multiple_member_uuids(mcid_uuid_list):
    """複数のメンバーのUUIDを一括更新"""
    if not mcid_uuid_list:
        return
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            execute_values(
                cur,
                """
                UPDATE linked_members 
                SET uuid = data.uuid
                FROM (VALUES %s) AS data(mcid, uuid)
                WHERE linked_members.mcid = data.mcid
                """,
                mcid_uuid_list,
                template=None,
                page_size=100
            )
            conn.commit()
            logger.info(f"[DB] UUID一括更新: {cur.rowcount}件")
    except Exception as e:
        logger.error(f"[DB Handler] update_multiple_member_uuids failed: {e}")
    finally:
        if conn: conn.close()

def save_application(mcid: str, discord_id: int, channel_id: int):
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("INSERT INTO applications (mcid, discord_id, channel_id) VALUES (%s, %s, %s)", (mcid, discord_id, channel_id))
        conn.commit()
    conn.close()

def get_pending_applications():
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("SELECT mcid, discord_id, channel_id FROM applications")
        return cur.fetchall()
    conn.close()

def delete_application_by_discord_id(discord_id: int):
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("DELETE FROM applications WHERE discord_id = %s", (discord_id,))
        conn.commit()
    conn.close()

def upsert_playtime_cache(playtime_list):
    """
    playtime_list: [(mcid, playtime), ...]
    """
    if not playtime_list:
        return
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            execute_values(
                cur,
                """
                INSERT INTO playtime_cache (mcid, playtime, updated_at)
                VALUES %s
                ON CONFLICT (mcid) DO UPDATE SET 
                    playtime = EXCLUDED.playtime,
                    updated_at = EXCLUDED.updated_at
                """,
                [(mcid, playtime, datetime.utcnow()) for mcid, playtime in playtime_list]
            )
            conn.commit()
    except Exception as e:
        logger.error(f"[DB Handler] upsert_playtime_cache failed: {e}")
    finally:
        if conn:
            conn.close()

def get_playtime_cache_for_members(mcid_list):
    """
    指定したmcidリストについてplaytime_cacheからデータを取得
    戻り値: {mcid: playtime}
    """
    if not mcid_list:
        return {}
    conn = get_conn()
    result = {}
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT mcid, playtime FROM playtime_cache
                WHERE mcid = ANY(%s)
            """, (mcid_list,))
            for mcid, playtime in cur.fetchall():
                result[mcid] = playtime
    except Exception as e:
        logger.error(f"[DB Handler] get_playtime_cache_for_members failed: {e}")
    finally:
        if conn: conn.close()
    return result

def cleanup_non_guild_members_raid_history(current_guild_uuids):
    """
    現在のギルドメンバーのUUID以外のレイド履歴を削除する
    """
    if not current_guild_uuids:
        return 0
    
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            # guild_raid_historyテーブルにmember_uuid列があることを前提
            # ない場合はmember_nameで対応する必要がある
            cur.execute("""
                SELECT member_name FROM guild_raid_history 
                WHERE member_name NOT IN (
                    SELECT mcid FROM linked_members WHERE uuid = ANY(%s)
                )
                GROUP BY member_name
            """, (current_guild_uuids,))
            non_guild_members = [row[0] for row in cur.fetchall()]
            
            if non_guild_members:
                cur.execute("""
                    DELETE FROM guild_raid_history 
                    WHERE member_name = ANY(%s)
                """, (non_guild_members,))
                deleted_count = cur.rowcount
                conn.commit()
                logger.info(f"[DB Cleanup] ギルド外メンバーのレイド履歴を{deleted_count}件削除: {non_guild_members}")
                return deleted_count
            else:
                logger.info("[DB Cleanup] ギルド外メンバーのレイド履歴削除対象なし")
                return 0
    except Exception as e:
        logger.error(f"[DB Cleanup] cleanup_non_guild_members_raid_history failed: {e}")
        return 0
    finally:
        if conn: conn.close()

def update_raid_history_member_names(uuid_to_name_mapping):
    """
    UUIDに対応する現在の名前でレイド履歴のmember_nameを更新する
    """
    if not uuid_to_name_mapping:
        return 0
    
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            updated_count = 0
            for uuid, current_name in uuid_to_name_mapping.items():
                # linked_membersから古い名前を取得
                cur.execute("SELECT mcid FROM linked_members WHERE uuid = %s", (uuid,))
                old_names = [row[0] for row in cur.fetchall()]
                
                # 古い名前と現在の名前が異なる場合、レイド履歴を更新
                for old_name in old_names:
                    if old_name != current_name:
                        cur.execute("""
                            UPDATE guild_raid_history 
                            SET member_name = %s 
                            WHERE member_name = %s
                        """, (current_name, old_name))
                        if cur.rowcount > 0:
                            updated_count += cur.rowcount
                            logger.info(f"[DB Cleanup] レイド履歴の名前更新: {old_name} -> {current_name} ({cur.rowcount}件)")
            
            conn.commit()
            if updated_count > 0:
                logger.info(f"[DB Cleanup] レイド履歴の名前更新完了: 合計{updated_count}件")
            return updated_count
    except Exception as e:
        logger.error(f"[DB Cleanup] update_raid_history_member_names failed: {e}")
        return 0
    finally:
        if conn: conn.close()

