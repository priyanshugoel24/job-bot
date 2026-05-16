"""
Instahyre & Cutshort Scrapers
These platforms are more API-friendly and don't require Selenium login.

Usage:
    from scrapers.other_scrapers import InstaHyreScraper, CutshortScraper
    jobs = InstaHyreScraper().scrape()
"""

import time
import requests
import logging
from datetime import datetime
from typing import Optional
from bs4 import BeautifulSoup

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import SEARCH_FILTERS, PROFILE

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")


# ─────────────────────────────────────────────────────────────────────────────
# INSTAHYRE
# ─────────────────────────────────────────────────────────────────────────────
class InstaHyreScraper:
    """
    Instahyre has a semi-public JSON API used by their frontend.
    No authentication required for search results.
    """
    API_URL = "https://www.instahyre.com/api/v1/opportunity/"
    logger = logging.getLogger("Instahyre")

    ROLE_MAP = {
        "Software Developer": "software-development",
        "Software Engineer": "software-development",
        "Backend Developer": "backend",
        "Full Stack Developer": "full-stack",
    }

    def _score(self, title: str, skills: list, company: str) -> int:
        score = 50
        t = title.lower()
        if any(r in t for r in ["software engineer", "software developer", "sde"]):
            score += 20
        elif "backend" in t:
            score += 15
        if any(x in t for x in ["senior", "lead", "staff"]):
            score -= 35
        hits = sum(1 for s in PROFILE["skills"] if s.lower() in [sk.lower() for sk in skills])
        score += min(hits * 3, 15)
        return max(0, min(100, score))

    def scrape(self) -> list:
        jobs = []
        seen = set()

        params = {
            "format": "json",
            "experience_range_min": 0,
            "experience_range_max": 1,
            "locations": "Bangalore,Noida,Gurgaon,Hyderabad,Pune,Remote",
            "limit": 50,
            "offset": 0,
        }

        headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
            "Referer": "https://www.instahyre.com/candidate/opportunities/",
        }

        self.logger.info("Scraping Instahyre...")

        for role_name in list(self.ROLE_MAP.keys())[:2]:
            params["offset"] = 0
            for _ in range(3):  # Up to 3 pages
                try:
                    resp = requests.get(self.API_URL, params=params, headers=headers, timeout=15)
                    if resp.status_code != 200:
                        self.logger.warning(f"HTTP {resp.status_code} from Instahyre")
                        break

                    data = resp.json()
                    results = data.get("results", [])
                    if not results:
                        break

                    for item in results:
                        try:
                            job_id = str(item.get("id", ""))
                            if job_id in seen:
                                continue
                            seen.add(job_id)

                            title = item.get("title", "")
                            company = item.get("company", {}).get("name", "")
                            location = ", ".join(item.get("locations", []))
                            skills = [s.get("name", "") for s in item.get("skills", [])]
                            ctc_min = item.get("ctc_min", 0)  # In LPA
                            ctc_max = item.get("ctc_max", 0)
                            url = f"https://www.instahyre.com/jobs/{job_id}/"

                            # Filter by minimum CTC
                            if ctc_min and ctc_min < SEARCH_FILTERS["min_ctc_lpa"]:
                                continue

                            # Skip senior roles
                            if any(x in title.lower() for x in SEARCH_FILTERS["excluded_roles"]):
                                continue

                            score = self._score(title, skills, company)

                            salary_text = f"{ctc_min}-{ctc_max} LPA" if ctc_min else ""

                            jobs.append({
                                "id": f"ih_{job_id}",
                                "title": title,
                                "company": company,
                                "location": location,
                                "salary_text": salary_text,
                                "salary_lpa": ctc_min or None,
                                "skills": skills,
                                "description": item.get("description", ""),
                                "url": url,
                                "source": "Instahyre",
                                "posted": item.get("created_at", "")[:10],
                                "match_score": score,
                                "scraped_at": datetime.now().isoformat(),
                            })
                            self.logger.info(f"  ✓ {title} @ {company} — score {score}")

                        except Exception:
                            continue

                    params["offset"] += 50
                    time.sleep(1.5)

                except requests.RequestException as e:
                    self.logger.error(f"Request error: {e}")
                    break

        jobs.sort(key=lambda j: j["match_score"], reverse=True)
        self.logger.info(f"Instahyre total: {len(jobs)} jobs")
        return jobs


