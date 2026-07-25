import logging

import resend

logger = logging.getLogger(__name__)


class EmailAlerter:
    """Alerte email via Resend — canal indépendant de Telegram, utile
    justement quand le problème est côté Telegram (token invalide, etc.)."""

    def __init__(self, api_key: str, sender: str, recipient: str) -> None:
        resend.api_key = api_key
        self._sender = sender
        self._recipient = recipient

    def send_error_alert(self, step: str, message: str) -> None:
        try:
            resend.Emails.send(
                {
                    "from": self._sender,
                    "to": [self._recipient],
                    "subject": f"[telegram-tech-bot] échec {step}",
                    "html": (
                        f"<p><strong>Étape :</strong> {step}</p>"
                        f"<p><strong>Erreur :</strong><br>{message}</p>"
                    ),
                }
            )
        except Exception as exc:
            logger.error("Échec de l'envoi de l'alerte email: %s", exc)
