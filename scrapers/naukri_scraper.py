"""
Naukri.com Job Scraper
Scrapes SDE/SWE fresher jobs from Naukri matching Priyanshu's filters.

Usage:
    from scrapers.naukri_scraper import NaukriScraper
    scraper = NaukriScraper()
    jobs = scraper.scrape()
"""

import time
import re
import logging
from datetime import datetime
from typing import Optional

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import (
    TimeoutException, NoSuchElementException
)

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import CREDENTIALS, SEARCH_FILTERS, PROFILE

logging.basicConfig(level=logging.INFO, format="%(asctime)s [Naukri] %(message)s")
log = logging.getLogger(__name__)


class NaukriScraper:
    LOGIN_URL = "https://www.naukri.com/nlogin/login"
    SEARCH_URL = "https://www.naukri.com/{role}-jobs-in-{location}"
    BASE_SEARCH = "https://www.naukri.com/jobs-in-{location}?k={role}&experience=0&experience=1&salary=2000000"

    def __init__(self, headless: bool = False):
        self.email = CREDENTIALS["naukri"]["email"]
        self.password = CREDENTIALS["naukri"]["password"]
        self.headless = headless
        self.driver = None
        self.wait = None

    def _start_driver(self):
        opts = Options()
        if self.headless:
            opts.add_argument("--headless=new")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--disable-blink-features=AutomationControlled")
        opts.add_experimental_option("excludeSwitches", ["enable-automation"])
        opts.add_experimental_option("useAutomationExtension", False)
        opts.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/124.0.0.0 Safari/537.36")
        from selenium.webdriver.chrome.service import Service
        from webdriver_manager.chrome import ChromeDriverManager
        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=opts)
        self.wait = WebDriverWait(self.driver, 15)
        log.info("Chrome driver started.")

    def _quit(self):
        if self.driver:
            self.driver.quit()
            self.driver = None

    def _login(self) -> bool:
        if not self.email or not self.password:
            log.warning("Naukri credentials not set — proceeding without login (limited results).")
            return True  # Naukri allows some scraping without login

        log.info("Logging in to Naukri...")
        self.driver.get(self.LOGIN_URL)
        time.sleep(2)

        try:
            email_field = self.wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "input[placeholder='Enter your active Email ID / Username']"))
            )
            email_field.clear()
            email_field.send_keys(self.email)

            pass_field = self.driver.find_element(
                By.CSS_SELECTOR, "input[placeholder='Enter your password']"
            )
            pass_field.clear()
            pass_field.send_keys(self.password)
            pass_field.send_keys(Keys.RETURN)
            time.sleep(3)

            # Handle OTP if prompted
            if "otp" in self.driver.current_url.lower():
                log.warning("Naukri OTP required. Please enter it in the browser.")
                input("Enter OTP in browser, then press Enter here...")

            log.info("Naukri login complete.")
            return True

        except TimeoutException:
            log.error("Timed out waiting for Naukri login form.")
            return False

    def _extract_lpa(self, salary_text: str) -> Optional[int]:
        """Parse Naukri salary strings like '20-30 Lacs PA', '25 Lakhs'."""
        if not salary_text:
            return None
        text = salary_text.lower()
        m = re.search(r"(\d+(?:\.\d+)?)\s*[-–to]*\s*(?:\d+)?\s*(?:lac|lakh|lpa|l\.p\.a)", text)
        if m:
            return int(float(m.group(1)))
        return None

    def _score_job(self, title: str, desc: str, company: str) -> int:
        score = 50
        t = title.lower()
        d = desc.lower()
        c = company.lower()

        if any(r in t for r in ["software engineer", "software developer", "sde", "swe"]):
            score += 25
        elif any(r in t for r in ["backend", "full stack", "fullstack"]):
            score += 15

        if any(x in t for x in ["senior", "sr.", "lead", "staff", "principal", "manager"]):
            score -= 40

        tier1 = [x.lower() for x in
                 SEARCH_FILTERS["target_companies"]["tier_1_mnc"] +
                 SEARCH_FILTERS["target_companies"]["tier_1_indian"]]
        if any(tc in c for tc in tier1):
            score += 10

        skills_hit = sum(1 for s in PROFILE["skills"] if s.lower() in d)
        score += min(skills_hit * 2, 15)

        return max(0, min(100, score))

    def _scrape_listing_page(self, role: str, location: str, page: int = 1) -> list:
        """Scrape one page of Naukri search results."""
        role_slug = role.lower().replace(" ", "-")
        loc_slug = location.lower().replace(" ", "-")

        # Naukri URL: salary 20Lac+ = 2000000, experience 0-1 years
        url = (
            f"https://www.naukri.com/{role_slug}-jobs-in-{loc_slug}"
            f"?experience=0&salary=2000000&wfhType=0%2C2"
        )
        if page > 1:
            url += f"&pageNo={page}"

        log.info(f"  Fetching: {role} in {location}, page {page}")
        self.driver.get(url)
        time.sleep(3)

        # Scroll to trigger lazy load
        self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight/2)")
        time.sleep(1.5)
        self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(1.5)

        jobs = []

        # Job cards
        cards = self.driver.find_elements(By.CSS_SELECTOR, "article.jobTuple, div.srp-jobtuple-wrapper")
        log.info(f"  Found {len(cards)} cards.")

        for card in cards:
            try:
                title_el = card.find_element(By.CSS_SELECTOR, "a.title, .row1 a.title")
                title = title_el.text.strip()
                job_url = title_el.get_attribute("href")

                company = card.find_element(
                    By.CSS_SELECTOR, "a.subTitle, .comp-name"
                ).text.strip()

                loc_text = ""
                try:
                    loc_text = card.find_element(By.CSS_SELECTOR, ".locWdth, .location").text.strip()
                except NoSuchElementException:
                    loc_text = location

                salary_text = ""
                salary_lpa = None
                try:
                    salary_text = card.find_element(By.CSS_SELECTOR, ".salary, .sal").text.strip()
                    salary_lpa = self._extract_lpa(salary_text)
                except NoSuchElementException:
                    pass

                exp_text = ""
                try:
                    exp_text = card.find_element(By.CSS_SELECTOR, ".exp, .experience").text.strip()
                except NoSuchElementException:
                    pass

                posted = ""
                try:
                    posted = card.find_element(By.CSS_SELECTOR, ".type-dt, .posted-update").text.strip()
                except NoSuchElementException:
                    pass

                desc_snippet = ""
                try:
                    desc_snippet = card.find_element(By.CSS_SELECTOR, ".job-description, .jd-desc").text.strip()
                except NoSuchElementException:
                    pass

                # Skip senior roles
                if any(x in title.lower() for x in SEARCH_FILTERS["excluded_roles"]):
                    continue

                # Skip if salary is listed but below threshold
                if salary_lpa and salary_lpa < SEARCH_FILTERS["min_ctc_lpa"]:
                    continue

                score = self._score_job(title, desc_snippet, company)

                jobs.append({
                    "id": f"nk_{abs(hash(job_url)) % 100000}",
                    "title": title,
                    "company": company,
                    "location": loc_text,
                    "salary_text": salary_text,
                    "salary_lpa": salary_lpa,
                    "experience_required": exp_text,
                    "description": desc_snippet,
                    "url": job_url,
                    "source": "Naukri",
                    "posted": posted,
                    "match_score": score,
                    "scraped_at": datetime.now().isoformat(),
                })
                log.info(f"  ✓ {title} @ {company} — score {score}")

            except Exception:
                continue

        return jobs

    def scrape(self, max_pages: int = 3) -> list:
        """Main entry point. Returns filtered, scored job list."""
        self._start_driver()
        all_jobs = []
        seen_urls = set()

        try:
            self._login()

            roles = SEARCH_FILTERS["role_priorities"][:4]
            locations = ["bangalore", "noida", "gurgaon", "hyderabad", "pune", "remote"]

            for role in roles:
                for location in locations:
                    for page in range(1, max_pages + 1):
                        try:
                            page_jobs = self._scrape_listing_page(role, location, page)
                            for job in page_jobs:
                                if job["url"] not in seen_urls:
                                    seen_urls.add(job["url"])
                                    all_jobs.append(job)
                            if not page_jobs:
                                break  # No more results
                            time.sleep(2)
                        except Exception as e:
                            log.error(f"Error: {e}")
                            continue

        finally:
            self._quit()

        all_jobs.sort(key=lambda j: j["match_score"], reverse=True)
        log.info(f"Naukri total unique jobs: {len(all_jobs)}")
        return all_jobs
