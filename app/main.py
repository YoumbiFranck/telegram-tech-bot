import argparse
import asyncio
import logging
import signal

from telegram import Bot

from app.core.logging import setup_logging
from app.core.scheduler import build_scheduler
from app.core.settings import load_settings
from app.generation.claude_client import ClaudeClient
from app.jobs.context import build_context
from app.persistence.db import connect
from app.persistence.repository import Repository
from app.publishing.telegram_publisher import TelegramPublisher

logger = logging.getLogger(__name__)


async def run_forever(settings) -> None:
    conn = connect(settings.data_dir / "app.db")
    repo = Repository(conn)
    client = ClaudeClient(
        binary_path=settings.claude_binary_path, timeout_seconds=settings.claude_timeout_seconds
    )
    bot = Bot(token=settings.telegram_bot_token)
    publisher = TelegramPublisher(
        bot=bot,
        chat_id=settings.telegram_chat_id,
        media_dir=settings.media_dir,
        send_delay_seconds=settings.send_delay_seconds,
    )
    ctx = build_context(settings, client, repo, publisher)

    scheduler = build_scheduler(ctx)
    scheduler.start()
    logger.info(
        "Scheduler démarré (tech_post=%r, news=%r, quiz=%r, tz=%s)",
        settings.schedule_tech_post_cron,
        settings.schedule_news_cron,
        settings.schedule_quiz_cron,
        settings.tz,
    )

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop_event.set)

    await stop_event.wait()
    logger.info("Signal d'arrêt reçu, arrêt du scheduler...")
    scheduler.shutdown(wait=False)
    conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="telegram-tech-bot")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="valide la configuration et le démarrage sans envoyer de message",
    )
    args = parser.parse_args()

    settings = load_settings()
    setup_logging(settings.log_level, settings.log_dir)

    logger.info("Configuration chargée (chat_id=%s, tz=%s)", settings.telegram_chat_id, settings.tz)

    if args.dry_run:
        logger.info("Dry-run: configuration valide, arrêt sans démarrer le scheduler.")
        return

    asyncio.run(run_forever(settings))


if __name__ == "__main__":
    main()
