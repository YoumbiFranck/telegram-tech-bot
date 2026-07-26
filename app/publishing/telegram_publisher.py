import asyncio
import logging
from io import BytesIO
from pathlib import Path
from typing import Awaitable, Callable, TypeVar

from telegram import Bot, Poll
from telegram.error import NetworkError, RetryAfter, TimedOut

from app.core.errors import TelegramSendError
from app.publishing.content_models import ContentItem, Image, ImagePoll, Quiz, SimpleMessage

logger = logging.getLogger(__name__)

T = TypeVar("T")


class TelegramPublisher:
    def __init__(
        self,
        bot: Bot,
        chat_id: str,
        media_dir: Path,
        send_delay_seconds: float = 1.0,
        max_retries: int = 3,
        retry_delay_seconds: float = 2.0,
    ) -> None:
        self._bot = bot
        self._chat_id = chat_id
        self._media_dir = media_dir
        self._send_delay_seconds = send_delay_seconds
        self._max_retries = max_retries
        self._retry_delay_seconds = retry_delay_seconds

    async def publish(self, item: ContentItem) -> None:
        if isinstance(item, SimpleMessage):
            await self._send_simple_message(item)
        elif isinstance(item, Quiz):
            await self._send_quiz(item)
        elif isinstance(item, Image):
            await self._send_image(item)
        elif isinstance(item, ImagePoll):
            await self._send_image(
                Image(type="image", content=item.caption, url=item.image_url)
            )
            await self._send_quiz(
                Quiz(
                    type="quiz",
                    question=item.question,
                    options=item.options,
                    correct_answer=item.correct_answer,
                    explanation=item.explanation,
                )
            )
        else:  # pragma: no cover - exhaustive by ContentItem union
            raise TelegramSendError(f"Unknown content item type: {item!r}")

        await asyncio.sleep(self._send_delay_seconds)

    async def publish_quiz_with_code_image(self, item: Quiz, image_bytes: bytes) -> None:
        """Quiz dont la question s'appuie sur du code déjà rendu en image —
        envoie la photo (en mémoire, aucun fichier temporaire) en légende,
        puis le poll lui-même via _send_quiz, réutilisée telle quelle."""

        async def send_photo_op():
            return await self._bot.send_photo(
                chat_id=self._chat_id,
                photo=BytesIO(image_bytes),
                caption=item.question,
            )

        await self._with_retry(send_photo_op)
        await self._send_quiz(item)
        await asyncio.sleep(self._send_delay_seconds)

    async def send_raw_text(self, chat_id: str, text: str) -> None:
        """Ops/alert message (ex: notification à l'admin) — ne passe pas par
        le contrat de contenu ContentItem, ce n'est pas du contenu publié."""
        await self._with_retry(lambda: self._bot.send_message(chat_id=chat_id, text=text))

    async def _with_retry(self, func: Callable[[], Awaitable[T]]) -> T:
        rate_limit_waits = 0
        attempt = 0
        while True:
            try:
                return await func()
            except RetryAfter as exc:
                rate_limit_waits += 1
                if rate_limit_waits > 3:
                    raise TelegramSendError(
                        f"Rate limit Telegram persistant après {rate_limit_waits} attentes"
                    ) from exc
                logger.warning(
                    "Rate limit Telegram, attente %.1fs avant nouvel essai", exc.retry_after
                )
                await asyncio.sleep(exc.retry_after + 0.5)
                # N'entame pas le budget de tentatives réseau ci-dessous —
                # attendre le délai demandé par Telegram n'est pas un échec.
            except (TimedOut, NetworkError) as exc:
                attempt += 1
                if attempt >= self._max_retries:
                    logger.error("Telegram call failed after %d attempts: %s", attempt, exc)
                    raise TelegramSendError(str(exc)) from exc
                logger.warning(
                    "Telegram call failed (attempt %d/%d), retrying in %ss: %s",
                    attempt,
                    self._max_retries,
                    self._retry_delay_seconds,
                    exc,
                )
                await asyncio.sleep(self._retry_delay_seconds)

    async def _send_simple_message(self, item: SimpleMessage) -> None:
        await self._with_retry(
            lambda: self._bot.send_message(chat_id=self._chat_id, text=item.content)
        )

    async def _send_quiz(self, item: Quiz) -> None:
        correct_option_id = item.options.index(item.correct_answer)
        await self._with_retry(
            lambda: self._bot.send_poll(
                chat_id=self._chat_id,
                question=item.question,
                options=item.options,
                type=Poll.QUIZ,
                correct_option_id=correct_option_id,
                explanation=item.explanation,
                is_anonymous=True,
            )
        )

    async def _send_image(self, item: Image) -> None:
        local_path = self._media_dir / item.url

        async def operation():
            if local_path.is_file():
                with local_path.open("rb") as image_file:
                    return await self._bot.send_photo(
                        chat_id=self._chat_id, photo=image_file, caption=item.content
                    )
            return await self._bot.send_photo(
                chat_id=self._chat_id, photo=item.url, caption=item.content
            )

        await self._with_retry(operation)
