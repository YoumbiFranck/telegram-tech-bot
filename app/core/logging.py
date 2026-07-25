import logging
import logging.handlers
from pathlib import Path

FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"

# httpx/httpcore log the full request URL at INFO level, which embeds the
# Telegram bot token (https://api.telegram.org/bot<TOKEN>/...). Keep these
# quiet so the token never lands in plaintext logs.
_NOISY_LOGGERS = ("httpx", "httpcore")


def setup_logging(level: str, log_dir: Path) -> None:
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()

    formatter = logging.Formatter(FORMAT)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    root.addHandler(stream_handler)

    file_handler = logging.handlers.RotatingFileHandler(
        log_dir / "app.log", maxBytes=5_000_000, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    for logger_name in _NOISY_LOGGERS:
        logging.getLogger(logger_name).setLevel(logging.WARNING)