# ─────────────────────────────────────────────────────────────────────────────
# CUTSHORT
# ─────────────────────────────────────────────────────────────────────────────
class CutshortScraper:
    """
    Cutshort scraper using their public job listing pages.
    Falls back to HTML scraping if API is unavailable.
    """
    SEARCH_URL = "https://cutshort.io/jobs"
    logger = logging.getLogger("Cutshort")

    def _score(self, title: str, desc: str) -> int:
        score = 50
        t = title.lower()
        if any(r in t for r in ["software engineer", "software developer", "sde"]):
            score += 20
        elif "backend" in t:
            score += 15
        if any(x in t for x in ["senior", "lead"]):
            score -= 35
        hits = sum(1 for s in PROFILE["skills"] if s.lower() in desc.lower())
        score += min(hits * 2, 15)
        return max(0, min(100, score))

    def scrape(self) -> list:
        """Scrape Cutshort job listings via their public pages."""
        jobs = []
        seen = set()

        search_queries = [
            "software-engineer",
            "backend-developer",
            "software-developer",
        ]

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml",
        }

        self.logger.info("Scraping Cutshort...")

        for query in search_queries:
            url = f"{self.SEARCH_URL}?q={query}&exp=0-2&salary=20-100&cities=Bangalore,Noida,Gurgaon,Hyderabad,Pune,Remote"
            try:
                resp = requests.get(url, headers=headers, timeout=15)
                if resp.status_code != 200:
                    self.logger.warning(f"HTTP {resp.status_code} for {query}")
                    continue

                soup = BeautifulSoup(resp.text, "html.parser")
                job_cards = soup.select("div.job-card, article.job-listing, div[data-job-id]")

                self.logger.info(f"  {query}: found {len(job_cards)} cards")

                for card in job_cards:
                    try:
                        title_el = card.select_one("h2, h3, .job-title, a.title")
                        if not title_el:
                            continue
                        title = title_el.text.strip()

                        if any(x in title.lower() for x in SEARCH_FILTERS["excluded_roles"]):
                            continue

                        company_el = card.select_one(".company-name, .company, h4")
                        company = company_el.text.strip() if company_el else "Unknown"

                        loc_el = card.select_one(".location, .city")
                        location = loc_el.text.strip() if loc_el else "India"

                        salary_el = card.select_one(".salary, .ctc, .pay")
                        salary_text = salary_el.text.strip() if salary_el else ""

                        link_el = card.select_one("a[href]")
                        job_url = ""
                        if link_el:
                            href = link_el.get("href", "")
                            job_url = f"https://cutshort.io{href}" if href.startswith("/") else href

                        if job_url in seen:
                            continue
                        seen.add(job_url)

                        desc_el = card.select_one(".description, .snippet, p")
                        desc = desc_el.text.strip() if desc_el else ""

                        score = self._score(title, desc)

                        jobs.append({
                            "id": f"cs_{abs(hash(job_url)) % 100000}",
                            "title": title,
                            "company": company,
                            "location": location,
                            "salary_text": salary_text,
                            "salary_lpa": None,
                            "description": desc,
                            "url": job_url,
                            "source": "Cutshort",
                            "posted": "",
                            "match_score": score,
                            "scraped_at": datetime.now().isoformat(),
                        })
                        self.logger.info(f"  ✓ {title} @ {company} — score {score}")

                    except Exception:
                        continue

                time.sleep(2)

            except requests.RequestException as e:
                self.logger.error(f"Request error for {query}: {e}")
                continue

        jobs.sort(key=lambda j: j["match_score"], reverse=True)
        self.logger.info(f"Cutshort total: {len(jobs)} jobs")
        return jobs
