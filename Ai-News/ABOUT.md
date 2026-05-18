# About Personal Intelligence Digest

This document provides an exhaustive overview of the **Personal Intelligence Digest (Ai-News)** architecture, data pipeline, and logic.

## 💡 The Idea
In the modern era of rapid information generation, software engineers are overwhelmed by noise. Important security vulnerabilities, limited-time student deals, and critical developer tool updates are often buried under generic tech news and social media chatter. 

**Ai-News** was created to be a highly curated, noise-free, and automated intelligence digest. It bypasses social media completely, fetching data strictly from high-trust primary sources (CISA, Google Project Zero, GitHub releases, etc.), and processes them through an intelligent pipeline to deliver exactly what you need to know in under 2 minutes.

## 🏗️ Architectural Overview
The system relies on a flat, minimal **4-file modular architecture** located in the `app/` directory:

1. **`core.py` (Data Structures & Storage)**
   - Manages the SQLite database (`digest.sqlite3`) for persistent storage.
   - Defines the `DigestItem` schema and runtime `Settings`.
   - Normalizes URLs and titles to prevent duplicate processing.

2. **`collectors.py` (Data Ingestion)**
   - **RSS & Atom**: Aggregates direct feeds from security and tech blogs.
   - **Google News**: Dynamically translates specific keywords into RSS feeds.
   - **GitHub Releases**: Watches critical repositories for new tags and tool releases.
   - **Web Scraping**: Uses `BeautifulSoup` as a fallback for sites lacking RSS capabilities.

3. **`engine.py` (The Intelligence Engine)**
   - **Text Cleaning:** Strips messy HTML formatting and normalizes whitespace.
   - **Classifier:** Groups items into categories (`cybersecurity`, `ai_tools`, `software_tools`, `gaming_deals`, `student_benefits`) via keyword matching.
   - **Deduplicator:** Eliminates duplicate articles by cross-referencing normalized titles and URLs.
   - **Ranker:** Applies a weighted scoring system based on source trust score, recency, category priority, and high-value keywords (e.g., "CVE", "free").
   - **Summarizer (Gemini AI):** Passes the top-ranked articles to the `gemini-2.0-flash-lite` model. It forces the AI to output strict JSON containing a 1-sentence "Why it matters", a direct "Action to take", a deadline (if applicable), and an Urgency rating (`CRITICAL`, `HIGH`, `MEDIUM`, `LOW`).

4. **`main.py` (Orchestration)**
   - The primary entry point.
   - Collects items -> Prepares/Scores them -> Inserts into DB -> Fetches recent top items -> Summarizes -> Renders HTML -> Emails via SMTP.

## ⚙️ Configuration & Tuning
The project behavior is entirely separated into the `config/` directory:
- **`sources.yaml`**: The list of all RSS feeds, GitHub repos, and their assigned `trust_score` (1-10).
- **`topics.yaml`**: The specific keyword queries fed into the Google News engine.
- **`scoring_rules.yaml`**: The mathematical weights used by the Ranker. You can tweak how much recency matters versus keyword hits.

## 🚀 CI/CD & Automation
The tool operates fully autonomously via GitHub Actions (`.github/workflows/weekly_digest.yml`).
Every Monday at 07:00 UTC (10:00 AM UTC+3), a runner is spun up. It installs the environment, runs the pipeline using repository secrets for the Gemini API and SMTP credentials, and emails the digest completely hands-free.
