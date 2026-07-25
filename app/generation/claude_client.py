import logging
import subprocess
from dataclasses import dataclass

from app.core.errors import GenerationError

logger = logging.getLogger(__name__)


class ClaudeTimeoutError(GenerationError):
    """Transport-level failure (CLI timed out) — safe to retry with backoff."""


class ClaudeCliError(GenerationError):
    """CLI exited non-zero or returned no output (not logged in, rate-limited,
    binary missing, ...). Not safe to retry blindly — needs an operator alert."""


@dataclass
class ClaudeResult:
    text: str


class ClaudeClient:
    """Thin wrapper around the Claude Code CLI in non-interactive print mode.
    Relies on the CLI already being authenticated (`claude /login`) — this
    client never handles credentials itself."""

    def __init__(self, binary_path: str = "claude", timeout_seconds: float = 90.0) -> None:
        self._binary_path = binary_path
        self._timeout_seconds = timeout_seconds

    def generate(self, prompt: str) -> ClaudeResult:
        try:
            proc = subprocess.run(
                [self._binary_path, "-p", prompt, "--output-format", "text"],
                capture_output=True,
                text=True,
                timeout=self._timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            raise ClaudeTimeoutError(
                f"claude CLI timed out after {self._timeout_seconds}s"
            ) from exc
        except FileNotFoundError as exc:
            raise ClaudeCliError(f"claude binary not found at {self._binary_path!r}") from exc

        if proc.returncode != 0:
            raise ClaudeCliError(
                f"claude CLI exited with code {proc.returncode}: {proc.stderr.strip()[:500]}"
            )

        text = proc.stdout.strip()
        if not text:
            raise ClaudeCliError("claude CLI returned empty output")

        return ClaudeResult(text=text)
