from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass
class NewsSource:
    name: str
    url: str


def load_sources(config_dir: Path) -> list[NewsSource]:
    data = yaml.safe_load((config_dir / "news_sources.yaml").read_text(encoding="utf-8"))
    return [NewsSource(name=item["name"], url=item["url"]) for item in data["sources"]]
