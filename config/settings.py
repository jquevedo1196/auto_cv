"""
Job Hunter Agent - Settings
Configure your API keys, target countries, and job preferences here.
"""

import os
from dataclasses import dataclass, field
from typing import List

# ─────────────────────────────────────────────
# API KEYS — set these as environment variables
# ─────────────────────────────────────────────
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")  # None if not set — SDK will raise a clear error
GOOGLE_SHEETS_CREDENTIALS = os.getenv("GOOGLE_SHEETS_CREDENTIALS", "credentials.json")
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "")  # The spreadsheet ID from the URL

# LinkedIn credentials (use a secondary account if possible)
LINKEDIN_EMAIL = os.getenv("LINKEDIN_EMAIL", "")
LINKEDIN_PASSWORD = os.getenv("LINKEDIN_PASSWORD", "")

# ─────────────────────────────────────────────
# JOB SEARCH PREFERENCES
# ─────────────────────────────────────────────
@dataclass
class SearchConfig:
    keywords: List[str] = field(default_factory=lambda: [
        "Principal DevOps Engineer",
        "Senior DevOps Engineer",
        "SRE Engineer",
        "Platform Engineer",
        "Cloud Infrastructure Engineer",
        "Kubernetes Engineer",
    ])

    countries: List[dict] = field(default_factory=lambda: [
        {"name": "Canada",        "code": "ca", "linkedin_geo": "101174742"},
        {"name": "New Zealand",   "code": "nz", "linkedin_geo": "105490917"},
        {"name": "Sweden",        "code": "se", "linkedin_geo": "105117694"},
        {"name": "USA",           "code": "us", "linkedin_geo": "103644278"},
        {"name": "Germany",       "code": "de", "linkedin_geo": "101282230"},
        {"name": "Poland",        "code": "pl", "linkedin_geo": "105072130"},
        {"name": "Mexico",        "code": "mx", "linkedin_geo": "103323778"},
    ])

    # Only apply to jobs posted in the last N days
    max_days_old: int = 3

    # Minimum job score (0-100) to auto-apply
    min_score_to_apply: int = 85

    # Max applications per day — fewer, higher-quality applications
    max_daily_applications: int = 15

    # Job types
    job_types: List[str] = field(default_factory=lambda: [
        "full-time", "part-time", "contract"
    ])

    # Experience level filters
    experience_levels: List[str] = field(default_factory=lambda: [
        "senior", "staff"
    ])

    # Keywords that disqualify a job
    blacklist_keywords: List[str] = field(default_factory=lambda: [
        "clearance required", "security clearance", "top secret",
        "must be citizen", "junior", "intern",
        "must be authorized to work", "no sponsorship", "no visa",
        "us citizens only", "permanent resident required",
        "cannot sponsor", "unable to sponsor",
    ])

# Singleton
SEARCH_CONFIG = SearchConfig()
