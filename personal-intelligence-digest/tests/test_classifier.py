from app.engine import classify_item
from app.core import DigestItem


def _classify_text(title: str, body: str = "") -> str:
    """Helper that wraps classify_item for backward-compatible text-only testing."""
    item = DigestItem(title=title, url="https://example.com", source="test", summary=body)
    classify_item(item)
    return item.category


def test_classifies_cybersecurity_item() -> None:
    assert _classify_text("Critical CVE exploit released for red team testing") == "cybersecurity"


def test_classifies_ai_tool_item() -> None:
    assert _classify_text("New AI coding debugger automates Python troubleshooting") == "ai_tools"


def test_classifies_student_benefit_item() -> None:
    assert _classify_text("Free student subscription for university developers") == "student_benefits"


def test_classifies_unknown_as_other() -> None:
    assert _classify_text("Local community event recap") == "other"
