import os
import logging
import psycopg2

logger = logging.getLogger(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL")  # Renderの環境変数利用

def get_conn():
    return psycopg2.connect(DATABASE_URL, sslmode='require')

def create_table():
    conn = get_conn()
    with conn.cursor() as cur:
        # ギルドのSeasonal Ratingテーブルを作成
        cur.execute("""
            CREATE TABLE IF NOT EXISTS guild_seasonal_ratings (
                guild_name TEXT PRIMARY KEY,
                guild_prefix TEXT NOT NULL,
                seasonal_rating INTEGER NOT NULL DEFAULT 0,
                season_number INTEGER NOT NULL DEFAULT 0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # インデックスを作成（レーティング順でのソート用）
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_guild_seasonal_ratings_rating 
            ON guild_seasonal_ratings(seasonal_rating DESC)
        """)
        
        conn.commit()
    conn.close()
    logger.info("全テーブルを作成/確認しました")

def upsert_guild_seasonal_rating(guild_name: str, guild_prefix: str, seasonal_rating: int, season_number: int):
    """ギルドのSeasonal Ratingを挿入または更新"""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO guild_seasonal_ratings 
                (guild_name, guild_prefix, seasonal_rating, season_number, updated_at)
                VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (guild_name) 
                DO UPDATE SET 
                    guild_prefix = EXCLUDED.guild_prefix,
                    seasonal_rating = EXCLUDED.seasonal_rating,
                    season_number = EXCLUDED.season_number,
                    updated_at = CURRENT_TIMESTAMP
            """, (guild_name, guild_prefix, seasonal_rating, season_number))
            conn.commit()
            logger.info(f"ギルド {guild_name}({guild_prefix}) のSeasonal Rating {seasonal_rating} を保存しました")
    except Exception as e:
        logger.error(f"ギルドSeasonal Rating保存エラー: {e}", exc_info=True)
        conn.rollback()
    finally:
        conn.close()

def get_seasonal_rating_leaderboard(limit: int = 100, offset: int = 0):
    """Seasonal Ratingのリーダーボードを取得"""
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
                WHERE seasonal_rating > 0
                ORDER BY seasonal_rating DESC 
                LIMIT %s OFFSET %s
            """, (limit, offset))
            return cur.fetchall()
    except Exception as e:
        logger.error(f"Seasonal Ratingリーダーボード取得エラー: {e}", exc_info=True)
        return []
    finally:
        conn.close()

def get_guild_count():
    """登録されているギルドの総数を取得"""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM guild_seasonal_ratings WHERE seasonal_rating > 0")
            result = cur.fetchone()
            return result[0] if result else 0
    except Exception as e:
        logger.error(f"ギルド数取得エラー: {e}", exc_info=True)
        return 0
    finally:
        conn.close()