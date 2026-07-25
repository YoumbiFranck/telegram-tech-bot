"""Phase D verification: exercises the SQLite schema and repository directly
(no Telegram calls). Run twice in a row to confirm idempotency (run_log) and
duplicate detection behave correctly on the second pass.

Usage: python -m scripts.smoke_test_db
"""

import datetime
import logging

from app.core.logging import setup_logging
from app.core.settings import load_settings
from app.persistence.db import connect
from app.persistence.repository import Repository
from app.publishing.content_models import Quiz

logger = logging.getLogger(__name__)


def run() -> None:
    settings = load_settings()
    setup_logging(settings.log_level, settings.log_dir)

    conn = connect(settings.data_dir / "app.db")
    repo = Repository(conn)

    today = datetime.date.today().isoformat()

    quiz = Quiz(
        type="quiz",
        question="[smoke test] Quel mot-clé Python définit une fonction ?",
        options=["def", "func", "function"],
        correct_answer="def",
        explanation="`def` introduit une définition de fonction en Python.",
    )

    already_done = repo.is_run_done(today)
    logger.info("is_run_done(%s) avant start_run = %s", today, already_done)

    repo.start_run(today)

    is_dup = repo.is_duplicate_title(quiz.question)
    logger.info("is_duplicate_title(...) avant insertion = %s", is_dup)

    if not is_dup:
        item_id = repo.record_published_item(
            content_type="quiz",
            title=quiz.question,
            item=quiz,
            status="published",
            theme="Python",
            prompt_version="v0-smoke-test",
        )
        logger.info("published_items.id = %s", item_id)
    else:
        logger.info("Doublon détecté, insertion sautée (comportement attendu au 2e run).")

    repo.mark_news_seen(
        url="https://example.com/smoke-test-article",
        title="[smoke test] article factice",
        source="smoke-test",
        published=False,
    )
    logger.info("has_seen_news(...) = %s", repo.has_seen_news("https://example.com/smoke-test-article"))

    titles = repo.recent_titles_by_theme("quiz", "Python", since_days=14)
    logger.info("recent_titles_by_theme('quiz', 'Python', 14j) = %s", titles)
    logger.info(
        "has_quiz_theme_published_today('Python') = %s",
        repo.has_quiz_theme_published_today("Python"),
    )

    repo.record_generation_error(step="smoke_test", error_class="none", message="ceci est un test, pas une vraie erreur")

    repo.finish_run(today, status="success", steps_completed=["smoke_test"])
    logger.info("is_run_done(%s) après finish_run = %s", today, repo.is_run_done(today))

    conn.close()
    logger.info("Smoke test DB terminé avec succès.")


if __name__ == "__main__":
    run()
