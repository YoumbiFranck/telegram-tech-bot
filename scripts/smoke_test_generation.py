"""Phase E verification: exercises the full path Claude Code -> validation ->
publication. Generates one tech post and one quiz via the CLI, validates them
against the typed content schema, and publishes both to the configured
Telegram chat (test channel).

Requires the `claude` CLI to be reachable and authenticated in this
environment (see app.core.settings.claude_binary_path).

Usage: python -m scripts.smoke_test_generation
"""

import asyncio
import logging

from telegram import Bot

from app.core.errors import ContentValidationError, GenerationError
from app.core.logging import setup_logging
from app.core.settings import load_settings
from app.generation.claude_client import ClaudeClient
from app.generation.quiz_generator import generate_quiz
from app.generation.tech_post_generator import generate_tech_post
from app.persistence.db import connect
from app.persistence.repository import Repository
from app.publishing.telegram_publisher import TelegramPublisher

logger = logging.getLogger(__name__)


async def run() -> None:
    settings = load_settings()
    setup_logging(settings.log_level, settings.log_dir)

    client = ClaudeClient(
        binary_path=settings.claude_binary_path,
        timeout_seconds=settings.claude_timeout_seconds,
    )
    conn = connect(settings.data_dir / "app.db")
    repo = Repository(conn)

    bot = Bot(token=settings.telegram_bot_token)
    publisher = TelegramPublisher(
        bot=bot,
        chat_id=settings.telegram_chat_id,
        media_dir=settings.media_dir,
        send_delay_seconds=settings.send_delay_seconds,
    )

    prompts_dir = settings.config_dir.parent / "app" / "generation" / "prompts"

    # -- tech post --------------------------------------------------------
    logger.info("Génération du post tech via Claude Code...")
    excluded_topics: list[str] = []  # branché sur l'historique réel en phase G (orchestration)
    try:
        post = generate_tech_post(client, prompts_dir, excluded_topics)
    except GenerationError as exc:
        logger.error("Échec génération post tech: %s", exc)
        repo.record_generation_error("tech_post", exc.__class__.__name__, str(exc))
        post = None

    if post is not None:
        logger.info("Post généré : %s", post.content)
        await publisher.publish(post)
        repo.record_published_item("simple_message", post.content[:80], post, status="published")

    # -- quiz ---------------------------------------------------------------
    theme = "Python"  # thème fixe pour ce smoke test bas-niveau ; en prod, run_quiz_step
    # tire un thème unique au sort chaque jour et genere 10 questions dessus
    # (6 faciles/2 intermediaires/2 difficiles) - voir app/jobs/daily_run.py

    try:
        quiz = generate_quiz(client, prompts_dir, theme, difficulty="medium", excluded_questions=[])
    except (GenerationError, ContentValidationError) as exc:
        logger.error("Échec génération quiz: %s", exc)
        repo.record_generation_error("quiz", exc.__class__.__name__, str(exc))
        quiz = None

    if quiz is not None:
        logger.info("Quiz généré : %s | options=%s | réponse=%s", quiz.question, quiz.options, quiz.correct_answer)
        await publisher.publish(quiz)
        repo.record_published_item("quiz", quiz.question, quiz, status="published", theme=theme)

    conn.close()
    logger.info("Smoke test génération terminé.")


if __name__ == "__main__":
    asyncio.run(run())
