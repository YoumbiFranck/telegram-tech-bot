import logging
import socket
from dataclasses import dataclass

import feedparser

from app.news.sources import NewsSource

logger = logging.getLogger(__name__)

# feedparser n'expose aucun paramètre de timeout et bloque indéfiniment sur
# un flux qui accepte la connexion sans jamais répondre — ce qui a déjà gelé
# tout le scheduler (event loop asyncio partagé) pendant deux semaines.
FETCH_TIMEOUT_SECONDS = 15


@dataclass
class NewsEntry:
    title: str
    url: str
    source: str
    summary: str
    published_at: str


def fetch_source(source: NewsSource, max_entries: int = 15) -> list[NewsEntry]:
    previous_timeout = socket.getdefaulttimeout()
    socket.setdefaulttimeout(FETCH_TIMEOUT_SECONDS)
    try:
        parsed = feedparser.parse(source.url)
    finally:
        socket.setdefaulttimeout(previous_timeout)
    if parsed.bozo:
        logger.warning(
            "Flux mal formé ou inaccessible, ignoré: %s (%s)", source.name, parsed.get("bozo_exception")
        )
        return []

    entries = []
    for entry in parsed.entries[:max_entries]:
        link = entry.get("link")
        title = entry.get("title")
        if not link or not title:
            continue
        entries.append(
            NewsEntry(
                title=title,
                url=link,
                source=source.name,
                summary=entry.get("summary", "")[:500],
                published_at=entry.get("published", entry.get("updated", "")),
            )
        )
    return entries


def fetch_all(sources: list[NewsSource], max_entries_per_source: int = 15) -> list[NewsEntry]:
    # Un flux en échec (indisponible, format cassé) ne doit jamais bloquer les
    # autres — c'est le comportement explicitement attendu de l'agrégation.
    all_entries: list[NewsEntry] = []
    for source in sources:
        try:
            all_entries.extend(fetch_source(source, max_entries_per_source))
        except Exception as exc:
            logger.warning("Échec de récupération du flux %s: %s", source.name, exc)
    return all_entries
