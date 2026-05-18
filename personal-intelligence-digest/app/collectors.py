"""Data collectors for RSS, Google News, GitHub Releases, and Webpages."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Iterable
from urllib.parse import quote_plus, urljoin

import feedparser
import requests
from bs4 import BeautifulSoup

from app.core import DigestItem

logger = logging.getLogger(__name__)


# --- RSS & Atom Collector ---
def _parse_feed_datetime(entry: dict) -> datetime | None:
    """Parse the most common RSS/Atom date fields."""
    for key in ("published", "updated", "created"):
        value = entry.get(key)
        if not value:
            continue
        try:
            parsed = parsedate_to_datetime(value)
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed
        except (TypeError, ValueError):
            logger.debug("Could not parse feed date %s", value)
    return None


def collect_rss_feeds(sources: Iterable[dict], max_items: int = 25) -> list[DigestItem]:
    """Collect items from configured RSS/Atom feeds."""
    collected: list[DigestItem] = []
    for source in sources:
        name = source.get("name", "Unknown RSS source")
        url = source.get("url")
        if not url:
            continue

        try:
            feed = feedparser.parse(url)
        except Exception:
            logger.exception("Failed to read RSS feed: %s", url)
            continue

        if getattr(feed, "bozo", False):
            logger.warning("Feed parser reported a problem for %s: %s", url, feed.get("bozo_exception"))

        for entry in feed.entries[:max_items]:
            item_url = entry.get("link")
            title = entry.get("title", "").strip()
            if not item_url or not title:
                continue

            collected.append(
                DigestItem(
                    title=title,
                    url=item_url,
                    source=name,
                    source_type="rss",
                    published_at=_parse_feed_datetime(entry),
                    summary=entry.get("summary", ""),
                    content=entry.get("description", entry.get("summary", "")),
                    metadata={"trust_score": str(source.get("trust_score", 5))},
                )
            )
    return collected


# --- Google News Collector ---
GOOGLE_NEWS_RSS = "https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"


def build_google_news_sources(topics: dict) -> list[dict]:
    """Create Google News RSS source definitions from configured topic queries."""
    sources: list[dict] = []
    for category, config in topics.get("topics", {}).items():
        queries = config.get("google_news_queries", [])
        for query in queries:
            sources.append(
                {
                    "name": f"Google News: {query}",
                    "url": GOOGLE_NEWS_RSS.format(query=quote_plus(query)),
                    "category_hint": category,
                    "trust_score": config.get("google_news_trust_score", 5),
                }
            )
    return sources


def collect_google_news(topics: dict, max_items: int = 15) -> list[DigestItem]:
    """Collect topic-matched items from Google News RSS."""
    items = collect_rss_feeds(build_google_news_sources(topics), max_items=max_items)
    for item in items:
        item.source_type = "google_news"
    return items


# --- GitHub Releases Collector ---
def collect_github_releases(sources: list[dict], max_items: int = 10) -> list[DigestItem]:
    """Collect release updates from GitHub Atom feeds for selected repos."""
    feed_sources = []
    for source in sources:
        repo = source.get("repo")
        if not repo:
            continue
        feed_sources.append(
            {
                "name": source.get("name", repo),
                "url": f"https://github.com/{repo}/releases.atom",
                "trust_score": source.get("trust_score", 7),
            }
        )

    items = collect_rss_feeds(feed_sources, max_items=max_items)
    for item in items:
        item.source_type = "github"
    return items


# --- Webpage Collector ---
def collect_webpages(sources: list[dict], max_items: int = 20) -> list[DigestItem]:
    """Collect links from configured public webpages (fallback for non-RSS sites)."""
    items: list[DigestItem] = []
    headers = {"User-Agent": "personal-intelligence-digest/0.1"}

    for source in sources:
        name = source.get("name", "Unknown webpage")
        url = source.get("url")
        selector = source.get("link_selector", "a")
        if not url:
            continue

        try:
            response = requests.get(url, headers=headers, timeout=20)
            response.raise_for_status()
        except requests.RequestException as exc:
            logger.warning("Failed to fetch webpage source %s: %s", url, exc)
            continue

        soup = BeautifulSoup(response.text, "html.parser")
        seen_urls: set[str] = set()
        for link in soup.select(selector):
            title = " ".join(link.get_text(" ", strip=True).split())
            href = link.get("href")
            if not title or not href:
                continue

            item_url = urljoin(url, href)
            if item_url in seen_urls:
                continue
            seen_urls.add(item_url)

            items.append(
                DigestItem(
                    title=title,
                    url=item_url,
                    source=name,
                    source_type="webpage",
                    published_at=datetime.now(timezone.utc),
                    metadata={"trust_score": str(source.get("trust_score", 4))},
                )
            )
            if len(seen_urls) >= max_items:
                break

    return items
