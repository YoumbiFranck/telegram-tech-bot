from pathlib import Path

from app.generation.claude_client import ClaudeClient
from app.news.aggregator import NewsEntry
from app.publishing.content_models import SimpleMessage


def _format_articles(entries: list[NewsEntry]) -> str:
    return "\n".join(f"- [{entry.source}] {entry.title}" for entry in entries)


def generate_news_digest(
    client: ClaudeClient, prompts_dir: Path, entries: list[NewsEntry]
) -> SimpleMessage:
    template = (prompts_dir / "news_digest.md").read_text(encoding="utf-8")
    prompt = template.replace("{{ARTICLES}}", _format_articles(entries))
    result = client.generate(prompt)
    return SimpleMessage(type="simple_message", content=result.text)
