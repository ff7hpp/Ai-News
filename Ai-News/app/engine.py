"""Processing, summarization, and email delivery engine."""

from __future__ import annotations

import html
import json
import logging
import re
import smtplib
from email.message import EmailMessage
from pathlib import Path

from bs4 import BeautifulSoup
from google import genai
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.core import PROJECT_ROOT, DigestItem, Settings, normalize_title, normalize_url

logger = logging.getLogger(__name__)


# --- Cleaner ---
WHITESPACE_RE = re.compile(r"\s+")

def clean_text(value: str) -> str:
    """Remove HTML markup and normalize whitespace."""
    if not value:
        return ""
    without_tags = BeautifulSoup(value, "html.parser").get_text(" ", strip=True)
    unescaped = html.unescape(without_tags)
    return WHITESPACE_RE.sub(" ", unescaped).strip()


# --- Classifier ---
CATEGORIES = {
    "cybersecurity": ["cve", "exploit", "zero-day", "zeroday", "red team", "offensive security", "vulnerability", "malware", "ransomware", "pentest", "burp", "nmap", "metasploit", "osint"],
    "ai_tools": ["ai", "llm", "openai", "agent", "coding assistant", "ai coding", "debugging", "debugger", "prompt", "automation", "copilot"],
    "software_tools": ["developer tool", "devtool", "cli", "sdk", "api", "library", "framework", "release", "open source", "github", "terminal", "ide"],
    "gaming_deals": ["free game", "epic games", "steam", "gog", "giveaway", "dlc", "limited-time game", "free weekend"],
    "student_benefits": ["student", "education", "university", "github student", "student discount", "free subscription", "campus", "academic"],
}

def classify_item(item: DigestItem) -> DigestItem:
    """Set the category for a collected item."""
    text = f"{item.title} {item.summary} {item.content}".lower()
    scores = {category: 0 for category in CATEGORIES}
    for category, keywords in CATEGORIES.items():
        for keyword in keywords:
            if keyword in text:
                scores[category] += 1

    best_category = max(scores, key=scores.get)
    item.category = best_category if scores[best_category] > 0 else "other"
    return item


# --- Deduplicator ---
def deduplicate_items(items: list[DigestItem]) -> list[DigestItem]:
    """Remove items with duplicate URLs or duplicate normalized titles."""
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    unique: list[DigestItem] = []

    for item in items:
        norm_url = normalize_url(item.url)
        norm_title = normalize_title(item.title)
        if norm_url in seen_urls or norm_title in seen_titles:
            continue
        seen_urls.add(norm_url)
        seen_titles.add(norm_title)
        unique.append(item)
    return unique


# --- Ranker ---
HIGH_VALUE_WORDS = ["free", "student", "limited time", "giveaway", "lifetime deal", "cve", "exploit", "zero-day", "ai coding", "debugging", "automation"]

def rank_items(items: list[DigestItem], scoring_rules: dict) -> list[DigestItem]:
    """Score and return items ordered from most to least useful."""
    for item in items:
        text = f"{item.title} {item.summary} {item.content}".lower()
        score = float(scoring_rules.get("base_score", 1))
        score += float(item.metadata.get("trust_score", scoring_rules.get("default_trust_score", 5)))
        score += float(scoring_rules.get("category_bonus", {}).get(item.category, 0))

        # Keywords
        for keyword, points in scoring_rules.get("keywords", {}).items():
            if keyword.lower() in text:
                score += float(points)
        high_value_points = float(scoring_rules.get("high_value_word_points", 4))
        for word in HIGH_VALUE_WORDS:
            if word in text:
                score += high_value_points

        # Recency
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        age_days = max((now - item.normalized_published_at()).total_seconds() / 86400, 0)
        recency = scoring_rules.get("recency", {})
        if age_days <= 1:
            score += float(recency.get("last_24_hours", 8))
        elif age_days <= 3:
            score += float(recency.get("last_3_days", 5))
        elif age_days <= 7:
            score += float(recency.get("last_7_days", 2))

        item.score = round(score, 2)

    return sorted(items, key=lambda item: item.score, reverse=True)


# --- Summarizer ---
_quota_exhausted = False

def _fallback_summary(item: DigestItem) -> DigestItem:
    """Fill useful summary fields when Gemini is unavailable."""
    item.why_it_matters = item.summary[:180] or f"Potentially useful {item.category.replace('_', ' ')} update from {item.source}."
    item.action_to_take = "Open the link and decide whether to read, claim, try, or save it this week."
    item.deadline = ""
    item.urgency = {"cybersecurity": "HIGH", "student_benefits": "HIGH", "gaming_deals": "MEDIUM", "ai_tools": "MEDIUM", "software_tools": "LOW"}.get(item.category, "LOW")
    return item

