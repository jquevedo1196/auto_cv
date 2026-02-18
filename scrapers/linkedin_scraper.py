"""
Job Hunter Agent - LinkedIn Scraper
Uses Playwright to scrape LinkedIn Jobs across target countries.
Supports Easy Apply detection.

Session persistence: saves LinkedIn cookies to linkedin_session.json after first
login so subsequent runs skip login entirely and avoid CAPTCHA/2FA challenges.
"""

import asyncio
import json
import logging
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional
from urllib.parse import urlencode

from playwright.async_api import async_playwright, Page, Browser, BrowserContext

from scrapers.base_scraper import BaseScraper, JobPosting

logger = logging.getLogger(__name__)

SESSION_FILE = Path("linkedin_session.json")


class LinkedInScraper(BaseScraper):
    """Scrapes LinkedIn Jobs using Playwright (headless browser)."""

    BASE_URL = "https://www.linkedin.com"
    JOBS_URL = "https://www.linkedin.com/jobs/search"

    def __init__(self, config, email: str, password: str):
        super().__init__(config)
        self.email = email
        self.password = password
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._logged_in = False

    async def _launch(self):
        """Launch browser with anti-detection flags."""
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--start-maximized",
            ]
        )
        self._context = await self._browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1440, "height": 900},
            locale="en-US",
            timezone_id="America/Toronto",
            java_script_enabled=True,
            bypass_csp=True,
        )
        await self._context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        self._page = await self._context.new_page()
        self._page.set_default_timeout(60_000)

    async def _login(self):
        """
        Log in to LinkedIn using saved cookies if available,
        otherwise do a fresh login and save the session for next time.
        """
        if self._logged_in:
            return

        # ── Try restoring saved session first ────────────────
        if SESSION_FILE.exists():
            logger.info("Restoring LinkedIn session from saved cookies...")
            try:
                cookies = json.loads(SESSION_FILE.read_text())
                await self._context.add_cookies(cookies)

                await self._page.goto(
                    f"{self.BASE_URL}/feed",
                    wait_until="domcontentloaded",
                    timeout=60_000,
                )
                await asyncio.sleep(2)

                # Check if session is still valid
                if "feed" in self._page.url or "mynetwork" in self._page.url:
                    self._logged_in = True
                    logger.info("LinkedIn session restored successfully ✅")
                    return
                else:
                    logger.warning("Saved session expired — doing fresh login")
                    SESSION_FILE.unlink(missing_ok=True)
            except Exception as e:
                logger.warning(f"Session restore failed: {e} — doing fresh login")
                SESSION_FILE.unlink(missing_ok=True)

        # ── Fresh login ───────────────────────────────────────
        logger.info("Logging into LinkedIn (fresh)...")
        await self._page.goto(
            f"{self.BASE_URL}/login",
            wait_until="domcontentloaded",
            timeout=60_000,
        )
        await asyncio.sleep(2)

        await self._page.fill("#username", self.email)
        await asyncio.sleep(0.5)
        await self._page.fill("#password", self.password)
        await asyncio.sleep(0.5)
        await self._page.click("[data-litms-control-urn='login-submit']")

        try:
            await self._page.wait_for_url(
                re.compile(r"linkedin\.com/(feed|mynetwork|jobs)"),
                timeout=20_000,
            )
            self._logged_in = True
            logger.info("LinkedIn login successful!")

            # ── Save cookies for future runs ──────────────────
            cookies = await self._context.cookies()
            SESSION_FILE.write_text(json.dumps(cookies, indent=2))
            logger.info(f"Session saved to {SESSION_FILE} — next run will skip login")

        except Exception:
            current_url = self._page.url
            if "checkpoint" in current_url or "challenge" in current_url:
                logger.error(
                    "\n"
                    "══════════════════════════════════════════════════\n"
                    "  LinkedIn CAPTCHA/2FA detected.\n"
                    "  Fix: run this once to save your session manually:\n"
                    "    poetry run python save_linkedin_session.py\n"
                    "══════════════════════════════════════════════════"
                )
            else:
                logger.warning(f"Login redirect not detected — current URL: {current_url}")

    async def search(self, keyword: str, country: dict) -> List[JobPosting]:
        """Search LinkedIn jobs for a keyword in a given country."""
        if not self._browser:
            await self._launch()
        await self._login()

        if not self._logged_in:
            logger.error("Skipping LinkedIn search — not logged in")
            return []

        jobs = []
        geo_id = country.get("linkedin_geo", "")

        # f_LF=f_AL is LinkedIn's Easy Apply filter.
        # Every job returned by this search is guaranteed to have Easy Apply,
        # so we mark easy_apply=True directly on the card instead of relying on
        # fragile post-navigation DOM detection.
        self._search_easy_apply_only = True
        params = {
            "keywords":  keyword,
            "location":  country["name"],
            "f_TPR":     f"r{self.config.max_days_old * 86400}",
            "f_JT":      "F",
            "f_E":       "4,5",
            "f_LF":      "f_AL",   # Easy Apply filter
            "geoId":     geo_id,
            "start":     0,
        }
        search_url = f"{self.JOBS_URL}?{urlencode(params)}"
        logger.info(f"Searching LinkedIn: {keyword} in {country['name']}")

        try:
            await self._page.goto(
                search_url,
                wait_until="domcontentloaded",
                timeout=60_000,
            )
            await asyncio.sleep(3)

            # Scroll to trigger lazy-loading
            for _ in range(3):
                await self._page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await asyncio.sleep(1.5)

        except Exception as e:
            logger.error(f"LinkedIn search page load failed: {e}")
            return []

        # LinkedIn uses different container selectors depending on login state
        # Try multiple known selectors in order
        card_selectors = [
            ".jobs-search__results-list li",           # classic logged-out
            ".scaffold-layout__list li",               # logged-in 2024+
            "[data-occludable-job-id]",                # logged-in card wrapper
            ".job-card-container",                     # fallback
            "li.ember-view",                           # older structure
        ]
        job_cards = []
        for sel in card_selectors:
            job_cards = await self._page.query_selector_all(sel)
            if job_cards:
                logger.debug(f"LinkedIn: found {len(job_cards)} cards with selector '{sel}'")
                break

        if not job_cards:
            # Save screenshot to help diagnose what LinkedIn is showing
            await self._page.screenshot(path="debug_linkedin.png")
            logger.warning(
                "LinkedIn: 0 cards found with any selector. "
                "Screenshot saved to debug_linkedin.png — check if login/CAPTCHA is blocking."
            )

        for card in job_cards[:20]:
            try:
                job = await self._extract_card(card, country)
                if job and not self.is_blacklisted(job):
                    jobs.append(job)
            except Exception as e:
                logger.debug(f"Error extracting job card: {e}")

        logger.info(f"Found {len(jobs)} jobs for '{keyword}' in {country['name']}")
        return jobs

    async def _extract_card(self, card, country: dict) -> Optional[JobPosting]:
        """Extract job data from a LinkedIn job card element.
        Handles both the logged-out (public) and logged-in card structures.
        """
        try:
            # ── Title ──────────────────────────────────────────────
            title = ""
            for sel in [
                ".job-card-list__title",            # logged-in 2024+
                ".job-card-container__link span",   # logged-in variant
                ".base-search-card__title",         # logged-out
                "h3",                               # generic fallback
            ]:
                el = await card.query_selector(sel)
                if el:
                    title = (await el.inner_text()).strip()
                    if title:
                        break

            # ── Company ────────────────────────────────────────────
            company = ""
            for sel in [
                ".job-card-container__primary-description",
                ".job-card-list__company-name",
                ".base-search-card__subtitle",
                ".job-card-container__company-name",
                "[data-tracking-control-name='public_jobs_jserp-result_job-search-card-subtitle']",
                "h4.base-search-card__subtitle",
                ".artdeco-entity-lockup__subtitle",
            ]:
                el = await card.query_selector(sel)
                if el:
                    company = (await el.inner_text()).strip()
                    if company:
                        break

            # Fallback: read company from aria-label of the card link
            if not company:
                try:
                    link = await card.query_selector("a[aria-label]")
                    if link:
                        aria = await link.get_attribute("aria-label")
                        if aria and " at " in aria:
                            company = aria.split(" at ")[-1].strip()
                except Exception:
                    pass

            # ── Location ───────────────────────────────────────────
            location = ""
            for sel in [
                ".job-card-container__metadata-item",
                ".job-search-card__location",
                ".job-card-list__metadata-item",
            ]:
                el = await card.query_selector(sel)
                if el:
                    location = (await el.inner_text()).strip()
                    if location:
                        break

            # ── URL ────────────────────────────────────────────────
            url = ""
            for sel in [
                "a.job-card-list__title",
                "a.job-card-container__link",
                "a.base-card__full-link",
                "a[href*='/jobs/view/']",
                "a",
            ]:
                el = await card.query_selector(sel)
                if el:
                    href = await el.get_attribute("href")
                    if href and "/jobs/" in href:
                        url = href.split("?")[0]
                        # Ensure absolute URL
                        if url.startswith("/"):
                            url = f"https://www.linkedin.com{url}"
                        break

            # ── Date ───────────────────────────────────────────────
            posted_date = None
            date_el = await card.query_selector("time")
            if date_el:
                dt_attr = await date_el.get_attribute("datetime")
                if dt_attr:
                    try:
                        posted_date = datetime.fromisoformat(dt_attr[:10])
                    except Exception:
                        pass

            if not title or not url:
                return None

            return JobPosting(
                title=title,
                company=company,
                location=location,
                country=country["name"],
                url=url,
                apply_url=url,
                source="linkedin",
                posted_date=posted_date,
                # Trust the f_LF=f_AL search filter: all results from that search
                # have Easy Apply. Headless DOM detection is unreliable on LinkedIn.
                easy_apply=getattr(self, "_search_easy_apply_only", False),
            )
        except Exception as e:
            logger.debug(f"Card extraction error: {e}")
            return None

    async def get_job_details(self, job: JobPosting) -> JobPosting:
        """Visit the job page and extract full description + Easy Apply status."""
        try:
            await self._page.goto(
                job.url,
                wait_until="domcontentloaded",
                timeout=60_000,
            )
            await asyncio.sleep(2)

            # ── Description ───────────────────────────────────
            desc_selectors = [
                ".jobs-description__content",
                ".jobs-description-content__text",
                "#job-details",
                ".job-view-layout .jobs-box__html-content",
                "[data-job-id] .jobs-description",
                ".jobs-unified-description__content",
            ]
            for sel in desc_selectors:
                try:
                    el = await self._page.query_selector(sel)
                    if el:
                        text = (await el.inner_text()).strip()
                        if len(text) > 100:
                            job.description = text[:4000]
                            break
                except Exception:
                    continue

            # ── Company name (if missing from card) ───────────
            if not job.company:
                company_selectors = [
                    ".jobs-unified-top-card__company-name a",
                    ".jobs-unified-top-card__company-name",
                    ".job-details-jobs-unified-top-card__company-name a",
                    ".topcard__org-name-link",
                ]
                for sel in company_selectors:
                    try:
                        el = await self._page.query_selector(sel)
                        if el:
                            job.company = (await el.inner_text()).strip()
                            if job.company:
                                break
                    except Exception:
                        continue

            # ── Easy Apply detection ──────────────────────────
            # Primary source: the f_LF=f_AL search filter already guarantees Easy Apply
            # for all LinkedIn results, so job.easy_apply is already True from _extract_card.
            # We do a quick DOM check as a secondary confirmation, but we never override
            # a True value — headless rendering of the Apply button is unreliable.
            try:
                detected = await self._page.evaluate("""
                    () => {
                        const hasAria = Array.from(
                            document.querySelectorAll('[aria-label]')
                        ).some(el =>
                            (el.getAttribute('aria-label') || '').includes('Easy Apply')
                        );
                        const hasText = Array.from(
                            document.querySelectorAll('button, span, a, div, li')
                        ).some(el => {
                            const t = el.textContent.trim();
                            return t === 'Easy Apply' || t === 'Easy apply';
                        });
                        return hasAria || hasText;
                    }
                """)
                # Additive: True from filter wins; detection can promote False → True.
                job.easy_apply = job.easy_apply or detected
                logger.info(f"Easy Apply detection for '{job.title[:40]}': {job.easy_apply}")
            except Exception as e:
                logger.debug(f"Easy Apply eval error: {e}")
                # Do not reset — preserve value set by the search filter

            # ── Salary ────────────────────────────────────────
            salary_selectors = [
                ".jobs-unified-top-card__job-insight span",
                ".compensation__salary",
                "[data-test-id='salary-info']",
            ]
            for sel in salary_selectors:
                try:
                    el = await self._page.query_selector(sel)
                    if el:
                        salary_text = (await el.inner_text()).strip()
                        if any(c in salary_text for c in ["$", "€", "£", "kr"]):
                            job = self._parse_salary(job, salary_text)
                            break
                except Exception:
                    continue

        except Exception as e:
            logger.debug(f"Error getting job details for {job.url}: {e}")

        return job

    def _parse_salary(self, job: JobPosting, text: str) -> JobPosting:
        """Attempt to parse salary range from text."""
        numbers = re.findall(r"[\d,]+", text.replace(",", ""))
        if len(numbers) >= 2:
            try:
                job.salary_min = int(numbers[0])
                job.salary_max = int(numbers[1])
            except ValueError:
                pass
        if "CAD" in text or "CA$" in text:
            job.salary_currency = "CAD"
        elif "€" in text or "EUR" in text:
            job.salary_currency = "EUR"
        elif "£" in text or "GBP" in text:
            job.salary_currency = "GBP"
        elif "NZD" in text or "NZ$" in text:
            job.salary_currency = "NZD"
        return job

    async def close(self):
        if self._browser:
            await self._browser.close()