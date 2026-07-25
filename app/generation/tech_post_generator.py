from pathlib import Path

from app.generation.claude_client import ClaudeClient
from app.publishing.content_models import SimpleMessage


def generate_tech_post(
    client: ClaudeClient, prompts_dir: Path, excluded_topics: list[str]
) -> SimpleMessage:
    template = (prompts_dir / "tech_post.md").read_text(encoding="utf-8")
    prompt = template.replace(
        "{{EXCLUDED_TOPICS}}",
        ", ".join(excluded_topics) if excluded_topics else "aucun",
    )
    result = client.generate(prompt)
    return SimpleMessage(type="simple_message", content=result.text)
