"""Core data structures, configuration, storage, and helper utilities."""

from __future__ import annotations

import json
import os
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import yaml
from dotenv import load_dotenv

# --- Paths & Regex ---
PROJECT_ROOT = Path(__file__).resolve().parents[1]
TRACKING_PARAMS_PREFIXES = ("utm_",)
TRACKING_PARAMS = {"fbclid", "gclid", "mc_cid", "mc_eid", "ref"}
PUNCT_RE = re.compile(r"[^\w\s-]")
WHITESPACE_RE = re.compile(r"\s+")


# --- Helper Utilities ---
def normalize_url(url: str) -> str:
    """Normalize URLs enough to catch common duplicates."""
    parts = urlsplit(url.strip())
    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key not in TRACKING_PARAMS and not key.startswith(TRACKING_PARAMS_PREFIXES)
    ]
    clean_path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), clean_path, urlencode(query, doseq=True), ""))


def normalize_title(title: str) -> str:
    """Normalize titles for duplicate checks."""
    lowered = title.lower().strip()
    without_punct = PUNCT_RE.sub("", lowered)
    return WHITESPACE_RE.sub(" ", without_punct).strip()


# --- Configuration ---
@dataclass(frozen=True)
class Settings:
    """Runtime settings loaded from environment variables."""
    gemini_api_key: str
    smtp_host: str
    smtp_port: int
    smtp_username: str
    smtp_password: str
    email_from: str
    email_to: str
    database_path: Path
    days_back: int = 7
    max_items_per_source: int = 25


def load_yaml(path: Path) -> dict[str, Any]:
    """Load a YAML configuration file and return a dictionary."""
    with path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Expected YAML mapping in {path}")
    return data


def get_settings() -> Settings:
    """Load settings from `.env` and the process environment."""
    load_dotenv(PROJECT_ROOT / ".env")
    database_path = Path(os.getenv("DATABASE_PATH", PROJECT_ROOT / "digest.sqlite3"))

    return Settings(
        gemini_api_key=os.getenv("GEMINI_API_KEY", ""),
        smtp_host=os.getenv("SMTP_HOST", ""),
        smtp_port=int(os.getenv("SMTP_PORT", "587")),
        smtp_username=os.getenv("SMTP_USERNAME", ""),
        smtp_password=os.getenv("SMTP_PASSWORD", ""),
        email_from=os.getenv("EMAIL_FROM", ""),
        email_to=os.getenv("EMAIL_TO", ""),
        database_path=database_path,
        days_back=int(os.getenv("DIGEST_DAYS_BACK", "7")),
        max_items_per_source=int(os.getenv("MAX_ITEMS_PER_SOURCE", "25")),
    )


def config_path(name: str) -> Path:
    """Return the absolute path for a file in the config directory."""
    return PROJECT_ROOT / "config" / name


# --- Models ---
@dataclass
class DigestItem:
    """A collected article, tool release, benefit, or offer."""
    title: str
    url: str
    source: str
    source_type: str = "web"
    published_at: datetime | None = None
    summary: str = ""
    content: str = ""
    category: str = "other"
    score: float = 0.0
    why_it_matters: str = ""
    action_to_take: str = ""
    deadline: str = ""
    urgency: str = "MEDIUM"
    metadata: dict[str, str] = field(default_factory=dict)

    def normalized_published_at(self) -> datetime:
        """Return a timezone-aware published timestamp."""
        if self.published_at is None:
            return datetime.now(timezone.utc)
        if self.published_at.tzinfo is None:
            return self.published_at.replace(tzinfo=timezone.utc)
        return self.published_at


# --- Database ---
SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    normalized_title TEXT NOT NULL,
    url TEXT NOT NULL,
    normalized_url TEXT NOT NULL UNIQUE,
    source TEXT NOT NULL,
    source_type TEXT NOT NULL,
    published_at TEXT NOT NULL,
    summary TEXT NOT NULL DEFAULT '',
    content TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT 'other',
    score REAL NOT NULL DEFAULT 0,
    why_it_matters TEXT NOT NULL DEFAULT '',
    action_to_take TEXT NOT NULL DEFAULT '',
    deadline TEXT NOT NULL DEFAULT '',
    urgency TEXT NOT NULL DEFAULT 'MEDIUM',
    metadata TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_items_published_at ON items(published_at);
CREATE INDEX IF NOT EXISTS idx_items_category ON items(category);
CREATE UNIQUE INDEX IF NOT EXISTS idx_items_normalized_title ON items(normalized_title);
"""


class Database:
    """Small SQLite wrapper for digest items."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(SCHEMA)

            # Ensure urgency column exists in case of schema upgrade
            try:
                connection.execute("ALTER TABLE items ADD COLUMN urgency TEXT NOT NULL DEFAULT 'MEDIUM'")
            except sqlite3.OperationalError:
                pass # Column already exists

    def upsert_items(self, items: list[DigestItem]) -> int:
        inserted = 0
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as connection:
            for item in items:
                try:
                    cursor = connection.execute(
                        """
                        INSERT OR IGNORE INTO items (
                            title, normalized_title, url, normalized_url, source, source_type,
                            published_at, summary, content, category, score, why_it_matters,
                            action_to_take, deadline, urgency, metadata, created_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            item.title,
                            normalize_title(item.title),
                            item.url,
                            normalize_url(item.url),
                            item.source,
                            item.source_type,
                            item.normalized_published_at().isoformat(),
                            item.summary,
                            item.content,
                            item.category,
                            item.score,
                            item.why_it_matters,
                            item.action_to_take,
                            item.deadline,
                            item.urgency,
                            json.dumps(item.metadata),
                            now,
                        ),
                    )
                    inserted += cursor.rowcount
                except sqlite3.Error:
                    continue
        return inserted

    def recent_items(self, days_back: int = 7) -> list[DigestItem]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM items WHERE published_at >= ? ORDER BY score DESC, published_at DESC",
                (cutoff.isoformat(),),
            ).fetchall()
        return [self._row_to_item(row) for row in rows]

    def update_item_summaries(self, items: list[DigestItem]) -> None:
        with self.connect() as connection:
            for item in items:
                connection.execute(
                    """
                    UPDATE items
                    SET category = ?, score = ?, why_it_matters = ?, action_to_take = ?, deadline = ?, urgency = ?
                    WHERE normalized_url = ?
                    """,
                    (
                        item.category,
                        item.score,
                        item.why_it_matters,
                        item.action_to_take,
                        item.deadline,
                        item.urgency,
                        normalize_url(item.url),
                    ),
                )

    def _row_to_item(self, row: sqlite3.Row) -> DigestItem:
        return DigestItem(
            title=row["title"],
            url=row["url"],
            source=row["source"],
            source_type=row["source_type"],
            published_at=datetime.fromisoformat(row["published_at"]),
            summary=row["summary"],
            content=row["content"],
            category=row["category"],
            score=row["score"],
            why_it_matters=row["why_it_matters"],
            action_to_take=row["action_to_take"],
            deadline=row["deadline"],
            urgency=row.keys().count("urgency") and row["urgency"] or "MEDIUM",
            metadata=json.loads(row["metadata"] or "{}"),
        )
