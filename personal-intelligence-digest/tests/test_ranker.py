from datetime import datetime, timedelta, timezone

from app.core import DigestItem
from app.engine import rank_items


SCORING_RULES = {
    "base_score": 1,
    "default_trust_score": 5,
    "high_value_word_points": 4,
    "recency": {"last_24_hours": 8, "last_3_days": 5, "last_7_days": 2},
    "category_bonus": {"cybersecurity": 5, "gaming_deals": 4, "other": 0},
    "keywords": {"free": 6, "CVE": 5, "exploit": 5},
}


def test_ranks_high_value_recent_items_first() -> None:
    older_generic = DigestItem(
        title="General software update",
        url="https://example.com/old",
        source="Example",
        published_at=datetime.now(timezone.utc) - timedelta(days=6),
        category="other",
        metadata={"trust_score": "3"},
    )
    recent_security = DigestItem(
        title="Free CVE exploit lab for students",
        url="https://example.com/security",
        source="Trusted",
        published_at=datetime.now(timezone.utc) - timedelta(hours=2),
        category="cybersecurity",
        metadata={"trust_score": "10"},
    )

    ranked = rank_items([older_generic, recent_security], SCORING_RULES)

    assert ranked[0] is recent_security
    assert ranked[0].score > ranked[1].score
