import logging
import sys

def setup_logger():
    """
    Bot全体のロガーを設定する関数。
    """
    # 既存ハンドラの状態に関わらず、標準出力へのストリームを強制設定
    root_logger = logging.getLogger()
    for h in list(root_logger.handlers):
        root_logger.removeHandler(h)

    dt_fmt = '%Y-%m-%d %H:%M:%S'
    formatter = logging.Formatter('[{asctime}] [{levelname:<8}] {name}: {message}', dt_fmt, style='{')
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    
    # Render環境でのログバッファリング問題を解決
    handler.setLevel(logging.INFO)
    handler.flush = lambda: sys.stdout.flush()  # 強制フラッシュ

    # ルートロガーだけにハンドラをつける
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(handler)

    discord_logger = logging.getLogger('discord')
    discord_logger.setLevel(logging.INFO)
