import os
import sys
import logging
import logging.handlers
from logging import Logger

def get_logger(name: str) -> Logger:
    """
    loggerを設定する

    Args:
        name(str): 基本的に__name__を代入すること
    Returns:
        Logger : Loggerインスタンス
    """
    # ./log/ディレクトリに保存
    log_dir = './log/'
    if not os.path.isdir(log_dir):
        os.makedirs(log_dir)

    # ログの出力フォーマット
    dt_fmt = '%Y-%m-%d %H:%M:%S'
    formatter = logging.Formatter('[{asctime}] [{levelname:<8}] {name}: {message}', dt_fmt, style='{')

    # ファイルハンドラーの設定
    # 32MB * 5個のログを保存する
    file_handler = logging.handlers.RotatingFileHandler(
        filename=f'{log_dir}app.log',
        encoding='utf-8',
        maxBytes=32 * 1024 * 1024,
        backupCount=5,
        mode='w'
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)

    # 標準出力ハンドラーの設定
    # ログはすべて標準出力に流す
    stream_handler = logging.StreamHandler(
        stream=sys.stdout
    )
    stream_handler.setLevel(logging.INFO)
    stream_handler.setFormatter(formatter)

    # loggerの設定
    logging.basicConfig(level=logging.NOTSET, handlers=[file_handler, stream_handler])
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    logging.getLogger('discord.http').setLevel(logging.INFO)

    return logger
