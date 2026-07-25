from app.news.aggregator import NewsEntry
from app.persistence.repository import Repository


def filter_new(entries: list[NewsEntry], repo: Repository) -> list[NewsEntry]:
    return [entry for entry in entries if not repo.has_seen_news(entry.url)]
