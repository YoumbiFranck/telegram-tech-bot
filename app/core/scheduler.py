import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.jobs.context import AppContext
from app.jobs.daily_run import run_news_step, run_quiz_step, run_tech_post_step

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

    return scheduler
