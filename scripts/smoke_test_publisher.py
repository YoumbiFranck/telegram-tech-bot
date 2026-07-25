"""Phase C verification: exercises the typed publishing layer end-to-end on the
configured Telegram chat (test channel). Sends one simple_message and one quiz.

Usage: python -m scripts.smoke_test_publisher
"""

import asyncio
import logging

from telegram import Bot

from app.core.logging import setup_logging
from app.core.settings import load_settings
from app.publishing.content_models import Quiz, SimpleMessage
from app.publishing.telegram_publisher import TelegramPublisher

logger = logging.getLogger(__name__)


async def run() -> None:
    settings = load_settings()
    setup_logging(settings.log_level, settings.log_dir)

    bot = Bot(token=settings.telegram_bot_token)
    publisher = TelegramPublisher(
        bot=bot,
        chat_id=settings.telegram_chat_id,
        media_dir=settings.media_dir,
        send_delay_seconds=settings.send_delay_seconds,
    )

    logger.info("Envoi simple_message de test...")
    await publisher.publish(
        SimpleMessage(
            type="simple_message",
            content="[smoke test] Nouvelle couche de publication typée (phase C) — OK.",
        )
    )

    logger.info("Envoi quiz de test...")
    await publisher.publish(
        Quiz(
            type="quiz",
            question="[smoke test] Quel langage ce bot utilise-t-il ?",
            options=["Python", "Java", "Rust"],
            correct_answer="Python",
            explanation="Le projet est écrit en Python (python-telegram-bot).",
        )
    )

    logger.info("Smoke test terminé avec succès.")


if __name__ == "__main__":
    asyncio.run(run())
