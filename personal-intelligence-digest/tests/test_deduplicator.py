from app.core import DigestItem, normalize_title, normalize_url
from app.engine import deduplicate_items


def test_normalize_url_removes_tracking_parameters() -> None:
    assert normalize_url("HTTPS://Example.com/Post/?utm_source=x&b=2#section") == "https://example.com/Post?b=2"


def test_normalize_title_removes_punctuation_and_case() -> None:
    assert normalize_title("  Free Game: Limited Time! ") == "free game limited time"


def test_deduplicates_by_url_and_title() -> None:
    items = [
        DigestItem(title="Free Game Limited Time", url="https://example.com/deal?utm_source=x", source="A"),
        DigestItem(title="Different title", url="https://example.com/deal", source="B"),
        DigestItem(title="Free Game: Limited Time!", url="https://example.com/other", source="C"),
    ]

    unique = deduplicate_items(items)

    assert len(unique) == 1
    assert unique[0].source == "A"
