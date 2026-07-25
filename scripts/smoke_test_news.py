"""Phase F verification: fetch all configured RSS sources, deduplicate against
the SQLite history, and mark the new ones as seen. Run twice in a row — the
second run should report far fewer (ideally zero) "new" entries, since the
first run already marked them seen.

Usage: python -m scripts.smoke_test_news
"""

import logging

from app.core.logging import setup_logging
from app.core.settings import load_settings
from app.news.aggregator import fetch_all
from app.news.dedup import filter_new
from app.news.sources import load_sources
from app.persistence.db import connect
from app.persistence.repository import Repository

logger = logging.getLogger(__name__)


def run() -> None:
    settings = load_settings()
    setup_logging(settings.log_level, settings.log_dir)

    sources = load_sources(settings.config_dir)
    logger.info("Sources configurées: %d", len(sources))

    entries = fetch_all(sources)
    logger.info("Articles récupérés (tous flux confondus): %d", len(entries))

    conn = connect(settings.data_dir / "app.db")
    repo = Repository(conn)

    new_entries = filter_new(entries, repo)
    logger.info("Articles nouveaux (non vus précédemment): %d / %d", len(new_entries), len(entries))

    for entry in new_entries:
        repo.mark_news_seen(url=entry.url, title=entry.title, source=entry.source, published=False)

    per_source: dict[str, int] = {}
    for entry in entries:
        per_source[entry.source] = per_source.get(entry.source, 0) + 1
    for source, count in per_source.items():
        logger.info("  - %s: %d article(s)", source, count)

    conn.close()
    logger.info("Smoke test agrégation actus terminé.")


if __name__ == "__main__":
    run()
