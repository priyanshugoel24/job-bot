#!/usr/bin/env python3
"""
Job Bot — Main Runner
Priyanshu Goel | DTU CS 2026 | Targeting 20LPA+ SDE-1

Usage:
    python main.py                    # Full run: scrape + AI tailor top 10
    python main.py --scrape-only      # Only scrape, save to output/jobs.json
    python main.py --apply-only       # Generate cover letters for saved jobs
    python main.py --job-url URL      # Tailor a single job URL
    python main.py --demo             # Demo mode (no browser, no API needed)
"""

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("JobBot")

from config import (
    OUTPUT_DIR, JOBS_FILE, APPLICATIONS_FILE,
    COVER_LETTERS_DIR, PROFILE, CREDENTIALS, GEMINI_API_KEY,
    SEARCH_FILTERS
)


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def ensure_dirs():
    for d in [OUTPUT_DIR, COVER_LETTERS_DIR]:
        os.makedirs(d, exist_ok=True)


def save_jobs(jobs: list):
    ensure_dirs()
    with open(JOBS_FILE, "w") as f:
        json.dump(jobs, f, indent=2, default=str)
    log.info(f"Saved {len(jobs)} jobs → {JOBS_FILE}")


def load_jobs() -> list:
    if not os.path.exists(JOBS_FILE):
        log.error(f"No jobs file found at {JOBS_FILE}. Run with --scrape-only first.")
        return []
    with open(JOBS_FILE) as f:
        return json.load(f)


def load_applications() -> list:
    if not os.path.exists(APPLICATIONS_FILE):
        return []
    with open(APPLICATIONS_FILE) as f:
        return json.load(f)


def save_application(job: dict, cover_letter: str, form_answers: dict = None):
    apps = load_applications()
    apps.append({
        "job_id": job.get("id"),
        "title": job["title"],
        "company": job["company"],
        "location": job.get("location"),
        "salary_text": job.get("salary_text"),
        "url": job.get("url"),
        "source": job.get("source"),
        "match_score": job.get("match_score"),
        "cover_letter": cover_letter,
        "form_answers": form_answers,
        "status": "ready",
        "applied_at": None,
        "applied_date": None,
        "created_at": datetime.now().isoformat(),
    })
    with open(APPLICATIONS_FILE, "w") as f:
        json.dump(apps, f, indent=2, default=str)


def print_banner():
    print("\n" + "=" * 60)
    print("  JOB BOT — Priyanshu Goel | DTU CS 2026")
    print(f"  Target: {PROFILE['target_ctc_min']}+ LPA | SDE-1 / SWE")
    print(f"  Locations: {', '.join(SEARCH_FILTERS['locations'][:4])}")
    print("=" * 60 + "\n")


def print_job(job: dict, idx: int):
    print(f"\n  [{idx}] {job['title']} @ {job['company']}")
    print(f"       Location : {job.get('location', 'N/A')}")
    print(f"       CTC      : {job.get('salary_text', 'Not listed')}")
    print(f"       Source   : {job.get('source', 'N/A')}")
    print(f"       Posted   : {job.get('posted', 'N/A')}")
    print(f"       Match    : {job.get('match_score', 0)}%")
    print(f"       URL      : {job.get('url', '')}")


# ─────────────────────────────────────────────────────────────────────────────
# SCRAPE
# ─────────────────────────────────────────────────────────────────────────────

