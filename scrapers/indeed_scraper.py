"""
Job Hunter Agent - Indeed Scraper
NOTE: Indeed aggressively blocks all automated scraping (403s regardless of method).
This module now uses a fallback strategy per country:
  - Canada      → Skipped (LinkedIn covers CA well) + Jobicy API (free, no auth)
  - New Zealand → Seek.co.nz is used via country_scrapers.py instead
  - Sweden      → Arbetsformedlingen API used instead
  - Germany     → StepStone used instead
  - Poland      → Pracuj.pl used instead

For Canada specifically, we add Jobicy (remote-friendly jobs, many Canadian companies)
and the Remotive API as supplementary sources.
"""

import asyncio
import logging
import re
from datetime import datetime
from typing import Optional

import aiohttp

from scrapers.base_scraper import BaseScraper, JobPosting

logger = logging.getLogger(__name__)


class IndeedScraper(BaseScraper):
    """
    Supplementary job scraper using free public APIs.
    Replaces Indeed (which blocks scraping) with:
      - Jobicy API  (remote jobs, many CA/international companies, free)
      - Remotive API (remote tech jobs, free)
    """

    JOBICY_API  = "https://jobicy.com/api/v2/remote-jobs"
    REMOTIVE_API = "https://remotive.com/api/remote-jobs"

    def __init__(self, config):
        super().__init__(config)
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=20),
            )
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    async def search(self, keyword: str, country: dict) -> list[JobPosting]:
        """Fetch jobs from free public APIs filtered by keyword."""
        country_name = country["name"]

        # These APIs focus on remote/international jobs — most relevant for Canada
        # For other countries the dedicated scrapers in country_scrapers.py handle it
        if country_name not in ("Canada", "New Zealand", "Sweden", "Germany", "Poland"):
            return []

        jobs: list[JobPosting] = []

        # Run both APIs concurrently
        jobicy_jobs, remotive_jobs = await asyncio.gather(
            self._fetch_jobicy(keyword, country_name),
            self._fetch_remotive(keyword, country_name),
            return_exceptions=True,
        )

        if isinstance(jobicy_jobs, list):
            jobs.extend(jobicy_jobs)
        if isinstance(remotive_jobs, list):
            jobs.extend(remotive_jobs)

        logger.info(f"Supplementary APIs ({country_name}): found {len(jobs)} jobs for '{keyword}'")
        return jobs

    # ── Jobicy API ───────────────────────────────────────────

    async def _fetch_jobicy(self, keyword: str, country_name: str) -> list[JobPosting]:
        """Fetch from Jobicy public API — no auth required."""
        session = await self._get_session()
        params = {
            "count":  20,
            "geo":    self._country_to_geo(country_name),
            "industry": "engineering",
            "tag":    keyword.lower().replace(" ", "-"),
        }
        try:
            async with session.get(self.JOBICY_API, params=params) as resp:
                if resp.status != 200:
                    logger.debug(f"Jobicy API returned {resp.status}")
                    return []
                data = await resp.json()
                return self._parse_jobicy(data.get("jobs", []), country_name)
        except Exception as e:
            logger.debug(f"Jobicy fetch error: {e}")
            return []

    def _parse_jobicy(self, jobs_data: list, country_name: str) -> list[JobPosting]:
        jobs = []
        for item in jobs_data:
            try:
                title = item.get("jobTitle", "")
                company = item.get("companyName", "")
                url = item.get("url", "")
                description = item.get("jobDescription", "")
                salary_min = item.get("annualSalaryMin")
                salary_max = item.get("annualSalaryMax")
                currency = item.get("salaryCurrency", "USD")

                if not title or not url:
                    continue

                # Parse date
                pub_date = item.get("pubDate", "")
                posted_date = None
                if pub_date:
                    try:
                        posted_date = datetime.strptime(pub_date[:10], "%Y-%m-%d")
                    except Exception:
                        pass

                job = JobPosting(
                    title=title,
                    company=company,
                    location=item.get("jobGeo", "Remote"),
                    country=country_name,
                    url=url,
                    apply_url=url,
                    source="jobicy",
                    description=description[:2000],
                    posted_date=posted_date,
                    salary_min=int(salary_min) if salary_min else None,
                    salary_max=int(salary_max) if salary_max else None,
                    salary_currency=currency,
                )
                if not self.is_blacklisted(job):
                    jobs.append(job)
            except Exception as e:
                logger.debug(f"Jobicy parse error: {e}")
        return jobs

    # ── Remotive API ─────────────────────────────────────────

    async def _fetch_remotive(self, keyword: str, country_name: str) -> list[JobPosting]:
        """Fetch from Remotive public API — no auth required."""
        session = await self._get_session()
        params = {
            "search":   keyword,
            "category": "devops-sysadmin",
            "limit":    20,
        }
        try:
            async with session.get(self.REMOTIVE_API, params=params) as resp:
                if resp.status != 200:
                    logger.debug(f"Remotive API returned {resp.status}")
                    return []
                data = await resp.json()
                return self._parse_remotive(data.get("jobs", []), country_name)
        except Exception as e:
            logger.debug(f"Remotive fetch error: {e}")
            return []

    def _parse_remotive(self, jobs_data: list, country_name: str) -> list[JobPosting]:
        jobs = []
        for item in jobs_data:
            try:
                title = item.get("title", "")
                company = item.get("company_name", "")
                url = item.get("url", "")
                description = item.get("description", "")
                salary = item.get("salary", "")

                if not title or not url:
                    continue

                pub_date_str = item.get("publication_date", "")
                posted_date = None
                if pub_date_str:
                    try:
                        posted_date = datetime.fromisoformat(pub_date_str[:10])
                    except Exception:
                        pass

                # Parse salary range from string like "$100k - $140k"
                salary_min, salary_max = self._parse_salary_string(salary)

                job = JobPosting(
                    title=title,
                    company=company,
                    location=item.get("candidate_required_location", "Remote"),
                    country=country_name,
                    url=url,
                    apply_url=url,
                    source="remotive",
                    description=description[:2000],
                    posted_date=posted_date,
                    salary_min=salary_min,
                    salary_max=salary_max,
                    salary_currency="USD",
                )
                if not self.is_blacklisted(job):
                    jobs.append(job)
            except Exception as e:
                logger.debug(f"Remotive parse error: {e}")
        return jobs

    # ── Helpers ──────────────────────────────────────────────

    async def get_job_details(self, job: JobPosting) -> JobPosting:
        """Details already included in API responses — nothing extra to fetch."""
        return job

    @staticmethod
    def _country_to_geo(country_name: str) -> str:
        return {
            "Canada":      "canada",
            "New Zealand": "new-zealand",
            "Sweden":      "sweden",
            "Germany":     "germany",
            "Poland":      "poland",
        }.get(country_name, "worldwide")

    @staticmethod
    def _parse_salary_string(text: str) -> tuple[Optional[int], Optional[int]]:
        if not text:
            return None, None
        numbers = re.findall(r"(\d+)[kK]?", text.replace(",", ""))
        parsed = []
        for n in numbers:
            val = int(n)
            if val < 1000:
                val *= 1000  # assume "k" notation
            parsed.append(val)
        if len(parsed) >= 2:
            return sorted(parsed[:2])
        elif len(parsed) == 1:
            return parsed[0], parsed[0]
        return None, None