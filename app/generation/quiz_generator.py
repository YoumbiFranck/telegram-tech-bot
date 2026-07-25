import json
import re
from pathlib import Path

from pydantic import ValidationError

from app.core.errors import ContentValidationError
from app.generation.claude_client import ClaudeClient
from app.publishing.content_models import Quiz

_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def _strip_code_fence(text: str) -> str:
    return _FENCE_RE.sub("", text).strip()


def _ensure_theme_prefix(question: str, theme: str) -> str:
    """Guarantee the theme is visible in the question text itself, regardless
    of whether the model followed the prompt instruction — a quiz poll seen
    in isolation in a Telegram thread must say unambiguously which
    language/theme it's about."""
    theme_upper = theme.upper()
    if question.upper().startswith(theme_upper):
        return question
    return f"{theme_upper} — {question}"


def generate_quiz(
    client: ClaudeClient, prompts_dir: Path, theme: str, excluded_questions: list[str]
) -> Quiz:
    template = (prompts_dir / "quiz.md").read_text(encoding="utf-8")
    prompt = (
        template.replace("{{THEME}}", theme)
        .replace("{{THEME_UPPER}}", theme.upper())
        .replace(
            "{{EXCLUDED_QUESTIONS}}",
            "; ".join(excluded_questions) if excluded_questions else "aucune",
        )
    )
    result = client.generate(prompt)
    cleaned = _strip_code_fence(result.text)

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ContentValidationError(
            f"Sortie non-JSON de Claude pour le quiz: {result.text[:200]!r}"
        ) from exc

    if "question" in data:
        data["question"] = _ensure_theme_prefix(data["question"], theme)

    try:
        return Quiz(type="quiz", **data)
    except ValidationError as exc:
        raise ContentValidationError(f"Quiz généré invalide: {exc}") from exc
