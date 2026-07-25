import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.jobs.backup_job import run_backup_step
from app.jobs.context import AppContext
from app.jobs.daily_run import run_news_step, run_quiz_step, run_tech_post_step
from app.jobs.heartbeat_job import run_heartbeat_step

logger = logging.getLogger(__name__)

# Si le conteneur était arrêté au moment prévu (reboot, restart), on laisse
# jusqu'à 1h à APScheduler pour rattraper le job plutôt que de le sauter en
# silence — c'est ce qui fournit la "reprise automatique" côté scheduler.
MISFIRE_GRACE_TIME_SECONDS = 3600


def build_scheduler(ctx: AppContext) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=ctx.settings.tz)

    scheduler.add_job(
        run_tech_post_step,
        CronTrigger.from_crontab(ctx.settings.schedule_tech_post_cron, timezone=ctx.settings.tz),
        args=[ctx],
        id="tech_post",
        misfire_grace_time=MISFIRE_GRACE_TIME_SECONDS,
    )
    scheduler.add_job(
        run_news_step,
        CronTrigger.from_crontab(ctx.settings.schedule_news_cron, timezone=ctx.settings.tz),
        args=[ctx],
        id="news_digest",
        misfire_grace_time=MISFIRE_GRACE_TIME_SECONDS,
    )
    scheduler.add_job(
        run_quiz_step,
        CronTrigger.from_crontab(ctx.settings.schedule_quiz_cron, timezone=ctx.settings.tz),
        args=[ctx],
        id="quiz",
        misfire_grace_time=MISFIRE_GRACE_TIME_SECONDS,
    )
    scheduler.add_job(
        run_backup_step,
        CronTrigger.from_crontab(ctx.settings.schedule_backup_cron, timezone=ctx.settings.tz),
        args=[ctx],
        id="backup",
        misfire_grace_time=MISFIRE_GRACE_TIME_SECONDS,
    )

    if ctx.settings.uptime_kuma_push_url:
        scheduler.add_job(
            run_heartbeat_step,
            IntervalTrigger(seconds=ctx.settings.heartbeat_interval_seconds),
            args=[ctx],
            id="heartbeat",
            misfire_grace_time=60,
        )
        logger.info(
            "Heartbeat Uptime Kuma activé (intervalle=%ds)", ctx.settings.heartbeat_interval_seconds
        )
    else:
        logger.info("Pas d'UPTIME_KUMA_PUSH_URL configurée, heartbeat désactivé.")

    return scheduler
