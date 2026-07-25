"""Phase G verification: proves the APScheduler wiring itself works (job
registered -> fires at the scheduled wall-clock time -> calls the right step
function with the right AppContext), without waiting until the next day.
Schedules the 3 steps 20s apart over the next ~90s using second-precision
CronTrigger (production only needs minute precision, see app.core.scheduler).

Since this typically runs right after scripts.smoke_test_daily_run in the
same day, the steps are expected to short-circuit via has_step_run (already
published today) — which also doubles as a live check that the idempotency
guard and the scheduler compose correctly.

Usage: python -m scripts.smoke_test_scheduler
"""

import asyncio
import datetime
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
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

    now = datetime.datetime.now()
    t1 = now + datetime.timedelta(seconds=15)
    t2 = now + datetime.timedelta(seconds=35)
    t3 = now + datetime.timedelta(seconds=55)
    logger.info(
        "Maintenant=%s | tech_post@%s news@%s quiz@%s",
        now.strftime("%H:%M:%S"),
        t1.strftime("%H:%M:%S"),
        t2.strftime("%H:%M:%S"),
        t3.strftime("%H:%M:%S"),
    )

    scheduler = AsyncIOScheduler(timezone=settings.tz)
    scheduler.add_job(
        run_tech_post_step,
        CronTrigger(second=t1.second, minute=t1.minute, hour=t1.hour, timezone=settings.tz),
        args=[ctx],
        id="tech_post",
    )
    scheduler.add_job(
        run_news_step,
        CronTrigger(second=t2.second, minute=t2.minute, hour=t2.hour, timezone=settings.tz),
        args=[ctx],
        id="news_digest",
    )
    scheduler.add_job(
        run_quiz_step,
        CronTrigger(second=t3.second, minute=t3.minute, hour=t3.hour, timezone=settings.tz),
        args=[ctx],
        id="quiz",
    )
    scheduler.start()

    await asyncio.sleep(70)

    scheduler.shutdown(wait=False)
    conn.close()
    logger.info("Smoke test scheduler terminé.")


if __name__ == "__main__":
    asyncio.run(run())
