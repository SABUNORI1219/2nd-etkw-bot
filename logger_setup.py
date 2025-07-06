# logger_setup.py
import logging
import sys

def setup_logger():
    """
    Bot全体のロガーを設定する関数。
    """
    # フォーマッターを定義（Dernal Botの形式を参考にします）
    dt_fmt = '%Y-%m-%d %H:%M:%S'
    formatter = logging.Formatter('[{asctime}] [{levelname:<8}] {name}: {message}', dt_fmt, style='{')

    # ハンドラーを定義（コンソールにログを出力）
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    # discordライブラリ自体のロガーにもハンドラーを適用
    discord_logger = logging.getLogger('discord')
    discord_logger.setLevel(logging.INFO)
    discord_logger.addHandler(handler)
    
    # 私たちのBot用のロガーにもハンドラーを適用
    # これにより、logging.getLogger(__name__)でどこからでも呼び出せる
    my_bot_logger = logging.getLogger()
    my_bot_logger.setLevel(logging.INFO)
    my_bot_logger.addHandler(handler)

    print("--- ロガーのセットアップが完了しました ---")
