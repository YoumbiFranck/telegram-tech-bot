import asyncio
import logging
from pathlib import Path
from typing import Awaitable, Callable, TypeVar

from telegram import Bot, Poll
from telegram.error import NetworkError, TimedOut

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

    async def _with_retry(self, func: Callable[[], Awaitable[T]]) -> T:
        for attempt in range(1, self._max_retries + 1):
            try:
                return await func()
            except (TimedOut, NetworkError) as exc:
                if attempt == self._max_retries:
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
        raise AssertionError("unreachable")  # pragma: no cover

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