def summarize_items(items: list[DigestItem], api_key: str, limit: int = 30) -> list[DigestItem]:
    """Summarize the highest-priority digest items using Gemini API."""
    global _quota_exhausted
    summarized: list[DigestItem] = []

    for idx, item in enumerate(items):
        if idx >= limit or not api_key or _quota_exhausted:
            summarized.append(_fallback_summary(item))
            continue

        try:
            client = genai.Client(api_key=api_key)
            payload = {
                "title": item.title, "source": item.source, "category": item.category,
                "url": item.url, "summary": item.summary[:1000], "content": item.content[:1000],
            }
            prompt = (
                "You are summarizing news for a software engineering student who only has 30 seconds per item. "
                "They care about: cybersecurity threats & CVEs, offensive security tools, free or limited-time offers, "
                "student discounts/benefits, free games, and practical AI/dev tools. "
                "Be DIRECT and CRITICAL. Skip anything generic or obvious.\n\n"
                "Return STRICT JSON with these exact keys:\n"
                "  why_it_matters: 1 punchy sentence (max 20 words). Start with the most critical fact.\n"
                "  action_to_take: Exact next step (max 15 words). Use verbs: Claim, Patch, Download, Enroll, Try, Read.\n"
                "  deadline: Specific date or timeframe if time-sensitive, else empty string.\n"
                "  urgency: one of: CRITICAL | HIGH | MEDIUM | LOW\n"
                "    - CRITICAL = active exploit, breach, CVE with patch, expiring free offer today/this week\n"
                "    - HIGH = important tool/release, deal expiring soon, must-know security news\n"
                "    - MEDIUM = useful but not urgent\n"
                "    - LOW = informational only\n\n"
                f"Item:\n{json.dumps(payload, ensure_ascii=False)}"
            )

            response = client.models.generate_content(
                model="gemini-2.0-flash-lite",
                contents=prompt,
                config=genai.types.GenerateContentConfig(temperature=0.2, response_mime_type="application/json"),
            )
            raw_text = response.text.strip()
            if raw_text.startswith("```"):
                raw_text = raw_text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
            data = json.loads(raw_text)

            item.why_it_matters = str(data.get("why_it_matters", "")).strip()
            item.action_to_take = str(data.get("action_to_take", "")).strip()
            item.deadline = str(data.get("deadline", "")).strip()
            item.urgency = str(data.get("urgency", "MEDIUM")).strip().upper()
            if item.urgency not in ("CRITICAL", "HIGH", "MEDIUM", "LOW"):
                item.urgency = "MEDIUM"

        except Exception as exc:
            exc_str = str(exc)
            if "429" in exc_str or "RESOURCE_EXHAUSTED" in exc_str or "quota" in exc_str.lower():
                _quota_exhausted = True
                logger.warning("Gemini quota exhausted — using fallback summaries for all remaining items.")
            else:
                logger.exception("Gemini summary failed for %s", item.url)
            item = _fallback_summary(item)

        summarized.append(item)

    return summarized


# --- Email Delivery ---
SECTION_ORDER = [
    ("cybersecurity",    "🔴 Cybersecurity & Red Teaming"),
    ("student_benefits", "🎓 Student Deals & Free Benefits"),
    ("gaming_deals",     "🎮 Free Games & Limited-Time Offers"),
    ("ai_tools",         "🤖 AI & Dev Tools"),
    ("software_tools",   "🛠 New Software & Tools"),
]
MAX_PER_SECTION = 3

def render_digest_html(items: list[DigestItem], template_dir: Path | None = None) -> str:
    """Render the digest HTML email."""
    sections: dict[str, list[DigestItem]] = {key: [] for key, _ in SECTION_ORDER}
    for item in items:
        if item.category in sections:
            sections[item.category].append(item)

    critical_items = [item for item in items if item.urgency in ("CRITICAL", "HIGH")][:3]
    action_items = [
        item for item in items
        if any(w in f"{item.title} {item.why_it_matters} {item.action_to_take}".lower() for w in ("claim", "free", "student", "enroll", "patch", "cve", "exploit"))
    ][:8]

    directory = template_dir or PROJECT_ROOT / "templates"
    env = Environment(loader=FileSystemLoader(directory), autoescape=select_autoescape(["html", "xml", "j2"]))
    template = env.get_template("weekly_digest.html.j2")
    return template.render(
        critical_items=critical_items,
        sections=sections,
        section_order=SECTION_ORDER,
        max_per_section=MAX_PER_SECTION,
        action_items=action_items,
    )

def send_email(settings: Settings, subject: str, html_body: str) -> None:
    """Send the rendered digest over SMTP."""
    required = [settings.smtp_host, settings.smtp_username, settings.smtp_password, settings.email_from, settings.email_to]
    if not all(required):
        logger.warning("SMTP settings are incomplete; skipping email send.")
        return

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = settings.email_from
    message["To"] = settings.email_to
    message.set_content("Your email client does not support HTML. Open the digest link items manually.")
    message.add_alternative(html_body, subtype="html")

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as smtp:
        smtp.starttls()
        smtp.login(settings.smtp_username, settings.smtp_password)
        smtp.send_message(message)
        logger.info("Digest email sent to %s", settings.email_to)
