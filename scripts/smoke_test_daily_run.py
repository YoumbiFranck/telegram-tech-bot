"""Phase G verification: runs the three daily steps directly (bypassing the
scheduler) twice in a row. The second pass should skip all three steps
(already done today) — proving the idempotency guard that protects against
double-publishing after a crash/restart.

Usage: python -m scripts.smoke_test_daily_run
"""

import asyncio
import logging

from telegram import Bot

from app.core.logging import setup_logging
from app.core.settings import load_settings
from app.generation.claude_client import ClaudeClient
from app.jobs.context import build_context
from app.jobs.daily_run import run_news_step, run_quiz_step, run_tech_post_step
from app.persistence.db import connect
from app.persistence.repository import Repository
from app.publishing.telegram_publisher import TelegramPublisher

logger = logging.getLogger(__name__)


async def run() -> None:
    settings = load_settings()
    setup_logging(settings.log_level, settings.log_dir)

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

    for pass_num in (1, 2):
        logger.info("=== Passage %d/2 ===", pass_num)
        await run_tech_post_step(ctx)
        await run_news_step(ctx)
        await run_quiz_step(ctx)

    conn.close()
    logger.info("Smoke test daily_run terminé.")


if __name__ == "__main__":
    asyncio.run(run())
