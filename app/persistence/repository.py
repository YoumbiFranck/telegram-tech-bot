import hashlib
import sqlite3
from datetime import datetime, timezone
from typing import Sequence

from app.publishing.content_models import ContentItem


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash(text: str) -> str:
    return hashlib.sha256(text.strip().lower().encode("utf-8")).hexdigest()


def normalize_title_hash(text: str) -> str:
    normalized = " ".join(text.strip().lower().split())
    return _hash(normalized)


class Repository:
    """Query layer over the SQLite history — the single source of truth for
    what has already been published, used for both deduplication and theme
    rotation decisions."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    # -- published_items ----------------------------------------------------

    def record_published_item(
        self,
        content_type: str,
        title: str,
        item: ContentItem,
        status: str,
        theme: str | None = None,
        prompt_version: str | None = None,
        telegram_message_id: int | None = None,
    ) -> int:
        cur = self._conn.execute(
            """
            INSERT INTO published_items
                (content_type, theme, title, content_json, prompt_version, telegram_message_id, status, published_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                content_type,
                theme,
                title,
                item.model_dump_json(),
                prompt_version,
                telegram_message_id,
                status,
                _now_iso(),
            ),
        )
        return cur.lastrowid

    def is_duplicate_title(self, title: str, since_days: int = 60) -> bool:
        title_hash = normalize_title_hash(title)
        rows = self._conn.execute(
            "SELECT title FROM published_items "
            "WHERE status = 'published' AND published_at >= datetime('now', ?)",
            (f"-{since_days} days",),
        ).fetchall()
        return any(normalize_title_hash(row["title"]) == title_hash for row in rows)

    def recent_titles(self, content_type: str, since_days: int = 14) -> list[str]:
        rows = self._conn.execute(
            "SELECT title FROM published_items "
            "WHERE content_type = ? AND status = 'published' AND published_at >= datetime('now', ?)",
            (content_type, f"-{since_days} days"),
        ).fetchall()
        return [row["title"] for row in rows]

    def recent_titles_by_theme(
        self, content_type: str, theme: str, since_days: int = 30
    ) -> list[str]:
        rows = self._conn.execute(
            "SELECT title FROM published_items "
            "WHERE content_type = ? AND theme = ? AND status = 'published' "
            "AND published_at >= datetime('now', ?)",
            (content_type, theme, f"-{since_days} days"),
        ).fetchall()
        return [row["title"] for row in rows]

    def has_quiz_theme_published_today(self, theme: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM published_items WHERE content_type = 'quiz' AND theme = ? "
            "AND status = 'published' AND date(published_at) = date('now') LIMIT 1",
            (theme,),
        ).fetchone()
        return row is not None

    # -- news_seen ------------------------------------------------------------

    def has_seen_news(self, url: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM news_seen WHERE url_hash = ?", (_hash(url),)
        ).fetchone()
        return row is not None

    def mark_news_seen(self, url: str, title: str, source: str, published: bool) -> None:
        self._conn.execute(
            """
            INSERT INTO news_seen (url_hash, url, title, source, first_seen_at, published)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(url_hash) DO UPDATE SET published = excluded.published
            """,
            (_hash(url), url, title, source, _now_iso(), int(published)),
        )

    # -- generation_errors ------------------------------------------------------

    def record_generation_error(self, step: str, error_class: str, message: str) -> None:
        self._conn.execute(
            "INSERT INTO generation_errors (step, error_class, message, created_at) VALUES (?, ?, ?, ?)",
            (step, error_class, message, _now_iso()),
        )

    # -- run_log (idempotency guard) ----------------------------------------------

    def is_run_done(self, run_date: str) -> bool:
        row = self._conn.execute(
            "SELECT status FROM run_log WHERE run_date = ?", (run_date,)
        ).fetchone()
        return row is not None and row["status"] in ("success", "partial")

    def start_run(self, run_date: str) -> None:
        self._conn.execute(
            """
            INSERT INTO run_log (run_date, status, steps_completed, started_at)
            VALUES (?, 'in_progress', '', ?)
            ON CONFLICT(run_date) DO UPDATE SET status = 'in_progress', started_at = excluded.started_at
            """,
            (run_date, _now_iso()),
        )

    def finish_run(self, run_date: str, status: str, steps_completed: Sequence[str]) -> None:
        self._conn.execute(
            "UPDATE run_log SET status = ?, steps_completed = ?, finished_at = ? WHERE run_date = ?",
            (status, ",".join(steps_completed), _now_iso(), run_date),
        )

    # -- per-step idempotency (survit a un crash/restart en cours de journee) ----

    def has_step_run(self, run_date: str, step: str) -> bool:
        row = self._conn.execute(
            "SELECT steps_completed FROM run_log WHERE run_date = ?", (run_date,)
        ).fetchone()
        if row is None:
            return False
        completed = [s for s in row["steps_completed"].split(",") if s]
        return step in completed

    def mark_step_done(self, run_date: str, step: str) -> None:
        row = self._conn.execute(
            "SELECT steps_completed FROM run_log WHERE run_date = ?", (run_date,)
        ).fetchone()
        if row is None:
            self._conn.execute(
                "INSERT INTO run_log (run_date, status, steps_completed, started_at) VALUES (?, 'in_progress', ?, ?)",
                (run_date, step, _now_iso()),
            )
            return
        completed = [s for s in row["steps_completed"].split(",") if s]
        if step not in completed:
            completed.append(step)
        self._conn.execute(
            "UPDATE run_log SET steps_completed = ? WHERE run_date = ?",
            (",".join(completed), run_date),
        )
