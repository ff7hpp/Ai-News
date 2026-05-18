# Personal Intelligence Digest

A sleek, automated, AI-powered weekly intelligence digest for software engineers. 
It bypasses the noise of social media by scraping high-trust sources (CISA, Google Project Zero, GitHub releases, BleepingComputer, Epic Games) directly. It then classifies, deduplicates, scores, and summarizes the top news using the Gemini AI into a scannable, premium HTML email.

## What It Produces
A weekly email containing the top curated links of the week, organized by urgency and category, designed to be read in under 2 minutes:
- **Need to Know Now:** Critical vulnerabilities, expiring deals, and high-urgency news.
- **Cybersecurity:** Top red team tools, CVE patches, and advisory news.
- **Student Deals & Free Games:** The best software benefits and limited-time game claims.
- **AI & Developer Tools:** The latest open-source tool releases and AI coding updates.
- **Weekly Action Checklist:** Clear items to "Claim", "Patch", "Download", or "Enroll" before next Monday.

## Project Architecture
The project is built on a minimal, flat architecture consisting of 4 core modules in `app/`:

- `core.py`: Defines data structures (`DigestItem`), loads configurations, and handles the SQLite persistence layer (`Database`).
- `collectors.py`: Fetches raw data from RSS feeds, GitHub Atom releases, Google News RSS, and public webpages.
- `engine.py`: The intelligence pipeline. It cleans text, classifies by category, removes duplicates, ranks by score, and generates Gemini AI summaries and urgency labels.
- `main.py`: The entry point that orchestrates the data pipeline and renders/sends the final email.

## Setup Instructions

```powershell
# Clone and enter the repository
git clone https://github.com/yourusername/personal-intelligence-digest.git
cd personal-intelligence-digest

# Create and activate virtual environment
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install dependencies
python -m pip install --upgrade pip
pip install -r requirements.txt

# Copy environment variables
Copy-Item .env.example .env
```

### Environment Variables
Edit `.env` and fill in the following:
```env
GEMINI_API_KEY=your_gemini_api_key_here
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your_email@gmail.com
SMTP_PASSWORD=your_app_password
EMAIL_FROM=your_email@gmail.com
EMAIL_TO=recipient_email@gmail.com
```

## Running the Application

**Test Run (No Email):**
Run the pipeline to collect, store, and summarize items without triggering the SMTP send.
```powershell
python -m app.main --no-send
```

**Full Run (Send Email):**
Generate and email the final digest.
```powershell
python -m app.main
```

## Configuration Options
All scoring and sources are highly customizable in the `config/` directory:
- `sources.yaml`: Configure trusted RSS feeds, GitHub repos, and webpages. Trust scores directly impact ranking.
- `topics.yaml`: Configure Google News specific search queries for category matching.
- `scoring_rules.yaml`: Tweak how items are ranked (keywords, category bonuses, recency decay).

## Automated GitHub Actions
The project includes a `.github/workflows/weekly_digest.yml` which automatically runs every Monday at 10:00 AM (UTC+3). 
To set this up, add the environment variables from your `.env` file as **Repository Secrets** in your GitHub repository settings.
