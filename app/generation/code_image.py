import logging

import httpx

logger = logging.getLogger(__name__)

# Repli si Claude ne fournit pas de "language" exploitable — mapping du
# thème vers un identifiant de coloration syntaxique raisonnable. "text" en
# dernier recours pour ne jamais planter sur un thème inconnu (ajouté plus
# tard dans config/quiz_themes.yaml sans mise à jour de ce fichier).
_DEFAULT_LANGUAGE_BY_THEME = {
    "Java": "java",
    "Python": "python",
    "SQL": "sql",
    "Symfony": "php",
    "PHP": "php",
    "JavaScript": "javascript",
    "TypeScript": "typescript",
    "Git": "bash",
    "Linux": "bash",
    "Docker": "dockerfile",
}
_FALLBACK_LANGUAGE = "text"


def resolve_language(theme: str, claude_language: str | None) -> str:
    if claude_language:
        return claude_language.strip().lower()
    return _DEFAULT_LANGUAGE_BY_THEME.get(theme, _FALLBACK_LANGUAGE)


def generate_code_image(
    code: str, language: str, api_url: str, timeout: float
) -> bytes | None:
    """Ne lève jamais d'exception — retourne None sur tout échec (service
    indisponible, timeout, erreur réseau, réponse invalide) pour que
    l'appelant puisse toujours retomber sur le repli texte."""
    try:
        response = httpx.post(
            api_url, json={"code": code, "language": language}, timeout=timeout
        )
        response.raise_for_status()
        return response.content
    except Exception as exc:
        logger.warning(
            "Échec génération image de code (langage=%s): %s", language, exc
        )
        return None


def format_question_with_inline_code(question: str, code: str, max_length: int = 300) -> str:
    """Repli texte quand l'image ne peut pas être générée — réintègre le
    code dans la question, en tronquant strictement pour ne jamais dépasser
    la limite Telegram. La question a toujours priorité sur le code."""
    combined = f"{question}\n\n{code}"
    if len(combined) <= max_length:
        return combined

    suffix = "… (tronqué)"
    available = max_length - len(question) - len("\n\n") - len(suffix)
    if available <= 0:
        return question[:max_length]
    return f"{question}\n\n{code[:available]}{suffix}"
