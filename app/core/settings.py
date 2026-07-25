from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    telegram_bot_token: str = Field(min_length=1)
    telegram_chat_id: str = Field(min_length=1)
    telegram_admin_chat_id: str | None = None

    tz: str = "Europe/Paris"
    log_level: str = "INFO"

    data_dir: Path = PROJECT_ROOT / "data"
    log_dir: Path = PROJECT_ROOT / "logs"
    config_dir: Path = PROJECT_ROOT / "config"
    media_dir: Path = PROJECT_ROOT / "data" / "media"

    send_delay_seconds: float = 1.0

    claude_binary_path: str = "claude"
    claude_timeout_seconds: float = 90.0

    # Expressions cron (min heure jour mois jour_semaine) — espacées pour ne
    # pas tout publier d'un coup.
    schedule_tech_post_cron: str = "0 8 * * *"
    schedule_news_cron: str = "15 8 * * *"
    schedule_quiz_cron: str = "30 12 * * *"

    # Alerte email (Resend) sur échec définitif de génération — optionnel,
    # actif seulement si resend_api_key ET alert_email_to sont renseignés.
    resend_api_key: str | None = None
    alert_email_from: str = "Telegram Tech Bot <onboarding@resend.dev>"
    alert_email_to: str | None = None


def load_settings() -> Settings:
    settings = Settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.log_dir.mkdir(parents=True, exist_ok=True)
    settings.media_dir.mkdir(parents=True, exist_ok=True)
    return settings
