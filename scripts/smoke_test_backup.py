"""Phase J verification: creates a real backup of data/app.db via VACUUM INTO,
then exercises the retention pruning logic.

Usage: python -m scripts.smoke_test_backup
"""

import logging
import sqlite3

from app.core.logging import setup_logging
from app.core.settings import load_settings
from app.persistence.backup import backup_database, prune_old_backups

logger = logging.getLogger(__name__)


def run() -> None:
    settings = load_settings()
    setup_logging(settings.log_level, settings.log_dir)

    db_path = settings.data_dir / "app.db"
    backup_path = backup_database(db_path, settings.backups_dir)

    conn = sqlite3.connect(backup_path)
    tables = [
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    ]
    conn.close()
    logger.info("Sauvegarde vérifiée, tables présentes: %s", tables)

    prune_old_backups(settings.backups_dir, keep_last=14)
    remaining = sorted(p.name for p in settings.backups_dir.glob("app-*.db"))
    logger.info("Sauvegardes restantes après purge: %s", remaining)


if __name__ == "__main__":
    run()
