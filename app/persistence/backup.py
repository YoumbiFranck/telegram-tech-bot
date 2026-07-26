import datetime
import logging
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)


def backup_database(db_path: Path, backups_dir: Path) -> Path:
    """Copie cohérente de la base (VACUUM INTO — fonctionne même si l'appli
    écrit en même temps, contrairement à une simple copie de fichier)."""
    backups_dir.mkdir(parents=True, exist_ok=True)
    today = datetime.date.today().isoformat()
    backup_path = backups_dir / f"app-{today}.db"
    # VACUUM INTO refuse d'écraser un fichier existant — pertinent si on
    # relance la sauvegarde manuellement le même jour (--run-now backup).
    backup_path.unlink(missing_ok=True)

    conn = sqlite3.connect(db_path)
    try:
        conn.execute("VACUUM INTO ?", (str(backup_path),))
    finally:
        conn.close()

    logger.info("Sauvegarde SQLite créée: %s", backup_path)
    return backup_path


def prune_old_backups(backups_dir: Path, keep_last: int = 14) -> None:
    backups = sorted(backups_dir.glob("app-*.db"))
    for path in backups[:-keep_last] if len(backups) > keep_last else []:
        path.unlink()
        logger.info("Sauvegarde supprimée (rétention dépassée): %s", path)
