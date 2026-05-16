# Job Application Bot 🤖
**Priyanshu Goel | DTU CS 2026 | Targeting 20LPA+ SDE-1 roles**

A fully automated job hunting system that scrapes LinkedIn, Naukri, Instahyre, and Cutshort — then uses Claude AI to generate custom cover letters and application answers for each job.

---

## Setup (15 minutes)

### Step 1 — Install Python dependencies
```bash
pip install -r requirements.txt
```

### Step 2 — Install Chrome + ChromeDriver
The scrapers use Selenium with Chrome.
- **Chrome**: https://www.google.com/chrome
- **ChromeDriver**: Download the version matching your Chrome from https://chromedriver.chromium.org
  - Add it to your PATH or place it in this folder

```bash
# Verify Chrome driver works
chromedriver --version
```

### Step 3 — Fill in config.py
Open `config.py` and fill in:

```python
CREDENTIALS = {
    "linkedin": {
        "email": "your@email.com",       # Your LinkedIn login email
        "password": "yourpassword",       # Your LinkedIn password
    },
    "naukri": {
        "email": "your@email.com",
        "password": "yourpassword",
    },
}

ANTHROPIC_API_KEY = "sk-ant-..."  # Get from console.anthropic.com (free tier available)
```

> **Security note:** These credentials are stored locally only — never uploaded anywhere.

### Step 4 — Test with demo mode
```bash
python main.py --demo
```
This runs without any browser or API calls, to verify your setup.

---

## Usage

### Full run (scrape all platforms + generate cover letters)
```bash
python main.py
```
This will:
1. Open Chrome and log into LinkedIn + Naukri
2. Scrape SDE-1/SWE jobs matching your filters (20LPA+, Bangalore/Noida/Gurgaon/Hyderabad/Pune/Remote)
3. Score and rank all jobs by profile match
4. Interactively generate AI-tailored cover letters for the top 10
5. Save everything to `output/`

### Scrape only (no cover letter generation)
```bash
python main.py --scrape-only
```

### Generate cover letters for previously scraped jobs
```bash
python main.py --apply-only
```

### Auto mode (no prompts — generates for top 10 automatically)
```bash
python main.py --auto --top 15
```

### Target specific platforms only
```bash
python main.py --sources li,nk        # LinkedIn + Naukri only
python main.py --sources ih,cs        # Instahyre + Cutshort only (no login needed)
```

### Check application status
```bash
python main.py --status
```

---

## Output Files

After running, the `output/` folder contains:

| File | Contents |
|------|----------|
| `output/jobs.json` | All scraped jobs with scores |
| `output/applications.json` | Generated applications with status tracking |
| `output/cover_letters/` | Individual cover letter `.txt` files per job |

---

## How the match score works

Each job is scored 0–100 based on:
- **Role match** (+25): "Software Engineer / SDE / SWE" = best match
- **Level match** (+10): Entry-level / SDE-1 keywords
- **Company tier** (+10): Top MNCs or Indian unicorns
- **Skills overlap** (+up to 15): Your skills appearing in the JD
- **Senior role penalty** (−40): "Senior / Lead / Staff" — auto-filtered

Jobs scoring **80+** are strong fits. The bot prioritizes these first.

---

## Cover letter strategy

The AI generates letters that:
- **Lead with Paytm** (current backend internship + upcoming SDE-1 promotion)
- **Mention DTU CGPA** (8.36 is strong for MNC screening)
- **Highlight HackFlow** (live product, 35% perf improvement — strong signal)
- **State salary expectation** naturally (20–40 LPA)
- **Stay under 220 words** (hiring managers don't read long letters)
- **Are company-specific** — different letter for Razorpay vs Google vs Zepto

---

## Tips for 20LPA+ roles

**Platforms to prioritize:**
- **Instahyre** — best for funded startups and unicorns, salary is usually listed
- **LinkedIn Easy Apply** — volume play for MNCs
- **Naukri** — good for mid-size product companies
- **Cutshort** — strong for early-stage well-funded startups

**Companies most likely to offer 20LPA+ to a strong fresher from DTU:**
- Razorpay, CRED, PhonePe, Groww, Zepto (25–35 LPA range)
- Google, Microsoft, Adobe, Goldman Sachs (30–45 LPA range)
- Meesho, Zomato, Swiggy, Ola (20–28 LPA range)
- Atlassian, Sprinklr, Nutanix (30–40 LPA, Bangalore remote-friendly)

**Things to add to your resume before mass applying:**
1. Add Paytm internship with 2–3 backend-specific bullet points
2. Add "High-scale systems" / "distributed systems" keywords
3. Mention any specific backend tech at Paytm (Kafka, Redis, etc.)
4. Consider adding your LeetCode/Codeforces rating if it's strong (700+ on CF or 1700+ on LC)

---

## Running the daily scheduler

```bash
python3 scheduler.py
```

Runs forever in the foreground. Every day at 8:00 AM it will:
1. Scrape all platforms (LinkedIn / Naukri / Instahyre / Cutshort)
2. Diff results against the previously saved `output/jobs.json`
3. Generate cover letters for the top 5 new jobs
4. Email a digest to `priyanshugoel24@gmail.com`

**To run in background on Mac** (keeps running after the terminal closes):
```bash
nohup python3 scheduler.py > output/scheduler.log 2>&1 &
```

**To test immediately** (triggers the full job without waiting for 8 AM):
```bash
python3 scheduler.py --test
```

### Email setup (required for digest emails)
Open `config.py` and fill in:
```python
GMAIL_SENDER = "you@gmail.com"      # The Gmail address that sends the email
GMAIL_APP_PASSWORD = "xxxx xxxx"    # Gmail App Password — NOT your regular password
```
Get an App Password at **myaccount.google.com/apppasswords** (requires 2FA enabled).

---

## Troubleshooting

**Chrome/Selenium issues:**
- Make sure ChromeDriver version matches your Chrome version exactly
- If LinkedIn shows a CAPTCHA, complete it manually — the script waits for you

**"No jobs found":**
- LinkedIn and Naukri frequently change their HTML structure — update the CSS selectors in the scraper files if needed
- Try `--sources ih,cs` (Instahyre + Cutshort) — these are more stable

**Cover letter quality:**
- The more detailed the job description you paste, the better the letter
- Edit `config.py` → `PROFILE["experiences"][0]["highlights"]` to add your specific Paytm work

**Rate limiting:**
- Don't scrape more than ~3 pages per query on LinkedIn (risk of temporary block)
- The bot adds polite delays (2s) between requests automatically
