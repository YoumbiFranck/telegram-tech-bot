class AppError(Exception):
    """Base class for all domain errors raised by this application."""


class ConfigError(AppError):
    """Raised when required configuration is missing or invalid."""


class ContentValidationError(AppError):
    """Raised when a generated or authored content item fails schema validation."""


class TelegramSendError(AppError):
    """Raised when a Telegram API call fails after all retries are exhausted."""


class GenerationError(AppError):
    """Raised when a Claude Code generation call fails (transport or non-zero exit)."""
