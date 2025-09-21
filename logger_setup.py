import logging
import sys

def setup_logger():
    """
    Bot全体のロガーを設定する関数。
    """
    # 既にハンドラが追加されていれば何もしない
    root_logger = logging.getLogger()
    if root_logger.hasHandlers():
        return

    dt_fmt = '%Y-%m-%d %H:%M:%S'
    formatter = logging.Formatter('[{asctime}] [{levelname:<8}] {name}: {message}', dt_fmt, style='{')
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    # ルートロガーだけにハンドラをつける
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(handler)

    discord_logger = logging.getLogger('discord')
    discord_logger.setLevel(logging.INFO)
