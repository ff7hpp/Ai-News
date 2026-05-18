from app.processing.classifier import classify_text


def test_classifies_cybersecurity_item() -> None:
    assert classify_text("Critical CVE exploit released for red team testing") == "cybersecurity"


def test_classifies_ai_tool_item() -> None:
    assert classify_text("New AI coding debugger automates Python troubleshooting") == "ai_tools"


def test_classifies_student_benefit_item() -> None:
    assert classify_text("Free student subscription for university developers") == "student_benefits"


def test_classifies_unknown_as_other() -> None:
    assert classify_text("Local community event recap") == "other"
