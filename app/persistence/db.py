import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS published_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content_type TEXT NOT NULL,
    theme TEXT,
    title TEXT NOT NULL,
    content_json TEXT NOT NULL,
    prompt_version TEXT,
    telegram_message_id INTEGER,
    status TEXT NOT NULL,
    published_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_published_items_type_theme_date
    ON published_items (content_type, theme, published_at);

CREATE TABLE IF NOT EXISTS news_seen (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url_hash TEXT NOT NULL UNIQUE,
    url TEXT NOT NULL,
    title TEXT NOT NULL,
    source TEXT NOT NULL,
    first_seen_at TEXT NOT NULL,
    published INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS generation_errors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    step TEXT NOT NULL,
    error_class TEXT NOT NULL,
    message TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS run_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_date TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL,
    steps_completed TEXT NOT NULL DEFAULT '',
    started_at TEXT NOT NULL,
    finished_at TEXT
);

CREATE TABLE IF NOT EXISTS daily_quiz_theme (
    run_date TEXT PRIMARY KEY,
    theme TEXT NOT NULL
);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, isolation_level=None)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn
