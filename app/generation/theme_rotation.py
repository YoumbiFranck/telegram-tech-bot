import random


def pick_theme(available_themes: list[str], recently_used: list[str]) -> str:
    pool = [theme for theme in available_themes if theme not in recently_used]
    if not pool:
        pool = available_themes
    return random.choice(pool)
