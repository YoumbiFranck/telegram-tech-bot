import asyncio
import datetime
import logging
from typing import Callable, TypeVar

from app.core.errors import ContentValidationError, GenerationError
from app.generation.claude_client import ClaudeCliError, ClaudeTimeoutError
from app.generation.code_image import (
    format_question_with_inline_code,
    generate_code_image,
    resolve_language,
)
from app.generation.news_generator import generate_news_digest
from app.generation.quiz_generator import generate_quiz
from app.generation.tech_post_generator import generate_tech_post
from app.generation.theme_rotation import pick_theme
from app.jobs.context import AppContext
from app.news.aggregator import fetch_all
from app.news.dedup import filter_new

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Délai entre deux quiz du même batch — au-delà du simple anti-flood, ça
# limite aussi le risque de rate limit Telegram sur une salve de ~10 envois.
QUIZ_BATCH_DELAY_SECONDS = 8

# Plan de difficulté fixe et déterministe pour les 10 questions du jour —
# l'ordre ne change jamais, ce qui permet de reprendre exactement au bon
# index après un crash (voir count_quiz_published_today).
DIFFICULTY_PLAN = ["easy"] * 6 + ["medium"] * 2 + ["hard"] * 2


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


async def run_tech_post_step(ctx: AppContext, force: bool = False) -> None:
    today = _today()
    if not force and ctx.repo.has_step_run(today, "tech_post"):
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


async def run_news_step(ctx: AppContext, force: bool = False) -> None:
    today = _today()
    if not force and ctx.repo.has_step_run(today, "news_digest"):
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


async def run_quiz_step(ctx: AppContext, force: bool = False) -> None:
    """Un thème unique est tiré au sort chaque jour (anti-répétition sur les
    14 derniers jours) et figé pour la journée entière. 10 questions sont
    générées sur ce thème selon un plan de difficulté fixe (6 faciles / 2
    intermédiaires / 2 difficiles). Chaque question est indépendante :
    l'échec de l'une (génération ou envoi) n'empêche jamais les suivantes,
    et la reprise après un crash se fait exactement au bon index grâce à
    count_quiz_published_today. Une question qui s'appuie sur du code est
    publiée avec une image générée par le service de rendu de code ; si ce
    service échoue, le code est réintégré (tronqué) dans le texte.

    force=True (--run-now --force) ignore l'idempotence du jour et republie
    un batch complet de 10 questions, sur le thème déjà tiré aujourd'hui
    s'il y en a un (sinon un nouveau est tiré) — utile pour tester sans
    attendre le lendemain."""
    today = _today()
    if not force and ctx.repo.has_step_run(today, "quiz"):
        logger.info("quiz déjà publié aujourd'hui (%s), on saute.", today)
        return

    theme = ctx.repo.get_quiz_theme_for_today()
    if theme is None:
        recent = ctx.repo.recent_quiz_themes(since_days=14)
        theme = pick_theme(ctx.quiz_themes, recent)
        ctx.repo.set_quiz_theme_for_today(theme)
        logger.info("Thème du jour tiré au sort: %s (récents exclus: %s)", theme, recent)
    else:
        logger.info("Thème du jour (déjà tiré): %s", theme)

    already_done = 0 if force else ctx.repo.count_quiz_published_today()
    if not force and already_done >= len(DIFFICULTY_PLAN):
        ctx.repo.mark_step_done(today, "quiz")
        return

    historical_excluded = ctx.repo.recent_titles_by_theme("quiz", theme, since_days=30)
    generated_this_run: list[str] = []

    for index in range(already_done, len(DIFFICULTY_PLAN)):
        difficulty = DIFFICULTY_PLAN[index]
        excluded = historical_excluded + generated_this_run
        step_label = f"quiz[{theme}/{difficulty}/{index + 1}]"

        try:
            quiz = await _generate_with_recovery(
                lambda difficulty=difficulty, excluded=excluded: generate_quiz(
                    ctx.client, ctx.prompts_dir, theme, difficulty, excluded
                ),
                step=step_label,
            )
        except GenerationError as exc:
            logger.error("Échec définitif génération %s: %s", step_label, exc)
            ctx.repo.record_generation_error(step_label, exc.__class__.__name__, str(exc))
            await _alert_admin(ctx, step_label, str(exc))
            continue

        generated_this_run.append(quiz.question)

        image_bytes = None
        if quiz.code:
            language = resolve_language(theme, quiz.language)
            image_bytes = generate_code_image(
                quiz.code,
                language,
                ctx.settings.code_image_api_url,
                ctx.settings.code_image_timeout_seconds,
            )
            if image_bytes is None:
                ctx.repo.record_generation_error(
                    f"{step_label}_image",
                    "ImageFallback",
                    "génération image échouée, repli texte utilisé",
                )
                quiz.question = format_question_with_inline_code(quiz.question, quiz.code)

        try:
            if image_bytes is not None:
                await ctx.publisher.publish_quiz_with_code_image(quiz, image_bytes)
            else:
                await ctx.publisher.publish(quiz)
        except Exception as exc:
            logger.error("Échec définitif envoi %s: %s", step_label, exc)
            ctx.repo.record_generation_error(f"{step_label}_send", exc.__class__.__name__, str(exc))
            await _alert_admin(ctx, f"{step_label} (envoi)", str(exc))
            continue

        ctx.repo.record_published_item("quiz", quiz.question, quiz, status="published", theme=theme)
        logger.info(
            "quiz publié (%s, difficulté=%s%s): %s",
            theme,
            difficulty,
            " +image" if image_bytes else "",
            quiz.question,
        )
        await asyncio.sleep(QUIZ_BATCH_DELAY_SECONDS)

    ctx.repo.mark_step_done(today, "quiz")
