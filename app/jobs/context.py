from dataclasses import dataclass
from pathlib import Path

import yaml

from app.core.settings import Settings
from app.generation.claude_client import ClaudeClient
from app.news.sources import NewsSource, load_sources
from app.persistence.repository import Repository
from app.publishing.telegram_publisher import TelegramPublisher

PROMPTS_DIR = Path(__file__).resolve().parents[1] / "generation" / "prompts"


@dataclass
class AppContext:
    settings: Settings
    client: ClaudeClient
    repo: Repository
    publisher: TelegramPublisher
    prompts_dir: Path
    quiz_themes: list[str]
    news_sources: list[NewsSource]


def build_context(
    settings: Settings, client: ClaudeClient, repo: Repository, publisher: TelegramPublisher
) -> AppContext:
    themes_data = yaml.safe_load(
        (settings.config_dir / "quiz_themes.yaml").read_text(encoding="utf-8")
    )
    news_sources = load_sources(settings.config_dir)
    return AppContext(
        settings=settings,
        client=client,
        repo=repo,
        publisher=publisher,
        prompts_dir=PROMPTS_DIR,
        quiz_themes=themes_data["themes"],
        news_sources=news_sources,
    )
