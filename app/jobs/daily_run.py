import asyncio
import datetime
import logging
from typing import Callable, TypeVar

from app.core.errors import ContentValidationError, GenerationError, TelegramSendError
from app.generation.claude_client import ClaudeCliError, ClaudeTimeoutError
from app.generation.news_generator import generate_news_digest
from app.generation.quiz_generator import generate_quiz
from app.generation.tech_post_generator import generate_tech_post
from app.jobs.context import AppContext
from app.news.aggregator import fetch_all
from app.news.dedup import filter_new

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Délai entre deux quiz du même batch — au-delà du simple anti-flood, ça
# limite aussi le risque de rate limit Telegram sur une salve de ~10 envois.
QUIZ_BATCH_DELAY_SECONDS = 8


def _today() -> str:
    return datetime.date.today().isoformat()


async def _generate_with_recovery(
    generate_fn: Callable[[], T], step: str, max_attempts: int = 2
) -> T:
    """Applique la politique d'erreurs de génération définie dans l'analyse :
    ClaudeCliError (non connecté, rate-limit, ...) n'est jamais retentée à
    l'aveugle et remonte immédiatement pour déclencher une alerte ;
    ClaudeTimeoutError (transitoire) et ContentValidationError (sortie hors
    schéma) ont droit à une tentative bornée avant d'abandonner."""
    last_exc: GenerationError | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return generate_fn()
        except ClaudeCliError:
            raise
        except (ClaudeTimeoutError, ContentValidationError) as exc:
            last_exc = exc
            logger.warning("%s: tentative %d/%d échouée: %s", step, attempt, max_attempts, exc)
            if attempt < max_attempts:
                await asyncio.sleep(5)
    assert last_exc is not None
    raise last_exc


async def _alert_admin(ctx: AppContext, step: str, message: str) -> None:
    """Fait converger tous les canaux d'alerte configurés — email et Telegram
    admin ne sont pas mutuellement exclusifs, et l'email a l'avantage de
    fonctionner même si le problème vient de Telegram lui-même."""
    alerted = False

    if ctx.settings.telegram_admin_chat_id:
        try:
            await ctx.publisher.send_raw_text(
                chat_id=ctx.settings.telegram_admin_chat_id,
                text=f"[telegram-tech-bot] échec {step}: {message}",
            )
            alerted = True
        except Exception as exc:
            logger.error("Échec de l'envoi de l'alerte Telegram: %s", exc)

    if ctx.email_alerter is not None:
        ctx.email_alerter.send_error_alert(step, message)
        alerted = True

    if not alerted:
        logger.warning(
            "Aucun canal d'alerte configuré (TELEGRAM_ADMIN_CHAT_ID / RESEND_API_KEY), "
            "échec %s non notifié: %s",
            step,
            message,
        )


async def run_tech_post_step(ctx: AppContext) -> None:
    today = _today()
    if ctx.repo.has_step_run(today, "tech_post"):
        logger.info("tech_post déjà publié aujourd'hui (%s), on saute.", today)
        return

    excluded_topics = ctx.repo.recent_titles("simple_message", since_days=14)

    try:
        post = await _generate_with_recovery(
            lambda: generate_tech_post(ctx.client, ctx.prompts_dir, excluded_topics),
            step="tech_post",
        )
    except GenerationError as exc:
        logger.error("Échec définitif génération tech_post: %s", exc)
        ctx.repo.record_generation_error("tech_post", exc.__class__.__name__, str(exc))
        await _alert_admin(ctx, "tech_post", str(exc))
        return

    await ctx.publisher.publish(post)
    ctx.repo.record_published_item("simple_message", post.content[:80], post, status="published")
    ctx.repo.mark_step_done(today, "tech_post")
    logger.info("tech_post publié: %s", post.content[:80])


async def run_news_step(ctx: AppContext) -> None:
    today = _today()
    if ctx.repo.has_step_run(today, "news_digest"):
        logger.info("news_digest déjà publié aujourd'hui (%s), on saute.", today)
        return

    entries = fetch_all(ctx.news_sources)
    new_entries = filter_new(entries, ctx.repo)
    logger.info("Actus: %d récupérées, %d nouvelles.", len(entries), len(new_entries))

    if not new_entries:
        logger.info("Aucune actu nouvelle aujourd'hui, digest sauté.")
        ctx.repo.mark_step_done(today, "news_digest")
        return

    candidates = new_entries[:20]

    try:
        digest = await _generate_with_recovery(
            lambda: generate_news_digest(ctx.client, ctx.prompts_dir, candidates),
            step="news_digest",
        )
    except GenerationError as exc:
        logger.error("Échec définitif génération news_digest: %s", exc)
        ctx.repo.record_generation_error("news_digest", exc.__class__.__name__, str(exc))
        await _alert_admin(ctx, "news_digest", str(exc))
        return

    await ctx.publisher.publish(digest)
    ctx.repo.record_published_item("simple_message", digest.content[:80], digest, status="published")
    for entry in candidates:
        ctx.repo.mark_news_seen(url=entry.url, title=entry.title, source=entry.source, published=True)
    ctx.repo.mark_step_done(today, "news_digest")
    logger.info("news_digest publié (%d articles source).", len(candidates))


async def run_quiz_step(ctx: AppContext) -> None:
    """Un quiz par thème configuré (config/quiz_themes.yaml), tous publiés à
    la même heure planifiée. Chaque thème est idempotent individuellement
    (has_quiz_theme_published_today) et son échec n'affecte pas les autres —
    un thème qui échoue ne doit jamais bloquer les 9 autres."""
    today = _today()

    for theme in ctx.quiz_themes:
        if ctx.repo.has_quiz_theme_published_today(theme):
            logger.info("quiz[%s] déjà publié aujourd'hui (%s), on saute.", theme, today)
            continue

        excluded_questions = ctx.repo.recent_titles_by_theme("quiz", theme, since_days=30)

        try:
            quiz = await _generate_with_recovery(
                lambda theme=theme, excluded=excluded_questions: generate_quiz(
                    ctx.client, ctx.prompts_dir, theme, excluded
                ),
                step=f"quiz[{theme}]",
            )
        except GenerationError as exc:
            logger.error("Échec définitif génération quiz[%s]: %s", theme, exc)
            ctx.repo.record_generation_error(f"quiz_{theme}", exc.__class__.__name__, str(exc))
            await _alert_admin(ctx, f"quiz[{theme}]", str(exc))
            continue

        try:
            await ctx.publisher.publish(quiz)
        except TelegramSendError as exc:
            logger.error("Échec définitif envoi quiz[%s]: %s", theme, exc)
            ctx.repo.record_generation_error(f"quiz_{theme}_send", "TelegramSendError", str(exc))
            await _alert_admin(ctx, f"quiz[{theme}] (envoi)", str(exc))
            continue

        ctx.repo.record_published_item("quiz", quiz.question, quiz, status="published", theme=theme)
        logger.info("quiz publié (thème=%s): %s", theme, quiz.question)
        await asyncio.sleep(QUIZ_BATCH_DELAY_SECONDS)

    ctx.repo.mark_step_done(today, "quiz")
