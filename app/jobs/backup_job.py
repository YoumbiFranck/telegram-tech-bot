import logging

from app.jobs.context import AppContext
from app.persistence.backup import backup_database, prune_old_backups

logger = logging.getLogger(__name__)

BACKUP_RETENTION_COUNT = 14


def run_backup_step(ctx: AppContext) -> None:
    db_path = ctx.settings.data_dir / "app.db"
    try:
        backup_database(db_path, ctx.settings.backups_dir)
        prune_old_backups(ctx.settings.backups_dir, keep_last=BACKUP_RETENTION_COUNT)
    except Exception as exc:
        logger.error("Échec de la sauvegarde SQLite: %s", exc)