def run_scrape(sources: list = None) -> list:
    """Run all enabled scrapers and return deduplicated job list."""
    if sources is None:
        sources = ["linkedin", "naukri", "instahyre", "cutshort"]

    all_jobs = []
    seen_ids = set()

    def add_jobs(new_jobs):
        for j in new_jobs:
            if j["id"] not in seen_ids:
                seen_ids.add(j["id"])
                all_jobs.append(j)

    if "linkedin" in sources:
        if not CREDENTIALS["linkedin"]["email"]:
            log.warning("LinkedIn credentials not set — skipping LinkedIn scraper.")
        else:
            log.info("─── Starting LinkedIn scraper ───")
            try:
                from scrapers.linkedin_scraper import LinkedInScraper
                jobs = LinkedInScraper(headless=False).scrape()
                add_jobs(jobs)
                log.info(f"LinkedIn: {len(jobs)} jobs")
            except Exception as e:
                log.error(f"LinkedIn scraper failed: {e}")

    if "naukri" in sources:
        log.info("─── Starting Naukri scraper ───")
        try:
            from scrapers.naukri_scraper import NaukriScraper
            jobs = NaukriScraper(headless=False).scrape()
            add_jobs(jobs)
            log.info(f"Naukri: {len(jobs)} jobs")
        except Exception as e:
            log.error(f"Naukri scraper failed: {e}")

    if "instahyre" in sources:
        log.info("─── Starting Instahyre scraper ───")
        try:
            from scrapers.other_scrapers import InstaHyreScraper
            jobs = InstaHyreScraper().scrape()
            add_jobs(jobs)
            log.info(f"Instahyre: {len(jobs)} jobs")
        except Exception as e:
            log.error(f"Instahyre scraper failed: {e}")

    if "cutshort" in sources:
        log.info("─── Starting Cutshort scraper ───")
        try:
            from scrapers.other_scrapers import CutshortScraper
            jobs = CutshortScraper().scrape()
            add_jobs(jobs)
            log.info(f"Cutshort: {len(jobs)} jobs")
        except Exception as e:
            log.error(f"Cutshort scraper failed: {e}")

    # Sort by match score
    all_jobs.sort(key=lambda j: j["match_score"], reverse=True)
    return all_jobs


# ─────────────────────────────────────────────────────────────────────────────
# APPLY
# ─────────────────────────────────────────────────────────────────────────────

def run_apply(jobs: list, top_n: int = 10, auto_mode: bool = False):
    """
    Generate tailored applications for top N jobs.
    In interactive mode, prompts user to confirm each one.
    """
    if not GEMINI_API_KEY:
        log.error("GEMINI_API_KEY not set in config.py — cannot generate AI cover letters.")
        log.error("Get your FREE key (no card) at: https://aistudio.google.com/app/apikey")
        return

    from utils.ai_generator import ApplicationGenerator
    gen = ApplicationGenerator()

    top_jobs = jobs[:top_n]
    log.info(f"\nGenerating applications for top {len(top_jobs)} jobs...\n")

    for i, job in enumerate(top_jobs):
        print_job(job, i + 1)

        if not auto_mode:
            choice = input("\n  Generate application for this job? [Y/n/s(skip all)]: ").strip().lower()
            if choice == "s":
                log.info("Stopping application generation.")
                break
            if choice == "n":
                continue

        print(f"\n  Generating cover letter for {job['title']} @ {job['company']}...")
        try:
            cover_letter = gen.generate_cover_letter(job)
            print("\n" + "-" * 60)
            print(cover_letter)
            print("-" * 60)

            # Save to file
            safe_company = job['company'].replace(' ', '_').replace('/', '-')
            filename = f"{COVER_LETTERS_DIR}/{job['id']}_{safe_company}.txt"
            ensure_dirs()
            with open(filename, "w") as f:
                f.write(f"Role: {job['title']}\nCompany: {job['company']}\n")
                f.write(f"Date: {datetime.now().strftime('%d %b %Y')}\n")
                f.write(f"URL: {job.get('url', '')}\n")
                f.write("=" * 40 + "\n\n")
                f.write(cover_letter)

            # Optional: form answers
            form_answers = None
            if not auto_mode:
                gen_forms = input("\n  Also generate form Q&A answers? [y/N]: ").strip().lower()
                if gen_forms == "y":
                    print("  Generating form answers...")
                    form_answers = gen.generate_form_answers(job)
                    print("\n  FORM ANSWERS:")
                    for q, a in form_answers.items():
                        print(f"\n  {q.upper()}:\n  {a}")

            save_application(job, cover_letter, form_answers)
            log.info(f"  ✓ Saved → {filename}")

        except Exception as e:
            log.error(f"  Failed: {e}")

        if i < len(top_jobs) - 1:
            time.sleep(0.5)


# ─────────────────────────────────────────────────────────────────────────────
# DEMO MODE
# ─────────────────────────────────────────────────────────────────────────────

