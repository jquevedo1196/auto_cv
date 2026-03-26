"""
Job Hunter Agent - Country-Specific Scrapers
Scrapers for Seek (NZ), StepStone (DE), Pracuj (PL), Arbetsformedlingen (SE).

Seek uses its internal GraphQL/JSON API — much more reliable than HTML scraping.
The others use Playwright with domcontentloaded to avoid networkidle timeouts.
"""

import asyncio
import json
import logging
import re
from typing import Optional
from urllib.parse import quote_plus

import aiohttp
from playwright.async_api import async_playwright, Browser, Page

from scrapers.base_scraper import BaseScraper, JobPosting

logger = logging.getLogger(__name__)


class CountryScraper(BaseScraper):
    """Scrapers for NZ, DE, PL, SE job portals."""

    def __init__(self, config):
        super().__init__(config)
        self._browser: Optional[Browser] = None
        self._page: Optional[Page] = None
        self._http_session: Optional[aiohttp.ClientSession] = None

    # ── Browser lifecycle ────────────────────────────────────

    async def _launch(self):
        playwright = await async_playwright().start()
        self._browser = await playwright.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
            ],
        )
        context = await self._browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1440, "height": 900},
            locale="en-US",
        )
        await context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        self._page = await context.new_page()
        self._page.set_default_timeout(60_000)

    async def _get_http_session(self) -> aiohttp.ClientSession:
        if self._http_session is None or self._http_session.closed:
            self._http_session = aiohttp.ClientSession(
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0.0.0 Safari/537.36"
                    ),
                    "Accept": "application/json, text/plain, */*",
                    "Accept-Language": "en-US,en;q=0.9",
                },
                timeout=aiohttp.ClientTimeout(total=20),
                connector=aiohttp.TCPConnector(ssl=False),  # bypass SSL cert issues on macOS
            )
        return self._http_session

    async def close(self):
        if self._browser:
            await self._browser.close()
        if self._http_session and not self._http_session.closed:
            await self._http_session.close()

    # ══════════════════════════════════════════════════════════
    # SEEK.CO.NZ — New Zealand  ★ Priority portal
    # Uses Seek's internal JSON API for reliable, structured data
    # ══════════════════════════════════════════════════════════
    async def scrape_seek_nz(self, keyword: str) -> list[JobPosting]:
        """
        Scrape Seek.co.nz using Playwright HTML scraping.
        Returns rich job data including salary, work type, and listing date.
        """
        logger.info(f"Scraping Seek NZ: '{keyword}'")
        return await self._scrape_seek_html(keyword)

    def _parse_seek_item(self, item: dict) -> Optional[JobPosting]:
        """Parse a single job item from Seek's API response."""
        try:
            title   = item.get("title", "")
            company = item.get("advertiser", {}).get("description", "")
            loc     = item.get("location", "")
            area    = item.get("area", "")
            location = f"{area}, {loc}".strip(", ") if area else loc

            job_id  = item.get("id", "")
            url     = f"https://www.seek.co.nz/job/{job_id}" if job_id else ""

            if not title or not url:
                return None

            # Work type: Full time, Part time, Contract/Temp, Casual, etc.
            work_type = item.get("workType", "")
            job_type  = "contract" if "contract" in work_type.lower() else "full-time"

            # Salary
            salary_text = item.get("salary", "")
            salary_min, salary_max = self._parse_seek_salary(salary_text)

            # Listing date
            listed_at = item.get("listingDate", "")
            posted_date = None
            if listed_at:
                try:
                    from datetime import datetime
                    posted_date = datetime.fromisoformat(listed_at[:10])
                except Exception:
                    pass

            # Description teaser (full description needs a detail request)
            teaser = item.get("teaser", "")
            bullet_points = item.get("bulletPoints", [])
            description = teaser
            if bullet_points:
                description += "\n• " + "\n• ".join(bullet_points)

            return JobPosting(
                title=title,
                company=company,
                location=location,
                country="New Zealand",
                url=url,
                apply_url=url,
                source="seek.co.nz",
                description=description,
                job_type=job_type,
                salary_min=salary_min,
                salary_max=salary_max,
                salary_currency="NZD",
                posted_date=posted_date,
            )
        except Exception as e:
            logger.debug(f"Seek item parse error: {e}")
            return None

    @staticmethod
    def _parse_seek_salary(text: str) -> tuple[Optional[int], Optional[int]]:
        """Parse salary range from Seek salary string like '$90k - $120k' or '$80,000'."""
        if not text:
            return None, None
        clean = text.replace(",", "").replace("$", "")
        numbers = re.findall(r"(\d+(?:\.\d+)?)([kK]?)", clean)
        parsed = []
        for num_str, suffix in numbers:
            val = float(num_str)
            if suffix.lower() == "k" or val < 1000:
                val *= 1000
            if val > 20_000:  # sanity check — avoid parsing "40 hours" as salary
                parsed.append(int(val))
        if len(parsed) >= 2:
            return sorted(parsed[:2])
        elif len(parsed) == 1:
            return parsed[0], parsed[0]
        return None, None

    async def _scrape_seek_html(self, keyword: str) -> list[JobPosting]:
        """Fallback: scrape Seek HTML if API is unavailable."""
        if not self._browser:
            await self._launch()

        jobs = []
        # Seek expects hyphens in the URL slug, e.g. "devops-engineer-jobs"
        keyword_slug = keyword.lower().replace(" ", "-")
        url = f"https://www.seek.co.nz/{keyword_slug}-jobs?sortmode=ListedDate"
        logger.info(f"Seek NZ HTML fallback: {url}")

        try:
            await self._page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            await asyncio.sleep(4)  # Seek is a React SPA — needs extra time to render

            # Multiple selector attempts for Seek's React app
            card_selectors = [
                "article[data-card-type='JobCard']",
                "[data-testid='job-card']",
                "article[data-job-id]",
                "[data-automation='normalJob']",
                "[data-automation='premiumJob']",
            ]
            cards = []
            for sel in card_selectors:
                cards = await self._page.query_selector_all(sel)
                if cards:
                    logger.debug(f"Seek HTML: matched {len(cards)} cards with '{sel}'")
                    break

            for card in cards[:20]:
                try:
                    title_el    = await card.query_selector("[data-automation='jobTitle'], h3, h2")
                    company_el  = await card.query_selector("[data-automation='jobCompany'], [data-automation='advertiser']")
                    location_el = await card.query_selector("[data-automation='jobLocation'], [data-automation='jobCardLocation']")
                    salary_el   = await card.query_selector("[data-automation='jobSalary'], [data-automation='jobListingPrice']")
                    date_el     = await card.query_selector("[data-automation='jobListingDate'], time")
                    worktype_el = await card.query_selector("[data-automation='jobWorkType'], [data-automation='jobListingWorkType']")
                    link_el     = await card.query_selector("a[data-automation='jobTitle'], a")

                    title       = (await title_el.inner_text()).strip()    if title_el    else ""
                    company     = (await company_el.inner_text()).strip()  if company_el  else ""
                    location    = (await location_el.inner_text()).strip() if location_el else ""
                    salary_text = (await salary_el.inner_text()).strip()   if salary_el   else ""
                    date_text   = (await date_el.inner_text()).strip()     if date_el     else ""
                    work_type   = (await worktype_el.inner_text()).strip() if worktype_el else ""
                    href        = await link_el.get_attribute("href")      if link_el     else ""
                    job_url     = f"https://www.seek.co.nz{href}" if href and href.startswith("/") else href

                    if not title or not job_url:
                        continue

                    salary_min, salary_max = self._parse_seek_salary(salary_text)
                    job_type = "contract" if "contract" in work_type.lower() else "full-time"

                    job = JobPosting(
                        title=title,
                        company=company,
                        location=location,
                        country="New Zealand",
                        url=job_url,
                        apply_url=job_url,
                        source="seek.co.nz",
                        job_type=job_type,
                        salary_min=salary_min,
                        salary_max=salary_max,
                        salary_currency="NZD",
                    )
                    if not self.is_blacklisted(job):
                        jobs.append(job)
                except Exception as e:
                    logger.debug(f"Seek HTML card error: {e}")

            if not jobs:
                await self._page.screenshot(path="debug_seek.png")
                logger.warning("Seek: 0 jobs found. Screenshot saved to debug_seek.png")

        except Exception as e:
            logger.error(f"Seek HTML scrape error: {e}")

        logger.info(f"Seek NZ HTML: found {len(jobs)} jobs for '{keyword}'")
        return jobs

    async def seek_get_job_details(self, job: JobPosting) -> JobPosting:
        """
        Fetch full job description from Seek's job detail API.
        Called from get_job_details() for Seek jobs.
        """
        # Extract job ID from URL: https://www.seek.co.nz/job/12345678
        m = re.search(r"/job/(\d+)", job.url)
        if not m:
            return job

        job_id = m.group(1)
        session = await self._get_http_session()

        try:
            detail_url = f"https://www.seek.co.nz/api/chalice-search/v4/job/{job_id}"
            async with session.get(detail_url) as resp:
                if resp.status == 200:
                    data = await resp.json(content_type=None)
                    # Full description in HTML — strip tags for plain text
                    desc_html = data.get("content", "") or data.get("description", "")
                    if desc_html:
                        # Simple HTML tag stripper
                        job.description = re.sub(r"<[^>]+>", " ", desc_html).strip()[:4000]
                    # Also grab salary if not already set
                    if not job.salary_min:
                        salary_text = data.get("salary", "")
                        job.salary_min, job.salary_max = self._parse_seek_salary(salary_text)
        except Exception as e:
            logger.debug(f"Seek detail API error: {e}")

        return job

    # ══════════════════════════════════════════════════════════
    # STEPSTONE.DE — Germany
    # ══════════════════════════════════════════════════════════
    async def scrape_stepstone_de(self, keyword: str) -> list[JobPosting]:
        """Scrape StepStone.de for Germany jobs using Playwright."""
        if not self._browser:
            await self._launch()

        jobs = []
        url = f"https://www.stepstone.de/jobs/{quote_plus(keyword)}"
        logger.info(f"Scraping StepStone DE: '{keyword}'")

        try:
            await self._page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            await asyncio.sleep(2)

            # Accept cookies
            for sel in ["[data-testid='ccmgt_explicit_accept']", "#onetrust-accept-btn-handler"]:
                try:
                    btn = await self._page.query_selector(sel)
                    if btn:
                        await btn.click()
                        await asyncio.sleep(1)
                        break
                except Exception:
                    pass

            cards = await self._page.query_selector_all("article[data-job-id], [data-at='job-item']")

            for card in cards[:15]:
                try:
                    title_el    = await card.query_selector("h2, [data-at='job-item-title']")
                    company_el  = await card.query_selector("[data-at='job-item-company-name']")
                    location_el = await card.query_selector("[data-at='job-item-location']")
                    link_el     = await card.query_selector("a")

                    title    = (await title_el.inner_text()).strip()    if title_el    else ""
                    company  = (await company_el.inner_text()).strip()  if company_el  else ""
                    location = (await location_el.inner_text()).strip() if location_el else ""
                    href     = await link_el.get_attribute("href")      if link_el     else ""
                    job_url  = f"https://www.stepstone.de{href}" if href.startswith("/") else href

                    if title and job_url:
                        job = JobPosting(
                            title=title, company=company, location=location,
                            country="Germany", url=job_url, apply_url=job_url,
                            source="stepstone.de",
                        )
                        if not self.is_blacklisted(job):
                            jobs.append(job)
                except Exception as e:
                    logger.debug(f"StepStone card error: {e}")

        except Exception as e:
            logger.error(f"StepStone scrape error: {e}")

        logger.info(f"StepStone DE: found {len(jobs)} jobs for '{keyword}'")
        return jobs

    # ══════════════════════════════════════════════════════════
    # PRACUJ.PL — Poland
    # ══════════════════════════════════════════════════════════
    async def scrape_pracuj_pl(self, keyword: str) -> list[JobPosting]:
        """Scrape Pracuj.pl for Poland jobs using Playwright."""
        if not self._browser:
            await self._launch()

        jobs = []
        url = f"https://www.pracuj.pl/praca/{quote_plus(keyword)};kw/it"
        logger.info(f"Scraping Pracuj.pl PL: '{keyword}'")

        try:
            await self._page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            await asyncio.sleep(2)

            # Accept cookies
            try:
                btn = await self._page.query_selector("button[data-test='button-acceptAllInCookieBar']")
                if btn:
                    await btn.click()
                    await asyncio.sleep(1)
            except Exception:
                pass

            cards = await self._page.query_selector_all("[data-test='default-offer']")

            for card in cards[:15]:
                try:
                    title_el    = await card.query_selector("h2, [data-test='offer-title']")
                    company_el  = await card.query_selector("[data-test='text-company-name']")
                    location_el = await card.query_selector("[data-test='text-region'], [data-test='offer-location']")
                    salary_el   = await card.query_selector("[data-test='offer-salary']")
                    link_el     = await card.query_selector("a")

                    title    = (await title_el.inner_text()).strip()    if title_el    else ""
                    company  = (await company_el.inner_text()).strip()  if company_el  else ""
                    location = (await location_el.inner_text()).strip() if location_el else ""
                    salary_text = (await salary_el.inner_text()).strip() if salary_el  else ""
                    href     = await link_el.get_attribute("href")      if link_el     else ""

                    if title and href:
                        job = JobPosting(
                            title=title, company=company, location=location,
                            country="Poland", url=href, apply_url=href,
                            source="pracuj.pl",
                            salary_currency="PLN",
                        )
                        if salary_text:
                            nums = re.findall(r"[\d\s]+", salary_text.replace(" ", ""))
                            parsed = [int(n.replace(" ", "")) for n in nums if n.strip()]
                            if len(parsed) >= 2:
                                job.salary_min, job.salary_max = sorted(parsed[:2])
                        if not self.is_blacklisted(job):
                            jobs.append(job)
                except Exception as e:
                    logger.debug(f"Pracuj card error: {e}")

        except Exception as e:
            logger.error(f"Pracuj scrape error: {e}")

        logger.info(f"Pracuj PL: found {len(jobs)} jobs for '{keyword}'")
        return jobs

    # ══════════════════════════════════════════════════════════
    # ARBETSFÖRMEDLINGEN — Sweden (public REST API)
    # ══════════════════════════════════════════════════════════
    async def scrape_arbetsformedlingen_se(self, keyword: str) -> list[JobPosting]:
        """Query Arbetsformedlingen's public JobTech API for Sweden jobs."""
        session = await self._get_http_session()
        jobs = []
        api_url = (
            f"https://jobsearch.api.jobtechdev.se/search"
            f"?q={quote_plus(keyword)}&limit=20&offset=0"
        )
        logger.info(f"Querying Arbetsformedlingen API: '{keyword}'")

        try:
            async with session.get(api_url, headers={"accept": "application/json"}) as resp:
                if resp.status != 200:
                    logger.warning(f"Arbetsformedlingen API: HTTP {resp.status}")
                    return []

                data = await resp.json()
                for hit in data.get("hits", []):
                    title   = hit.get("headline", "")
                    company = hit.get("employer", {}).get("name", "")
                    loc     = hit.get("workplace_address", {}).get("city", "") or "Sweden"
                    job_id  = hit.get("id", "")
                    job_url = f"https://arbetsformedlingen.se/platsbanken/annonser/{job_id}"
                    desc    = hit.get("description", {}).get("text", "")

                    # Salary info (sometimes present)
                    salary_desc = hit.get("salary_description", "")

                    job = JobPosting(
                        title=title, company=company, location=loc,
                        country="Sweden", url=job_url, apply_url=job_url,
                        source="arbetsformedlingen.se",
                        description=desc[:2000],
                        salary_currency="SEK",
                    )
                    if not self.is_blacklisted(job):
                        jobs.append(job)

        except Exception as e:
            logger.error(f"Arbetsformedlingen error: {e}")

        logger.info(f"Arbetsformedlingen SE: found {len(jobs)} jobs for '{keyword}'")
        return jobs

    # ══════════════════════════════════════════════════════════
    # OCC MUNDIAL — Mexico
    # ══════════════════════════════════════════════════════════
    async def scrape_occ_mx(self, keyword: str) -> list[JobPosting]:
        """Scrape OCC Mundial for Mexico jobs using Playwright."""
        if not self._browser:
            await self._launch()

        jobs = []
        keyword_slug = quote_plus(keyword)
        url = f"https://www.occ.com.mx/empleos/de-{keyword_slug}"
        logger.info(f"Scraping OCC Mundial MX: '{keyword}'")

        try:
            await self._page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            await asyncio.sleep(3)

            # Accept cookies if prompted
            try:
                btn = await self._page.query_selector("[id*='cookie'] button, [class*='cookie'] button")
                if btn:
                    await btn.click()
                    await asyncio.sleep(1)
            except Exception:
                pass

            card_selectors = [
                "[class*='resultCard']",
                "[data-test='job-card']",
                "a[href*='/empleo/']",
                ".offer-card",
            ]
            cards = []
            for sel in card_selectors:
                cards = await self._page.query_selector_all(sel)
                if cards:
                    logger.debug(f"OCC MX: matched {len(cards)} cards with '{sel}'")
                    break

            for card in cards[:20]:
                try:
                    title_el    = await card.query_selector("h2, [class*='title'], [class*='Title']")
                    company_el  = await card.query_selector("[class*='company'], [class*='Company']")
                    location_el = await card.query_selector("[class*='location'], [class*='Location']")
                    salary_el   = await card.query_selector("[class*='salary'], [class*='Salary']")

                    title    = (await title_el.inner_text()).strip()    if title_el    else ""
                    company  = (await company_el.inner_text()).strip()  if company_el  else ""
                    location = (await location_el.inner_text()).strip() if location_el else ""
                    salary_text = (await salary_el.inner_text()).strip() if salary_el  else ""

                    # Get job URL
                    href = ""
                    if card.evaluate:
                        tag = await card.evaluate("el => el.tagName")
                        if tag == "A":
                            href = await card.get_attribute("href") or ""
                    if not href:
                        link_el = await card.query_selector("a[href*='/empleo/']")
                        if link_el:
                            href = await link_el.get_attribute("href") or ""
                    job_url = f"https://www.occ.com.mx{href}" if href and href.startswith("/") else href

                    if not title or not job_url:
                        continue

                    # Parse salary
                    salary_min, salary_max = None, None
                    if salary_text:
                        nums = re.findall(r"[\d,]+", salary_text.replace(",", ""))
                        parsed = [int(n) for n in nums if n.strip() and int(n) > 1000]
                        if len(parsed) >= 2:
                            salary_min, salary_max = sorted(parsed[:2])
                        elif len(parsed) == 1:
                            salary_min = salary_max = parsed[0]

                    job = JobPosting(
                        title=title,
                        company=company,
                        location=location,
                        country="Mexico",
                        url=job_url,
                        apply_url=job_url,
                        source="occ.com.mx",
                        salary_min=salary_min,
                        salary_max=salary_max,
                        salary_currency="MXN",
                    )
                    if not self.is_blacklisted(job):
                        jobs.append(job)
                except Exception as e:
                    logger.debug(f"OCC MX card error: {e}")

            if not jobs:
                await self._page.screenshot(path="debug_occ_mx.png")
                logger.warning("OCC MX: 0 jobs found. Screenshot saved to debug_occ_mx.png")

        except Exception as e:
            logger.error(f"OCC MX scrape error: {e}")

        logger.info(f"OCC Mundial MX: found {len(jobs)} jobs for '{keyword}'")
        return jobs

    # ══════════════════════════════════════════════════════════
    # Dispatcher + detail fetcher
    # ══════════════════════════════════════════════════════════
    async def search(self, keyword: str, country: dict) -> list[JobPosting]:
        country_name = country["name"]
        match country_name:
            case "New Zealand": return await self.scrape_seek_nz(keyword)
            case "Germany":     return await self.scrape_stepstone_de(keyword)
            case "Poland":      return await self.scrape_pracuj_pl(keyword)
            case "Sweden":      return await self.scrape_arbetsformedlingen_se(keyword)
            case "Mexico":      return await self.scrape_occ_mx(keyword)
            case _:             return []

    async def get_job_details(self, job: JobPosting) -> JobPosting:
        """Fetch full description for a job. Uses API for Seek, Playwright for others."""
        if job.source == "seek.co.nz":
            return await self.seek_get_job_details(job)
        # OCC and other portals use the Playwright fallback below

        # Playwright fallback for other portals
        if not self._browser:
            await self._launch()
        try:
            await self._page.goto(job.url, wait_until="domcontentloaded", timeout=60_000)
            await asyncio.sleep(2)
            body_text = await self._page.inner_text("body")
            job.description = body_text[:3000]
        except Exception as e:
            logger.debug(f"Detail fetch error: {e}")
        return job