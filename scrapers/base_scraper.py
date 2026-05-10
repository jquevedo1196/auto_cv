"""
Job Hunter Agent - Base Scraper
Abstract base class for all job scrapers.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


@dataclass
class JobPosting:
    """Normalized job posting from any source."""
    # Required fields
    title:       str
    company:     str
    location:    str
    country:     str
    url:         str
    source:      str  # linkedin, indeed, seek, stepstone, pracuj

    # Optional fields
    description:     str = ""
    salary_min:      Optional[int] = None
    salary_max:      Optional[int] = None
    salary_currency: str = "USD"
    job_type:        str = "full-time"   # full-time, contract, part-time
    posted_date:     Optional[datetime] = None
    apply_url:       str = ""
    easy_apply:      bool = False        # LinkedIn Easy Apply

    # Computed fields
    job_id:          str = ""
    score:           int = 0            # AI relevance score 0-100
    cover_letter:    str = ""           # Generated cover letter
    resume_path:     str = ""           # Path to tailored resume PDF
    applied:         bool = False
    applied_date:    Optional[datetime] = None
    status:          str = "found"      # found | scored | applied | rejected | interview

    def __post_init__(self):
        if not self.job_id:
            import hashlib
            self.job_id = hashlib.md5(
                f"{self.title}{self.company}{self.url}".encode()
            ).hexdigest()[:12]

    def to_dict(self) -> dict:
        return {
            "job_id":        self.job_id,
            "title":         self.title,
            "company":       self.company,
            "location":      self.location,
            "country":       self.country,
            "url":           self.url,
            "source":        self.source,
            "salary":        f"{self.salary_currency} {self.salary_min}-{self.salary_max}" if self.salary_min else "N/A",
            "job_type":      self.job_type,
            "posted_date":   self.posted_date.strftime("%Y-%m-%d") if self.posted_date else "",
            "easy_apply":    str(self.easy_apply),
            "score":         self.score,
            "status":        self.status,
            "applied_date":  self.applied_date.strftime("%Y-%m-%d %H:%M") if self.applied_date else "",
            "apply_url":     self.apply_url or self.url,
            "cover_letter":  self.cover_letter,
        }


class BaseScraper(ABC):
    """Abstract base for all job scrapers."""

    def __init__(self, config):
        self.config = config
        self.logger = logging.getLogger(self.__class__.__name__)

    @abstractmethod
    async def search(self, keyword: str, country: dict) -> List[JobPosting]:
        """Search for jobs with given keyword in given country."""
        pass

    @abstractmethod
    async def get_job_details(self, job: JobPosting) -> JobPosting:
        """Fetch full job description for a posting."""
        pass

    def is_blacklisted(self, job: JobPosting) -> bool:
        """Check if job contains blacklist keywords."""
        text = (job.title + " " + job.description).lower()
        return any(kw.lower() in text for kw in self.config.blacklist_keywords)