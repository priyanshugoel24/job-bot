#!/usr/bin/env python3
"""
Job Bot — Daily Scheduler
Runs every day at 8:00 AM, diffs against previously seen jobs,
generates cover letters for the top 5 new ones, and emails a digest.

Usage:
    python3 scheduler.py          # Runs forever, triggers at 8 AM daily
    python3 scheduler.py --test   # Triggers the job immediately (for testing)
"""

import argparse
import json
import logging
import os
import smtplib
import sys
import time
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import schedule

from config import (
    COVER_LETTERS_DIR, GEMINI_API_KEY, GMAIL_APP_PASSWORD,
    GMAIL_SENDER, JOBS_FILE, NOTIFY_EMAIL, OUTPUT_DIR, SCHEDULER_LOG,
)

# ─────────────────────────────────────────
# LOGGING — file + console
# ─────────────────────────────────────────

os.makedirs(OUTPUT_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(SCHEDULER_LOG),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("Scheduler")


# ─────────────────────────────────────────
# JOB DIFF
# ─────────────────────────────────────────

def load_saved_jobs() -> list:
    if not os.path.exists(JOBS_FILE):
        return []
    with open(JOBS_FILE) as f:
        return json.load(f)


def save_jobs(jobs: list):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(JOBS_FILE, "w") as f:
        json.dump(jobs, f, indent=2, default=str)


def find_new_jobs(current_jobs: list, previous_jobs: list) -> list:
    seen_urls = {j.get("url") for j in previous_jobs if j.get("url")}
    return [j for j in current_jobs if j.get("url") not in seen_urls]


# ─────────────────────────────────────────
# COVER LETTER GENERATION
# ─────────────────────────────────────────

def generate_cover_letters(jobs: list, top_n: int = 5) -> dict:
    """Returns {job_id: cover_letter_text} for up to top_n jobs."""
    if not GEMINI_API_KEY:
        log.warning("GEMINI_API_KEY not set — skipping cover letter generation.")
        return {}

    from utils.ai_generator import ApplicationGenerator
    gen = ApplicationGenerator()
    letters = {}

    for job in jobs[:top_n]:
        try:
            log.info(f"Generating cover letter for {job['title']} @ {job['company']}")
            letter = gen.generate_cover_letter(job)
            letters[job["id"]] = letter

            # Persist to file
            os.makedirs(COVER_LETTERS_DIR, exist_ok=True)
            safe_company = job["company"].replace(" ", "_").replace("/", "-")
            path = f"{COVER_LETTERS_DIR}/{job['id']}_{safe_company}.txt"
            with open(path, "w") as f:
                f.write(f"Role: {job['title']}\nCompany: {job['company']}\n")
                f.write(f"Date: {datetime.now().strftime('%d %b %Y')}\n")
                f.write(f"URL: {job.get('url', '')}\n")
                f.write("=" * 40 + "\n\n")
                f.write(letter)
        except Exception as e:
            log.error(f"Cover letter failed for {job.get('title')}: {e}")

    return letters


# ─────────────────────────────────────────
# EMAIL
# ─────────────────────────────────────────

SOURCE_MAP = {
    "linkedin": "LinkedIn",
    "naukri": "Naukri",
    "instahyre": "Instahyre",
    "cutshort": "Cutshort",
}


def build_email_body(new_jobs: list, cover_letters: dict) -> str:
    today = datetime.now().strftime("%d %b %Y")

    # Source breakdown for summary line
    source_counts: dict = {}
    for j in new_jobs:
        src = SOURCE_MAP.get(j.get("source", "").lower(), j.get("source", "Unknown"))
        source_counts[src] = source_counts.get(src, 0) + 1
    source_summary = " / ".join(f"{v} {k}" for k, v in sorted(source_counts.items()))

    lines = [
        f"Job Bot Daily Digest — {today}",
        "=" * 60,
        f"{len(new_jobs)} new jobs found across {source_summary or 'all platforms'}",
        "",
    ]

    for i, job in enumerate(new_jobs, 1):
        lines += [
            f"[{i}] {job['title']} @ {job['company']}",
            f"    Location  : {job.get('location', 'N/A')}",
            f"    Salary    : {job.get('salary_text', 'Not listed')}",
            f"    Match     : {job.get('match_score', 0)}%",
            f"    Source    : {job.get('source', 'N/A')}",
            f"    URL       : {job.get('url', '')}",
        ]
        letter = cover_letters.get(job.get("id"))
        if letter:
            lines += [
                "",
                "    --- Cover Letter ---",
            ]
            for ll in letter.splitlines():
                lines.append("    " + ll)
        lines += ["", "-" * 60, ""]

    if not cover_letters:
        lines.append("(Cover letter generation was skipped — set GEMINI_API_KEY in config.py)")

    lines += [
        "",
        "— Job Bot",
        "Run: python3 scheduler.py --test to trigger manually",
    ]
    return "\n".join(lines)


def send_email(subject: str, body: str):
    if not GMAIL_SENDER or not GMAIL_APP_PASSWORD:
        log.warning(
            "Email not sent — GMAIL_SENDER or GMAIL_APP_PASSWORD not set in config.py.\n"
            "Get an App Password at: myaccount.google.com/apppasswords"
        )
        log.info("Email body (would have been sent):\n" + body)
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = GMAIL_SENDER
    msg["To"] = NOTIFY_EMAIL
    msg.attach(MIMEText(body, "plain"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(GMAIL_SENDER, GMAIL_APP_PASSWORD)
            smtp.sendmail(GMAIL_SENDER, NOTIFY_EMAIL, msg.as_string())
        log.info(f"Email sent to {NOTIFY_EMAIL}")
    except Exception as e:
        log.error(f"Failed to send email: {e}")


# ─────────────────────────────────────────
# SCRAPE (reuses main.py logic)
# ─────────────────────────────────────────

def run_scrape() -> list:
    from main import run_scrape as _scrape
    return _scrape(sources=["linkedin", "naukri", "instahyre", "cutshort"])


# ─────────────────────────────────────────
# MAIN SCHEDULED JOB
# ─────────────────────────────────────────

def scheduled_job():
    log.info("=" * 60)
    log.info("Scheduled job starting")
    log.info("=" * 60)

    # 1. Scrape fresh jobs
    log.info("Step 1/4 — Scraping all platforms...")
    try:
        current_jobs = run_scrape()
    except Exception as e:
        log.error(f"Scrape failed: {e}")
        return
    log.info(f"Scraped {len(current_jobs)} jobs total")

    # 2. Diff against saved jobs
    log.info("Step 2/4 — Diffing against previously seen jobs...")
    previous_jobs = load_saved_jobs()
    new_jobs = find_new_jobs(current_jobs, previous_jobs)
    log.info(f"Found {len(new_jobs)} new jobs ({len(previous_jobs)} already seen)")

    # Save the updated full list (previous + new) so next run diffs correctly
    all_seen = previous_jobs + new_jobs
    save_jobs(all_seen)

    if not new_jobs:
        log.info("No new jobs today — skipping cover letter generation and email.")
        return

    # 3. Generate cover letters for top 5 new jobs
    log.info("Step 3/4 — Generating cover letters for top 5 new jobs...")
    top_new = sorted(new_jobs, key=lambda j: j.get("match_score", 0), reverse=True)
    cover_letters = generate_cover_letters(top_new, top_n=5)
    log.info(f"Generated {len(cover_letters)} cover letter(s)")

    # 4. Send email digest
    log.info("Step 4/4 — Sending email digest...")
    today_str = datetime.now().strftime("%d %b %Y")
    subject = f"Job Bot — {len(new_jobs)} new jobs found [{today_str}]"
    body = build_email_body(top_new, cover_letters)
    send_email(subject, body)

    log.info("Scheduled job complete.")


# ─────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Job Bot Daily Scheduler")
    parser.add_argument(
        "--test",
        action="store_true",
        help="Trigger the job immediately instead of waiting for 8 AM",
    )
    args = parser.parse_args()

    if args.test:
        log.info("--test flag detected: running job immediately.")
        scheduled_job()
        return

    schedule.every().day.at("08:00").do(scheduled_job)
    log.info("Scheduler started — job will run daily at 08:00 AM.")
    log.info("Press Ctrl+C to stop.")

    while True:
        schedule.run_pending()
        time.sleep(60)


if __name__ == "__main__":
    main()
