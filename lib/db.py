import os
import logging
import psycopg2
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL")  # Renderの環境変数利用

def get_conn():
    return psycopg2.connect(DATABASE_URL, sslmode='require')

def create_table():
    conn = get_conn()
    with conn.cursor() as cur:
        # 既存テーブルを削除（データ収集問題解決のため）
        cur.execute("DROP TABLE IF EXISTS guild_seasonal_ratings CASCADE")
        logger.info("既存のguild_seasonal_ratingsテーブルを削除しました")
        
        # ギルドのSeasonal Ratingテーブルを作成（シーズンごと）
        cur.execute("""
            CREATE TABLE guild_seasonal_ratings (
                guild_name TEXT NOT NULL,
                guild_prefix TEXT NOT NULL,
                season_number INTEGER NOT NULL,
                seasonal_rating INTEGER NOT NULL DEFAULT 0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (guild_name, season_number)
            )
        """)
        
        # インデックスを作成（シーズン別レーティング順でのソート用）
        cur.execute("""
            CREATE INDEX idx_guild_seasonal_ratings_season_rating 
            ON guild_seasonal_ratings(season_number, seasonal_rating DESC)
        """)
        
        # ギルドプレフィックス用のインデックス
        cur.execute("""
            CREATE INDEX idx_guild_seasonal_ratings_prefix 
            ON guild_seasonal_ratings(guild_prefix)
        """)
        
        # 最新シーズン管理テーブル
        cur.execute("""
            CREATE TABLE IF NOT EXISTS current_season_info (
                id INTEGER PRIMARY KEY DEFAULT 1,
                current_season INTEGER NOT NULL,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT single_row CHECK (id = 1)
            )
        """)
        
        conn.commit()
    conn.close()
    logger.info("全テーブルを新規作成しました")

def upsert_guild_seasonal_rating(guild_name: str, guild_prefix: str, season_number: int, seasonal_rating: int):
    """ギルドの特定シーズンのSeasonal Ratingを挿入または更新"""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            # 既存レコードをチェック
            cur.execute("""
                SELECT seasonal_rating FROM guild_seasonal_ratings 
                WHERE guild_name = %s AND season_number = %s
            """, (guild_name, season_number))
            existing = cur.fetchone()
            
            cur.execute("""
                INSERT INTO guild_seasonal_ratings 
                (guild_name, guild_prefix, season_number, seasonal_rating, updated_at)
                VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (guild_name, season_number) 
                DO UPDATE SET 
                    guild_prefix = EXCLUDED.guild_prefix,
                    seasonal_rating = EXCLUDED.seasonal_rating,
                    updated_at = CURRENT_TIMESTAMP
            """, (guild_name, guild_prefix, season_number, seasonal_rating))
            conn.commit()
            
            action = "更新" if existing else "新規作成"
            logger.debug(f"ギルド {guild_name}({guild_prefix}) のS{season_number} Rating {seasonal_rating} を{action}しました")
    except Exception as e:
        logger.error(f"ギルドSeasonal Rating保存エラー: {e}", exc_info=True)
        conn.rollback()
        raise  # エラーを再発生させて呼び出し元に通知
    finally:
        conn.close()

def get_seasonal_rating_leaderboard(season_number: int, limit: int = 100, offset: int = 0):
    """指定シーズンのSeasonal Ratingリーダーボードを取得"""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT 
                    guild_name, 
                    guild_prefix, 
                    seasonal_rating, 
                    season_number,
                    updated_at
                FROM guild_seasonal_ratings 
                WHERE season_number = %s AND seasonal_rating > 0
                ORDER BY seasonal_rating DESC 
                LIMIT %s OFFSET %s
            """, (season_number, limit, offset))
            return cur.fetchall()
    except Exception as e:
        logger.error(f"S{season_number} Ratingリーダーボード取得エラー: {e}", exc_info=True)
        return []
    finally:
        conn.close()

def get_guild_count_by_season(season_number: int):
    """指定シーズンの登録されているギルド数を取得"""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) FROM guild_seasonal_ratings 
                WHERE season_number = %s AND seasonal_rating > 0
            """, (season_number,))
            result = cur.fetchone()
            return result[0] if result else 0
    except Exception as e:
        logger.error(f"S{season_number} ギルド数取得エラー: {e}", exc_info=True)
        return 0
    finally:
        conn.close()

def get_available_seasons():
    """データベースに保存されているシーズン一覧を取得"""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT DISTINCT season_number 
                FROM guild_seasonal_ratings 
                WHERE seasonal_rating > 0
                ORDER BY season_number DESC
            """)
            return [row[0] for row in cur.fetchall()]
    except Exception as e:
        logger.error(f"利用可能シーズン取得エラー: {e}", exc_info=True)
        return []
    finally:
        conn.close()

def get_guild_seasonal_data(guild_name: str):
    """ギルドの全シーズンデータを取得"""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT 
                    season_number,
                    seasonal_rating,
                    guild_prefix,
                    updated_at
                FROM guild_seasonal_ratings 
                WHERE guild_name = %s AND seasonal_rating > 0
                ORDER BY season_number DESC
            """, (guild_name,))
            return cur.fetchall()
    except Exception as e:
        logger.error(f"ギルド {guild_name} データ取得エラー: {e}", exc_info=True)
        return []
    finally:
        conn.close()

def update_current_season(season_number: int):
    """現在のシーズン番号を更新"""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO current_season_info (id, current_season, last_updated)
                VALUES (1, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (id)
                DO UPDATE SET 
                    current_season = EXCLUDED.current_season,
                    last_updated = CURRENT_TIMESTAMP
            """, (season_number,))
            conn.commit()
            logger.info(f"現在のシーズンをSeason {season_number}に更新しました")
    except Exception as e:
        logger.error(f"現在シーズン更新エラー: {e}", exc_info=True)
        conn.rollback()
    finally:
        conn.close()

def get_current_season():
    """現在のシーズン番号を取得"""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT current_season FROM current_season_info WHERE id = 1")
            result = cur.fetchone()
            return result[0] if result else None
    except Exception as e:
        logger.error(f"現在シーズン取得エラー: {e}", exc_info=True)
        return None
    finally:
        conn.close()

def is_season_completed(season_number: int):
    """指定シーズンの収集が完了しているかチェック"""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            # そのシーズンで24時間以内に更新されたギルドがあるかチェック
            cur.execute("""
                SELECT COUNT(*) FROM guild_seasonal_ratings 
                WHERE season_number = %s AND updated_at > %s
            """, (season_number, datetime.now() - timedelta(hours=24)))
            result = cur.fetchone()
            recent_updates = result[0] if result else 0
            
            # 過去シーズンで最近更新があったら「未完了」とみなす
            current_season = get_current_season()
            if current_season and season_number < current_season and recent_updates > 0:
                return False
            
            # 過去シーズンで最近更新がなければ「完了済み」
            if current_season and season_number < current_season:
                return True
                
            return False
    except Exception as e:
        logger.error(f"シーズン完了状況確認エラー: {e}", exc_info=True)
        return False
    finally:
        conn.close()