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

    # 可能なら標準出力を行バッファリングに再構成（Python 3.7+）
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(line_buffering=True)
    except Exception:
        pass

    # 1レコード毎に確実にflushするハンドラ
    class FlushStreamHandler(logging.StreamHandler):
        def emit(self, record):
            super().emit(record)
            try:
                self.flush()
            except Exception:
                try:
                    sys.stdout.flush()
                except Exception:
                    pass

    dt_fmt = '%Y-%m-%d %H:%M:%S'
    formatter = logging.Formatter('[{asctime}] [{levelname:<8}] {name}: {message}', dt_fmt, style='{')
    handler = FlushStreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    
    # Render環境でのログバッファリング問題を解決
    handler.setLevel(logging.INFO)

    # ルートロガーだけにハンドラをつける
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(handler)

    discord_logger = logging.getLogger('discord')
    discord_logger.setLevel(logging.INFO)

    # warningsもloggingへ取り込む
    logging.captureWarnings(True)
