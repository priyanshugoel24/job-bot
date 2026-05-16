"""
LinkedIn Job Scraper
Uses undetected-chromedriver to bypass LinkedIn bot detection.
Saves cookies after first login so subsequent runs skip the login flow entirely.

Usage:
    from scrapers.linkedin_scraper import LinkedInScraper
    scraper = LinkedInScraper()
    jobs = scraper.scrape()
"""

import os
import sys
import time
import re
import pickle
import random
import logging
from datetime import datetime
from typing import Optional

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import CREDENTIALS, SEARCH_FILTERS, PROFILE

logging.basicConfig(level=logging.INFO, format="%(asctime)s [LinkedIn] %(message)s")
log = logging.getLogger(__name__)

COOKIES_FILE = "output/linkedin_cookies.pkl"


class LinkedInScraper:
    BASE_URL = "https://www.linkedin.com"
    LOGIN_URL = "https://www.linkedin.com/login"
    JOBS_URL = "https://www.linkedin.com/jobs/search/"

    def __init__(self, headless: bool = False):
        self.email = CREDENTIALS["linkedin"]["email"]
        self.password = CREDENTIALS["linkedin"]["password"]
        self.headless = headless
        self.driver = None
        self.wait = None

    # ── Driver ────────────────────────────────────────────────────────────────
    def _start_driver(self):
        opts = uc.ChromeOptions()
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--window-size=1920,1080")
        # undetected_chromedriver handles its own driver download and patching —
        # no webdriver_manager needed here
        self.driver = uc.Chrome(options=opts, headless=self.headless)
        self.wait = WebDriverWait(self.driver, 15)
        log.info("Chrome driver started (undetected mode).")

    def _quit(self):
        if self.driver:
            self.driver.quit()
            self.driver = None

    # ── Human-like typing ─────────────────────────────────────────────────────
    def _type_human(self, element, text: str):
        """Type character-by-character with random delays to mimic a human."""
        for char in text:
            element.send_keys(char)
            time.sleep(random.uniform(0.04, 0.14))

    # ── Cookie persistence ────────────────────────────────────────────────────
    def _save_cookies(self):
        os.makedirs("output", exist_ok=True)
        with open(COOKIES_FILE, "wb") as f:
            pickle.dump(self.driver.get_cookies(), f)
        log.info("LinkedIn session cookies saved — future runs will skip login.")

    def _load_cookies(self) -> bool:
        """Load saved cookies and check if the session is still valid."""
        if not os.path.exists(COOKIES_FILE):
            return False
        log.info("Found saved cookies — trying to resume session...")
        self.driver.get(self.BASE_URL)
        time.sleep(2)
        for cookie in pickle.load(open(COOKIES_FILE, "rb")):
            try:
                self.driver.add_cookie(cookie)
            except Exception:
                pass
        self.driver.refresh()
        time.sleep(3)
        if "feed" in self.driver.current_url or "mynetwork" in self.driver.current_url:
            log.info("Session resumed via saved cookies — no login needed.")
            return True
        log.info("Saved cookies expired — will log in fresh.")
        return False

    # ── Login ─────────────────────────────────────────────────────────────────
    def _dismiss_overlays(self):
        """Dismiss cookie banners / consent dialogs before touching the form."""
        for sel in [
            "button[action-type='ACCEPT']",
            "button[data-tracking-control-name='cookie-policy-accept']",
            "button.artdeco-global-alert__action",
            "button[aria-label='Accept cookies']",
            "button[aria-label='Dismiss']",
        ]:
            try:
                self.driver.find_element(By.CSS_SELECTOR, sel).click()
                time.sleep(0.5)
                log.info(f"Dismissed overlay: {sel}")
                break
            except NoSuchElementException:
                pass

    def _login(self) -> bool:
        if not self.email or not self.password:
            log.error("LinkedIn credentials not set in config.py")
            return False

        # Try cookie-based resume first
        if self._load_cookies():
            return True

        log.info("Logging in to LinkedIn...")
        self.driver.get(self.LOGIN_URL)
        time.sleep(3)
        self._dismiss_overlays()

        # Find email field
        email_field = None
        for by, sel in [
            (By.ID, "username"),
            (By.CSS_SELECTOR, "input[name='session_key']"),
            (By.CSS_SELECTOR, "input[autocomplete='username']"),
        ]:
            try:
                email_field = WebDriverWait(self.driver, 5).until(
                    EC.presence_of_element_located((by, sel))
                )
                log.info(f"Found email field via: {sel}")
                break
            except TimeoutException:
                continue

        if email_field is None:
            self.driver.save_screenshot("debug_linkedin.png")
            log.error("Login form not found. Screenshot: debug_linkedin.png")
            return False

        # Type credentials with human-like delays
        email_field.clear()
        self._type_human(email_field, self.email)
        time.sleep(random.uniform(0.3, 0.8))

        pass_field = None
        for by, sel in [
            (By.ID, "password"),
            (By.CSS_SELECTOR, "input[name='session_password']"),
            (By.CSS_SELECTOR, "input[type='password']"),
        ]:
            try:
                pass_field = self.driver.find_element(by, sel)
                break
            except NoSuchElementException:
                continue

        if pass_field is None:
            self.driver.save_screenshot("debug_linkedin.png")
            log.error("Password field not found. Screenshot: debug_linkedin.png")
            return False

        pass_field.clear()
        self._type_human(pass_field, self.password)
        time.sleep(random.uniform(0.3, 0.6))
        pass_field.send_keys(Keys.RETURN)
        time.sleep(4)

        # Handle CAPTCHA / verification checkpoint
        if "challenge" in self.driver.current_url or "checkpoint" in self.driver.current_url:
            log.warning("LinkedIn verification required. Complete it in the browser.")
            try:
                input("Complete the verification, then press Enter...")
            except EOFError:
                log.warning("Non-interactive shell — waiting 90s for manual verification.")
                time.sleep(90)

        if "feed" in self.driver.current_url or "mynetwork" in self.driver.current_url:
            log.info("Login successful.")
            self._save_cookies()
            return True

        self.driver.save_screenshot("debug_linkedin.png")
        log.error(f"Login failed. URL: {self.driver.current_url} — Screenshot: debug_linkedin.png")
        return False

    # ── Search & Scrape ───────────────────────────────────────────────────────
    def _build_search_url(self, role: str, location: str) -> str:
        params = {
            "keywords": role.replace(" ", "%20"),
            "location": location.replace(" ", "%20"),
            "f_E": "2",          # Entry level
            "f_TPR": "r604800",  # Past week
            "sortBy": "DD",      # Date posted
        }
        query = "&".join(f"{k}={v}" for k, v in params.items())
        return f"{self.JOBS_URL}?{query}"

    def _extract_salary(self, text: str) -> Optional[int]:
        patterns = [
            r"(\d+)\s*[-–to]+\s*\d+\s*(?:lpa|l\.p\.a|lakh|lac)",
            r"(\d+)\s*(?:lpa|l\.p\.a|lakh|lac)",
            r"₹\s*(\d+)[,\d]*\s*[-–]\s*₹",
        ]
        text_lower = text.lower()
        for pat in patterns:
            m = re.search(pat, text_lower)
            if m:
                val = int(m.group(1))
                if val > 1000:
                    val = val // 100000
                return val
        return None

    def _score_job(self, title: str, description: str, company: str) -> int:
        score = 50
        t, d, c = title.lower(), description.lower(), company.lower()

        if any(r in t for r in ["software engineer", "software developer", "sde", "swe"]):
            score += 25
        elif any(r in t for r in ["backend", "full stack", "fullstack"]):
            score += 15

        if any(x in t for x in ["sde-1", "swe-1", "junior", "entry", "fresher", "associate"]):
            score += 10
        if any(x in t for x in ["senior", "sr", "lead", "staff", "principal"]):
            score -= 40

        tier1 = SEARCH_FILTERS["target_companies"]["tier_1_mnc"] + \
                SEARCH_FILTERS["target_companies"]["tier_1_indian"]
        if any(co.lower() in c for co in tier1):
            score += 10

        score += min(sum(1 for s in PROFILE["skills"] if s.lower() in d) * 2, 15)

        if any(kw in d for kw in SEARCH_FILTERS["positive_keywords"]):
            score += 5

        return max(0, min(100, score))

    def _scrape_job_details(self, job_url: str) -> dict:
        try:
            self.driver.get(job_url)
            time.sleep(random.uniform(1.5, 2.5))

            try:
                see_more = self.driver.find_element(
                    By.CSS_SELECTOR, "button[aria-label='Click to see more description']"
                )
                see_more.click()
                time.sleep(0.5)
            except NoSuchElementException:
                pass

            desc = ""
            for sel in [".jobs-description__content", ".jobs-box__html-content", ".job-details-jobs-unified-top-card__job-insight"]:
                try:
                    desc = self.driver.find_element(By.CSS_SELECTOR, sel).text
                    if desc:
                        break
                except NoSuchElementException:
                    pass

            salary = ""
            try:
                salary = self.driver.find_element(
                    By.CSS_SELECTOR, ".jobs-unified-top-card__job-insight--highlight"
                ).text
            except NoSuchElementException:
                pass

            return {"description": desc, "salary_text": salary}
        except Exception as e:
            log.warning(f"Could not fetch job details: {e}")
            return {"description": "", "salary_text": ""}

    def _scrape_search_results(self, role: str, location: str, max_pages: int = 3) -> list:
        jobs = []
        url = self._build_search_url(role, location)
        log.info(f"Searching: '{role}' in '{location}'")
        self.driver.get(url)
        time.sleep(random.uniform(3, 4))

        for page in range(max_pages):
            log.info(f"  Page {page + 1}...")

            try:
                job_list = self.wait.until(EC.presence_of_element_located((
                    By.CSS_SELECTOR,
                    ".jobs-search__results-list, .scaffold-layout__list-container"
                )))
                # Scroll gradually — sudden jumps to bottom look bot-like
                for _ in range(3):
                    self.driver.execute_script(
                        "arguments[0].scrollTop += arguments[0].scrollHeight / 3", job_list
                    )
                    time.sleep(random.uniform(0.6, 1.2))
            except TimeoutException:
                log.warning("Job list container not found.")
                break

            cards = self.driver.find_elements(
                By.CSS_SELECTOR,
                "li.jobs-search-results__list-item, div.job-card-container"
            )
            log.info(f"  Found {len(cards)} cards.")

            for card in cards:
                try:
                    title_el = card.find_element(
                        By.CSS_SELECTOR,
                        "a.job-card-list__title, h3.base-search-card__title, a[data-control-name='job_card_title']"
                    )
                    title = title_el.text.strip()
                    job_url = title_el.get_attribute("href").split("?")[0]

                    company = card.find_element(
                        By.CSS_SELECTOR,
                        "a.job-card-container__company-name, h4.base-search-card__subtitle, "
                        ".job-card-container__primary-description"
                    ).text.strip()

                    loc = card.find_element(
                        By.CSS_SELECTOR,
                        "li.job-card-container__metadata-item, span.job-search-card__location"
                    ).text.strip()

                    posted = ""
                    try:
                        posted = card.find_element(
                            By.CSS_SELECTOR, "time, .job-card-container__listed-status"
                        ).text.strip()
                    except NoSuchElementException:
                        pass

                    if any(x in title.lower() for x in SEARCH_FILTERS["excluded_roles"]):
                        continue

                    details = self._scrape_job_details(job_url)
                    salary_lpa = self._extract_salary(details.get("salary_text", ""))

                    if salary_lpa and salary_lpa < SEARCH_FILTERS["min_ctc_lpa"]:
                        log.info(f"  Skipping '{title}' — CTC {salary_lpa} LPA below threshold.")
                        continue

                    score = self._score_job(title, details.get("description", ""), company)
                    jobs.append({
                        "id": f"li_{abs(hash(job_url)) % 100000}",
                        "title": title,
                        "company": company,
                        "location": loc,
                        "salary_text": details.get("salary_text", ""),
                        "salary_lpa": salary_lpa,
                        "description": details.get("description", ""),
                        "url": job_url,
                        "source": "LinkedIn",
                        "posted": posted,
                        "match_score": score,
                        "scraped_at": datetime.now().isoformat(),
                    })
                    log.info(f"  ✓ {title} @ {company} — score {score}")

                except Exception:
                    continue

            # Next page
            try:
                self.driver.find_element(By.CSS_SELECTOR, "button[aria-label='Next']").click()
                time.sleep(random.uniform(2.5, 4))
            except NoSuchElementException:
                break

        return jobs

    # ── Public API ────────────────────────────────────────────────────────────
    def scrape(self, max_pages_per_query: int = 3) -> list:
        self._start_driver()
        all_jobs = []
        seen_urls = set()

        try:
            if not self._login():
                log.error("Login failed. Aborting LinkedIn scraper.")
                return []

            roles = SEARCH_FILTERS["role_priorities"][:4]
            locations = SEARCH_FILTERS["locations"][:4]

            for role in roles:
                for location in locations:
                    try:
                        jobs = self._scrape_search_results(role, location, max_pages_per_query)
                        for job in jobs:
                            if job["url"] not in seen_urls:
                                seen_urls.add(job["url"])
                                all_jobs.append(job)
                        time.sleep(random.uniform(2, 3))
                    except Exception as e:
                        log.error(f"Error scraping '{role}' in '{location}': {e}")
                        continue
        finally:
            self._quit()

        all_jobs.sort(key=lambda j: j["match_score"], reverse=True)
        log.info(f"LinkedIn total unique jobs: {len(all_jobs)}")
        return all_jobs
