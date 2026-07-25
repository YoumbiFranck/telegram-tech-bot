import argparse
import logging

from app.core.logging import setup_logging
from app.core.settings import load_settings

logger = logging.getLogger(__name__)


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

    logger.info("Scheduler non encore implémenté (phase suivante) — arrêt.")


if __name__ == "__main__":
    main()
