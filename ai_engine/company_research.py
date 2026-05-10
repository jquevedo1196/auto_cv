"""
Job Hunter Agent - Company Research
Lightweight company context fetching to personalize cover letters.
"""

import logging
from typing import Optional

import aiohttp

logger = logging.getLogger(__name__)


class CompanyResearcher:
    """Fetches basic company context for cover letter personalization."""

    def __init__(self):
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if not self._session or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=10),
                headers={
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                }
            )
        return self._session

    async def research(self, company_name: str, job_url: str = "") -> dict:
        """
        Gather basic company context. Returns a dict with whatever info
        could be found. Used to enrich cover letter prompts.
        """
        result = {
            "company": company_name,
            "about": "",
            "industry": "",
            "size_hint": "",
        }

        domain = self._guess_domain(company_name, job_url)
        if domain:
            about_text = await self._fetch_about_page(domain)
            if about_text:
                result["about"] = about_text[:600]

        return result

    def _guess_domain(self, company_name: str, job_url: str) -> str:
        """Attempt to guess the company's website domain."""
        if job_url:
            from urllib.parse import urlparse
            parsed = urlparse(job_url)
            host = parsed.hostname or ""
            # Skip job board domains
            job_boards = ["linkedin.com", "indeed.com", "seek.co", "stepstone.",
                          "pracuj.pl", "jobicy.com", "remotive.com"]
            if not any(jb in host for jb in job_boards):
                return f"https://{host}"

        clean = company_name.lower().replace(" ", "").replace(",", "").replace(".", "")
        return f"https://www.{clean}.com"

    async def _fetch_about_page(self, domain: str) -> str:
        """Try to fetch the company's about page for context."""
        urls_to_try = [
            f"{domain}/about",
            f"{domain}/about-us",
            domain,
        ]
        session = await self._get_session()

        for url in urls_to_try:
            try:
                async with session.get(url, allow_redirects=True, ssl=False) as resp:
                    if resp.status == 200:
                        text = await resp.text()
                        return self._extract_text(text)
            except Exception:
                continue
        return ""

    def _extract_text(self, html: str) -> str:
        """Extract readable text from HTML, stripping tags."""
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "nav", "header", "footer"]):
            tag.decompose()
        text = soup.get_text(separator=" ", strip=True)
        # Return first ~600 chars of meaningful text
        lines = [l.strip() for l in text.split("\n") if len(l.strip()) > 30]
        return " ".join(lines)[:600]

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
