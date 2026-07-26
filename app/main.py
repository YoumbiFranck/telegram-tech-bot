import argparse
import asyncio
import logging
import signal
import sqlite3

from telegram import Bot

from app.core.logging import setup_logging
from app.core.scheduler import build_scheduler
from app.core.settings import Settings, load_settings
from app.generation.claude_client import ClaudeClient
from app.jobs.context import AppContext, build_context
from app.jobs.daily_run import run_news_step, run_quiz_step, run_tech_post_step
from app.jobs.backup_job import run_backup_step
from app.persistence.db import connect
from app.persistence.repository import Repository
from app.publishing.telegram_publisher import TelegramPublisher

logger = logging.getLogger(__name__)


async def _run_backup_step_async(ctx: AppContext, force: bool = False) -> None:
    # La sauvegarde n'a pas de notion d'idempotence à contourner — force est
    # accepté seulement pour garder une signature uniforme entre les jobs.
    run_backup_step(ctx)


RUN_NOW_JOBS = {
    "tech_post": run_tech_post_step,
    "news": run_news_step,
    "quiz": run_quiz_step,
    "backup": _run_backup_step_async,
}


def build_app_context(settings: Settings) -> tuple[sqlite3.Connection, AppContext]:
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
    return conn, build_context(settings, client, repo, publisher)


async def run_forever(settings: Settings) -> None:
    conn, ctx = build_app_context(settings)

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


async def run_once(settings: Settings, job_name: str, force: bool = False) -> None:
    """Exécute un seul job immédiatement puis quitte — pour tester sans
    attendre l'heure planifiée. Ne démarre pas le scheduler. force=True
    ignore l'idempotence du jour (sinon un job déjà passé aujourd'hui est
    simplement sauté, comme en fonctionnement normal)."""
    conn, ctx = build_app_context(settings)
    logger.info("Exécution manuelle du job %r (force=%s)...", job_name, force)
    await RUN_NOW_JOBS[job_name](ctx, force=force)
    logger.info("Job %r terminé.", job_name)
    conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="telegram-tech-bot")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="valide la configuration et le démarrage sans envoyer de message",
    )
    parser.add_argument(
        "--run-now",
        choices=sorted(RUN_NOW_JOBS),
        help="exécute ce job immédiatement (test), puis quitte sans démarrer le scheduler",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="avec --run-now, ignore l'idempotence du jour (republie même si déjà fait aujourd'hui)",
    )
    args = parser.parse_args()

    settings = load_settings()
    setup_logging(settings.log_level, settings.log_dir)

    logger.info("Configuration chargée (chat_id=%s, tz=%s)", settings.telegram_chat_id, settings.tz)

    if args.dry_run:
        logger.info("Dry-run: configuration valide, arrêt sans démarrer le scheduler.")
        return

    if args.run_now:
        asyncio.run(run_once(settings, args.run_now, force=args.force))
        return

    asyncio.run(run_forever(settings))


if __name__ == "__main__":
    main()