def run_demo():
    """Demo mode: shows sample output without any browser or API calls."""
    print("\n📋 DEMO MODE — Sample job results:\n")

    sample_jobs = [
        {"id": "demo_1", "title": "SDE-1 (Backend)", "company": "Razorpay",
         "location": "Bangalore", "salary_text": "25-35 LPA", "source": "Instahyre",
         "posted": "2 days ago", "match_score": 91,
         "description": "We're looking for a backend engineer...",
         "url": "https://instahyre.com/jobs/razorpay-sde1"},
        {"id": "demo_2", "title": "Software Engineer I", "company": "Google",
         "location": "Bangalore", "salary_text": "30-45 LPA", "source": "LinkedIn",
         "posted": "3 days ago", "match_score": 84,
         "description": "Join Google's engineering team...",
         "url": "https://careers.google.com/jobs/1"},
        {"id": "demo_3", "title": "Backend Engineer", "company": "CRED",
         "location": "Bangalore", "salary_text": "22-30 LPA", "source": "Cutshort",
         "posted": "Today", "match_score": 88,
         "description": "Build high-scale fintech systems...",
         "url": "https://cred.club/careers"},
    ]

    for i, job in enumerate(sample_jobs):
        print_job(job, i + 1)

    save_jobs(sample_jobs)
    print(f"\n  Demo jobs saved to {JOBS_FILE}")

    if GEMINI_API_KEY:
        print("\n  Generating sample cover letter for Razorpay...\n")
        from utils.ai_generator import ApplicationGenerator
        gen = ApplicationGenerator()
        letter = gen.generate_cover_letter(sample_jobs[0])
        print("-" * 60)
        print(letter)
        print("-" * 60)
    else:
        print("\n  Set GEMINI_API_KEY in config.py to generate AI cover letters.")
        print("     Get it FREE (no card) at: https://aistudio.google.com/app/apikey\n")


# ─────────────────────────────────────────────────────────────────────────────
# STATUS REPORT
# ─────────────────────────────────────────────────────────────────────────────

def print_status():
    apps = load_applications()
    jobs = load_jobs()

    print("\n" + "=" * 50)
    print("  APPLICATION STATUS")
    print("=" * 50)
    print(f"  Jobs scraped  : {len(jobs)}")
    print(f"  Applications  : {len(apps)}")
    print(f"  Applied       : {sum(1 for a in apps if a.get('applied_at'))}")
    print(f"  Pending       : {sum(1 for a in apps if not a.get('applied_at'))}")

    statuses = {}
    for a in apps:
        s = a.get("status", "ready")
        statuses[s] = statuses.get(s, 0) + 1

    for s, count in statuses.items():
        print(f"  {s.capitalize():12}: {count}")

    print("=" * 50)


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Job Application Bot — Priyanshu Goel",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py                        # Full run
  python main.py --demo                 # Demo (no browser/API needed)
  python main.py --scrape-only          # Only scrape
  python main.py --apply-only           # Generate cover letters for saved jobs
  python main.py --apply-only --auto    # Auto mode (no prompts)
  python main.py --sources li,nk        # Only LinkedIn + Naukri
  python main.py --top 20              # Generate for top 20 jobs
  python main.py --status              # Show current application stats
        """
    )
    parser.add_argument("--scrape-only", action="store_true", help="Only scrape jobs")
    parser.add_argument("--apply-only", action="store_true", help="Only generate applications for saved jobs")
    parser.add_argument("--demo", action="store_true", help="Demo mode — no credentials needed")
    parser.add_argument("--status", action="store_true", help="Show application stats")
    parser.add_argument("--auto", action="store_true", help="Auto mode — no interactive prompts")
    parser.add_argument("--top", type=int, default=10, help="Number of top jobs to apply to (default: 10)")
    parser.add_argument("--sources", type=str, default="li,nk,ih,cs",
                        help="Comma-separated sources: li=LinkedIn, nk=Naukri, ih=Instahyre, cs=Cutshort")

    args = parser.parse_args()
    print_banner()

    source_map = {"li": "linkedin", "nk": "naukri", "ih": "instahyre", "cs": "cutshort"}
    sources = [source_map[s.strip()] for s in args.sources.split(",") if s.strip() in source_map]

    if args.status:
        print_status()
        return

    if args.demo:
        run_demo()
        return

    if args.apply_only:
        jobs = load_jobs()
        if jobs:
            run_apply(jobs, top_n=args.top, auto_mode=args.auto)
        return

    # Default: scrape then apply
    log.info("Starting job scrape...")
    jobs = run_scrape(sources=sources)

    if not jobs:
        log.warning("No jobs scraped. Check credentials and network.")
        return

    save_jobs(jobs)
    log.info(f"\n✓ Scraped {len(jobs)} jobs. Top results:")
    for job in jobs[:5]:
        print_job(job, jobs.index(job) + 1)

    if not args.scrape_only:
        print(f"\n\nTop {args.top} jobs ready for applications.")
        run_apply(jobs, top_n=args.top, auto_mode=args.auto)

    print_status()


if __name__ == "__main__":
    main()
