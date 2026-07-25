import logging

import httpx

logger = logging.getLogger(__name__)


def send_heartbeat(push_url: str) -> None:
    """Ping un moniteur Uptime Kuma de type Push — prouve que le process
    (et sa boucle asyncio) est bien vivant entre deux publications, qui
    peuvent être espacées de plusieurs heures."""
    try:
        response = httpx.get(push_url, timeout=10.0)
        response.raise_for_status()
    except Exception as exc:
        logger.warning("Échec de l'envoi du heartbeat Uptime Kuma: %s", exc)
