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
