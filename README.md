# 🤖 Job Hunter Agent
### Automated DevOps/SRE Job Search for International Relocation
**For: Jesús Enrique Quevedo Torres | Principal DevOps Engineer @ Oracle**

Searches and applies to DevOps/SRE jobs in Canada, New Zealand, Sweden, Germany, and Poland — automatically.

---

## 🗂 Project Structure

```
job-hunter-agent/
├── config/
│   ├── settings.py          ← Keywords, countries, limits
│   └── cv_data.py           ← Your CV as structured data
├── scrapers/
│   ├── base_scraper.py      ← JobPosting dataclass + base class
│   ├── linkedin_scraper.py  ← LinkedIn Jobs (all countries)
│   └── country_scrapers.py  ← Seek NZ, StepStone DE, Pracuj PL, Arbetsformedlingen SE
├── ai_engine/
│   └── cover_letter.py      ← Claude API: scores jobs + generates cover letters
├── applier/
│   └── form_filler.py       ← Playwright: fills LinkedIn Easy Apply forms
├── tracker/
│   └── sheets_tracker.py    ← Google Sheets + CSV fallback
├── assets/
│   └── Resume_DevOps_SRE.pdf  ← ⚠️ PUT YOUR CV HERE
├── agent.py                 ← Main orchestrator
├── Dockerfile               ← For containerized deployment
└── requirements.txt
```

---

## 🚀 Quick Start

### 1. Prerequisites

```bash
# Requires Python 3.12+
python3 --version  # should show 3.12.x or higher

# Install Poetry (dependency manager)
curl -sSL https://install.python-poetry.org | python3 -
```

### 2. Clone & Install

```bash
git clone https://github.com/YOUR_USERNAME/job-hunter-agent.git
cd job-hunter-agent

# Install all dependencies (creates .venv automatically)
poetry install

# Install Playwright's Chromium browser
poetry run playwright install chromium
```

### 3. Configure

```bash
cp .env.example .env
# Edit .env with your API keys and credentials
```

### 4. Add your CV

```bash
cp /path/to/your/Resume_DevOps_SRE.pdf assets/Resume_DevOps_SRE.pdf
```

### 5. Test with a dry run

```bash
# Scrape and score jobs, but don't apply
poetry run python agent.py --dry-run

# Only search Canada
poetry run python agent.py --dry-run --country Canada
```

### 6. Run live

```bash
# Single run
poetry run python agent.py

# Daily schedule (runs at 9 AM every day)
poetry run python agent.py --schedule
```

---

## 🐳 Docker Deployment (recommended)

```bash
# Build
docker build -t job-hunter-agent .

# Run once
docker run --env-file .env \
  -v $(pwd)/assets:/app/assets \
  -v $(pwd)/credentials.json:/app/credentials.json \
  job-hunter-agent python agent.py --dry-run

# Run scheduled (on a $5/mo DigitalOcean droplet)
docker run -d --restart unless-stopped \
  --env-file .env \
  -v $(pwd)/assets:/app/assets \
  -v $(pwd)/credentials.json:/app/credentials.json \
  job-hunter-agent
```

---

## 🔑 API Keys Setup

### Anthropic API Key
1. Go to https://console.anthropic.com
2. Create API key → add to `.env`

### Google Sheets Setup
1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a new project
3. Enable **Google Sheets API** and **Google Drive API**
4. Create a **Service Account** → download JSON credentials
5. Save as `credentials.json` in project root
6. Create a Google Sheet
7. **Share the sheet** with the service account email (from credentials.json)
8. Copy the Sheet ID from the URL → add to `.env`

---

## ⚙️ Customization

### Adjust job keywords (`config/settings.py`)
```python
keywords = [
    "Principal DevOps Engineer",
    "Senior SRE",
    "Cloud Platform Engineer",
    # Add more...
]
```

### Change scoring threshold
```python
min_score_to_apply = 70  # Only apply to jobs scored ≥ 70/100
```

### Change daily limit
```python
max_daily_applications = 20  # Be responsible!
```

---

## 📊 Tracking Sheet Columns

| Column | Description |
|--------|-------------|
| Job ID | Unique hash identifier |
| Title | Job title |
| Company | Company name |
| Location | City/region |
| Country | Target country |
| Source | linkedin / seek / stepstone / pracuj |
| Score | AI relevance score (0-100) |
| Status | found / scored / applied / interview |
| Easy Apply | Yes/No |
| Salary | Range if available |
| Posted Date | When job was posted |
| Applied Date | When you applied |
| URL | Job posting link |
| Cover Letter | Preview of generated letter |

---

## ⚠️ Important Notes

- **LinkedIn ToS**: Automated LinkedIn access may violate their Terms of Service. Use responsibly and consider using a secondary account for testing.
- **Rate limiting**: The agent has built-in delays. Don't increase them aggressively.
- **Work Authorization**: The form filler is configured to indicate you'll need visa/work permit sponsorship. Review `applier/form_filler.py` → `EASY_APPLY_ANSWERS`.
- **Canada**: No separate portal scraper; LinkedIn covers it well.
- **Germany**: StepStone is the primary portal; XING is also popular but harder to scrape.

---

## 🛠 Troubleshooting

**LinkedIn login fails?**
→ LinkedIn may require CAPTCHA. Try logging in manually first, then rerun.

**Playwright browser errors?**
→ Run `playwright install chromium --with-deps`

**Google Sheets 403 error?**
→ Make sure you shared the sheet with the service account email.

---

Built with ❤️ for Jesús's international job search. Good luck! 🌍