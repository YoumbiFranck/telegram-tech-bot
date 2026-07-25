from app.core.heartbeat import send_heartbeat
from app.jobs.context import AppContext


def run_heartbeat_step(ctx: AppContext) -> None:
    if not ctx.settings.uptime_kuma_push_url:
        return
    send_heartbeat(ctx.settings.uptime_kuma_push_url)
