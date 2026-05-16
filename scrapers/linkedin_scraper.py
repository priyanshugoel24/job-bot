"""
LinkedIn Job Scraper
Uses Selenium to log in and scrape SDE-1 / SWE jobs matching Priyanshu's filters.

Usage:
    from scrapers.linkedin_scraper import LinkedInScraper
    scraper = LinkedInScraper()
    jobs = scraper.scrape()
"""

import time
import json
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
    TimeoutException, NoSuchElementException, WebDriverException
)

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import CREDENTIALS, SEARCH_FILTERS, PROFILE

logging.basicConfig(level=logging.INFO, format="%(asctime)s [LinkedIn] %(message)s")
log = logging.getLogger(__name__)


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
        self.driver.execute_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        self.wait = WebDriverWait(self.driver, 15)
        log.info("Chrome driver started.")

    def _quit(self):
        if self.driver:
            self.driver.quit()
            self.driver = None

    # ── Login ─────────────────────────────────────────────────────────────────
    def _dismiss_overlays(self):
        """Dismiss cookie banners and consent dialogs before interacting with forms."""
        overlay_selectors = [
            "button[action-type='ACCEPT']",
            "button[data-tracking-control-name='cookie-policy-accept']",
            "button.artdeco-global-alert__action",
            "button[aria-label='Accept cookies']",
            "button[aria-label='Dismiss']",
        ]
        for sel in overlay_selectors:
            try:
                btn = self.driver.find_element(By.CSS_SELECTOR, sel)
                btn.click()
                time.sleep(0.5)
                log.info(f"Dismissed overlay: {sel}")
                break
            except NoSuchElementException:
                pass

    def _login(self) -> bool:
        if not self.email or not self.password:
            log.error("LinkedIn credentials not set in config.py")
            return False

        log.info("Logging in to LinkedIn...")
        self.driver.get(self.LOGIN_URL)
        time.sleep(3)  # Let the page settle before touching anything

        self._dismiss_overlays()

        # Try multiple selectors for the email field
        email_selectors = [
            (By.ID, "username"),
            (By.CSS_SELECTOR, "input[name='session_key']"),
            (By.CSS_SELECTOR, "input[autocomplete='username']"),
        ]
        email_field = None
        for by, sel in email_selectors:
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
            log.error("Timed out waiting for login form. Screenshot saved: debug_linkedin.png")
            return False

        try:
            email_field.clear()
            email_field.send_keys(self.email)

            # Password field mirrors the same strategy
            pass_selectors = [
                (By.ID, "password"),
                (By.CSS_SELECTOR, "input[name='session_password']"),
                (By.CSS_SELECTOR, "input[type='password']"),
            ]
            pass_field = None
            for by, sel in pass_selectors:
                try:
                    pass_field = self.driver.find_element(by, sel)
                    break
                except NoSuchElementException:
                    continue

            if pass_field is None:
                self.driver.save_screenshot("debug_linkedin.png")
                log.error("Could not find password field. Screenshot saved: debug_linkedin.png")
                return False

            pass_field.clear()
            pass_field.send_keys(self.password)
            pass_field.send_keys(Keys.RETURN)

            time.sleep(3)

            # Check for CAPTCHA or verification
            if "challenge" in self.driver.current_url or "checkpoint" in self.driver.current_url:
                log.warning("LinkedIn is asking for verification. Please complete it manually.")
                input("Complete the LinkedIn verification in the browser, then press Enter here...")

            if "feed" in self.driver.current_url or "mynetwork" in self.driver.current_url:
                log.info("Login successful.")
                return True
            else:
                self.driver.save_screenshot("debug_linkedin.png")
                log.error(f"Login may have failed. URL: {self.driver.current_url} — Screenshot saved: debug_linkedin.png")
                return False

        except Exception as e:
            self.driver.save_screenshot("debug_linkedin.png")
            log.error(f"Login error: {e} — Screenshot saved: debug_linkedin.png")
            return False

    # ── Search & Scrape ───────────────────────────────────────────────────────
    def _build_search_params(self, role: str, location: str) -> dict:
        """Build LinkedIn job search URL parameters."""
        return {
            "keywords": role,
            "location": location,
            "f_E": "1",          # Entry level
            "f_TPR": "r604800",  # Past week
            "sortBy": "DD",      # Date posted
        }

    def _extract_salary(self, text: str) -> Optional[int]:
        """Extract minimum salary in LPA from text."""
        # Match patterns like "20-30 LPA", "₹25,00,000", "20L", "25 lakh"
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
                # If the number looks like annual rupees (e.g. 2500000), convert
                if val > 1000:
                    val = val // 100000  # Convert to LPA
                return val
        return None

    def _score_job(self, title: str, description: str, company: str) -> int:
        """Score a job 0–100 based on how well it matches Priyanshu's profile."""
        score = 50
        title_lower = title.lower()
        desc_lower = description.lower()
        company_lower = company.lower()

        # Role match
        priority_roles = ["software engineer", "software developer", "sde", "swe"]
        secondary_roles = ["backend", "full stack", "fullstack"]
        if any(r in title_lower for r in priority_roles):
            score += 25
        elif any(r in title_lower for r in secondary_roles):
            score += 15

        # Experience level
        if any(x in title_lower for x in ["sde-1", "swe-1", "junior", "entry", "fresher", "associate"]):
            score += 10
        if any(x in title_lower for x in ["senior", "sr", "lead", "staff", "principal"]):
            score -= 40  # Hard filter

        # Company tier
        tier1 = SEARCH_FILTERS["target_companies"]["tier_1_mnc"] + \
                SEARCH_FILTERS["target_companies"]["tier_1_indian"]
        if any(c.lower() in company_lower for c in tier1):
            score += 10

        # Skills match
        skills_in_desc = sum(1 for s in PROFILE["skills"] if s.lower() in desc_lower)
        score += min(skills_in_desc * 2, 15)

        # Positive signals
        if any(kw in desc_lower for kw in SEARCH_FILTERS["positive_keywords"]):
            score += 5

        return max(0, min(100, score))

    def _scrape_job_details(self, job_url: str) -> dict:
        """Open a job page and extract full description."""
        try:
            self.driver.get(job_url)
            time.sleep(2)

            # Expand "See more" if present
            try:
                see_more = self.driver.find_element(
                    By.CSS_SELECTOR, "button[aria-label='Click to see more description']"
                )
                see_more.click()
                time.sleep(0.5)
            except NoSuchElementException:
                pass

            desc = ""
            try:
                desc_el = self.driver.find_element(
                    By.CSS_SELECTOR, ".jobs-description__content, .jobs-box__html-content"
                )
                desc = desc_el.text
            except NoSuchElementException:
                pass

            salary = ""
            try:
                salary_el = self.driver.find_element(
                    By.CSS_SELECTOR, ".jobs-unified-top-card__job-insight--highlight"
                )
                salary = salary_el.text
            except NoSuchElementException:
                pass

            return {"description": desc, "salary_text": salary}

        except Exception as e:
            log.warning(f"Could not fetch job details: {e}")
            return {"description": "", "salary_text": ""}

    def _scrape_search_results(self, role: str, location: str, max_pages: int = 3) -> list:
        """Scrape job listings for a role+location combination."""
        jobs = []
        params = self._build_search_params(role, location)
        query = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"{self.JOBS_URL}?{query}"

        log.info(f"Searching: '{role}' in '{location}'")
        self.driver.get(url)
        time.sleep(3)

        for page in range(max_pages):
            log.info(f"  Page {page + 1}...")

            # Scroll to load all cards
            try:
                job_list = self.wait.until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, ".jobs-search__results-list, .scaffold-layout__list-container")
                    )
                )
                self.driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight", job_list)
                time.sleep(2)
            except TimeoutException:
                log.warning("Job list not found on this page.")
                break

            # Extract cards
            cards = self.driver.find_elements(
                By.CSS_SELECTOR,
                "li.jobs-search-results__list-item, div.job-card-container"
            )
            log.info(f"  Found {len(cards)} cards.")

            for card in cards:
                try:
                    title_el = card.find_element(By.CSS_SELECTOR, "a.job-card-list__title, h3.base-search-card__title")
                    title = title_el.text.strip()
                    job_url = title_el.get_attribute("href").split("?")[0]

                    company = card.find_element(
                        By.CSS_SELECTOR,
                        "a.job-card-container__company-name, h4.base-search-card__subtitle"
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

                    # Skip clearly senior roles
                    title_lower = title.lower()
                    if any(x in title_lower for x in SEARCH_FILTERS["excluded_roles"]):
                        continue

                    # Fetch full description for better scoring
                    details = self._scrape_job_details(job_url)

                    salary_lpa = self._extract_salary(details.get("salary_text", ""))

                    # Filter by minimum CTC if salary is listed
                    if salary_lpa and salary_lpa < SEARCH_FILTERS["min_ctc_lpa"]:
                        log.info(f"  Skipping '{title}' at {company} — CTC {salary_lpa} LPA below threshold.")
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

                except (NoSuchElementException, Exception) as e:
                    continue

            # Next page
            try:
                next_btn = self.driver.find_element(
                    By.CSS_SELECTOR, "button[aria-label='Next']"
                )
                next_btn.click()
                time.sleep(3)
            except NoSuchElementException:
                break

        return jobs

    # ── Public API ────────────────────────────────────────────────────────────
    def scrape(self, max_pages_per_query: int = 3) -> list:
        """
        Main entry point. Logs in, iterates role × location combos, returns jobs list.
        """
        self._start_driver()
        all_jobs = []
        seen_urls = set()

        try:
            if not self._login():
                log.error("Login failed. Aborting.")
                return []

            roles = SEARCH_FILTERS["role_priorities"][:4]   # Top 4 roles
            locations = SEARCH_FILTERS["locations"][:4]      # Top 4 locations

            for role in roles:
                for location in locations:
                    try:
                        jobs = self._scrape_search_results(role, location, max_pages_per_query)
                        for job in jobs:
                            if job["url"] not in seen_urls:
                                seen_urls.add(job["url"])
                                all_jobs.append(job)
                        time.sleep(2)  # Polite delay between searches
                    except Exception as e:
                        log.error(f"Error scraping '{role}' in '{location}': {e}")
                        continue

        finally:
            self._quit()

        # Sort by match score descending
        all_jobs.sort(key=lambda j: j["match_score"], reverse=True)
        log.info(f"Total unique jobs scraped: {len(all_jobs)}")
        return all_jobs
