"""Command-line entry point for the weekly personal intelligence digest."""

from __future__ import annotations

import argparse
import logging
from datetime import datetime, timezone

from app.collectors import (
    collect_github_releases,
    collect_google_news,
    collect_rss_feeds,
    collect_webpages,
)
from app.core import Database, config_path, get_settings, load_yaml
from app.engine import (
    classify_item,
    clean_text,
    deduplicate_items,
    rank_items,
    render_digest_html,
    send_email,
    summarize_items,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def collect_all_items(sources_config: dict, topics_config: dict, max_items: int) -> list:
    """Run all configured collectors and return raw items."""
    sources = sources_config.get("sources", {})
    items = []
    items.extend(collect_rss_feeds(sources.get("rss", []), max_items=max_items))
    items.extend(collect_google_news(topics_config, max_items=max(5, max_items // 2)))
    items.extend(collect_webpages(sources.get("webpages", []), max_items=max_items))
    items.extend(collect_github_releases(sources.get("github_releases", []), max_items=max(5, max_items // 2)))
    return items


def prepare_items(items: list, scoring_rules: dict) -> list:
    """Clean, classify, deduplicate, and score collected items."""
    for item in items:
        item.title = clean_text(item.title)
        item.summary = clean_text(item.summary)
        item.content = clean_text(item.content)
        classify_item(item)

    unique_items = deduplicate_items([item for item in items if item.title and item.url])
    return rank_items(unique_items, scoring_rules)


def run(send: bool = True) -> str:
    """Run the full digest pipeline and return rendered HTML."""
    settings = get_settings()
    topics_config = load_yaml(config_path("topics.yaml"))
    sources_config = load_yaml(config_path("sources.yaml"))
    scoring_rules = load_yaml(config_path("scoring_rules.yaml"))

    database = Database(settings.database_path)
    database.initialize()

    logger.info("Collecting items from trusted sources.")
    raw_items = collect_all_items(sources_config, topics_config, settings.max_items_per_source)
    ranked_items = prepare_items(raw_items, scoring_rules)
    inserted = database.upsert_items(ranked_items)
    logger.info("Collected %s items and inserted %s new items.", len(ranked_items), inserted)

    recent_items = database.recent_items(days_back=settings.days_back)
    recent_items = rank_items(recent_items, scoring_rules)
    summarized_items = summarize_items(recent_items, api_key=settings.gemini_api_key)
    database.update_item_summaries(summarized_items)

    html = render_digest_html(summarized_items)
    if send:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        send_email(settings, f"Weekly Personal Intelligence Digest - {today}", html)
    return html


def main() -> None:
    """Parse CLI flags and run the digest."""
    parser = argparse.ArgumentParser(description="Generate and email the weekly personal intelligence digest.")
    parser.add_argument("--no-send", action="store_true", help="Render the digest without sending email.")
    args = parser.parse_args()
    run(send=not args.no_send)


if __name__ == "__main__":
    main()
