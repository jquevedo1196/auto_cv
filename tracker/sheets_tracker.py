"""
Job Hunter Agent - Google Sheets Tracker
Saves all job applications to a Google Sheet for tracking.
Sheet columns: Job ID | Title | Company | Country | Source | Score | Status | Applied Date | URL | Salary | Cover Letter
"""

import logging
from datetime import datetime
from typing import List, Optional

logger = logging.getLogger(__name__)

# Column headers for the tracking sheet
SHEET_HEADERS = [
    "Job ID", "Title", "Company", "Location", "Country", "Source",
    "Score", "Status", "Easy Apply", "Salary", "Posted Date",
    "Applied Date", "URL", "Cover Letter Preview"
]

try:
    import gspread
    from google.oauth2.service_account import Credentials
    GSPREAD_AVAILABLE = True
except ImportError:
    GSPREAD_AVAILABLE = False
    logger.warning("gspread not installed. Run: pip install gspread google-auth")


class SheetsTracker:
    """Tracks job applications in Google Sheets."""

    SCOPES = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]

    def __init__(self, credentials_path: str, sheet_id: str):
        self.credentials_path = credentials_path
        self.sheet_id = sheet_id
        self._client = None
        self._sheet = None
        self._existing_ids: set = set()
        self._applied_ids: set = set()

    def connect(self) -> bool:
        """Connect to Google Sheets."""
        if not GSPREAD_AVAILABLE:
            logger.error("gspread not available. Install: pip install gspread google-auth")
            return False

        try:
            creds = Credentials.from_service_account_file(
                self.credentials_path, scopes=self.SCOPES
            )
            self._client = gspread.authorize(creds)
            spreadsheet = self._client.open_by_key(self.sheet_id)

            # Get or create the "Applications" worksheet
            try:
                self._sheet = spreadsheet.worksheet("Applications")
            except gspread.exceptions.WorksheetNotFound:
                self._sheet = spreadsheet.add_worksheet(
                    title="Applications", rows=1000, cols=len(SHEET_HEADERS)
                )
                # Write headers
                self._sheet.update("A1", [SHEET_HEADERS])
                # Format header row (bold)
                self._sheet.format("A1:N1", {
                    "textFormat": {"bold": True},
                    "backgroundColor": {"red": 0.2, "green": 0.2, "blue": 0.8},
                })

            # Cache existing job IDs to avoid duplicates
            existing_rows = self._sheet.get_all_values()
            if len(existing_rows) > 1:
                self._existing_ids = {row[0] for row in existing_rows[1:] if row}
                # Also cache applied job IDs separately — never re-apply
                self._applied_ids = {
                    row[0] for row in existing_rows[1:]
                    if row and len(row) > 7 and row[7] in ("applied", "interview", "offer", "rejected")
                }
                logger.info(
                    f"Connected to Google Sheets. {len(self._existing_ids)} existing entries "
                    f"({len(self._applied_ids)} already applied)."
                )
            return True

        except Exception as e:
            logger.error(f"Google Sheets connection error: {e}")
            return False

    def save_job(self, job) -> bool:
        """Save a single job to the sheet. Returns True if saved (False if duplicate)."""
        if not self._sheet:
            logger.warning("Sheet not connected")
            return False

        if job.job_id in self._existing_ids:
            logger.debug(f"Duplicate job skipped: {job.job_id}")
            return False

        try:
            row = self._job_to_row(job)
            self._sheet.append_row(row, value_input_option="RAW")
            self._existing_ids.add(job.job_id)
            logger.info(f"Saved to sheet: {job.title} @ {job.company} ({job.country})")
            return True
        except Exception as e:
            logger.error(f"Error saving job to sheet: {e}")
            return False

    def save_jobs(self, jobs: list) -> int:
        """Save multiple jobs. Returns count of new entries saved."""
        if not self._sheet:
            logger.warning("Sheet not connected, cannot save jobs")
            return 0

        new_rows = []
        for job in jobs:
            if job.job_id not in self._existing_ids:
                new_rows.append(self._job_to_row(job))
                self._existing_ids.add(job.job_id)

        if new_rows:
            try:
                self._sheet.append_rows(new_rows, value_input_option="RAW")
                logger.info(f"Batch saved {len(new_rows)} new jobs to sheet")
            except Exception as e:
                logger.error(f"Batch save error: {e}")
                return 0

        return len(new_rows)

    def update_job_status(self, job_id: str, status: str, applied_date: Optional[datetime] = None):
        """Update the status of an existing job entry."""
        if not self._sheet:
            return

        try:
            cell = self._sheet.find(job_id)
            if cell:
                row = cell.row
                # Status is column 8 (index 7)
                self._sheet.update_cell(row, 8, status)
                if applied_date:
                    self._sheet.update_cell(row, 12, applied_date.strftime("%Y-%m-%d %H:%M"))
                logger.info(f"Updated status for job {job_id} → {status}")
        except Exception as e:
            logger.error(f"Error updating job status: {e}")

    def get_applied_count_today(self) -> int:
        """Get count of applications made today."""
        if not self._sheet:
            return 0
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            all_rows = self._sheet.get_all_values()
            count = sum(1 for row in all_rows[1:] if len(row) > 11 and today in row[11])
            return count
        except Exception:
            return 0

    def _job_to_row(self, job) -> list:
        """Convert a JobPosting to a sheet row."""
        d = job.to_dict()
        return [
            d["job_id"],
            d["title"],
            d["company"],
            d["location"],
            d["country"],
            d["source"],
            d["score"],
            d["status"],
            d["easy_apply"],
            d["salary"],
            d["posted_date"],
            d["applied_date"],
            d["apply_url"],
            d["cover_letter"],
        ]


class LocalCSVTracker:
    """
    Fallback tracker that saves to a local CSV file
    when Google Sheets is not configured.
    """

    def __init__(self, filepath: str = "job_applications.csv"):
        self.filepath = filepath
        self._existing_ids: set = set()
        self._load_existing()

    def _load_existing(self):
        """Load existing job IDs from CSV."""
        import csv
        from pathlib import Path
        if Path(self.filepath).exists():
            with open(self.filepath, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if "Job ID" in row:
                        self._existing_ids.add(row["Job ID"])
        logger.info(f"CSV tracker loaded {len(self._existing_ids)} existing entries")

    def save_job(self, job) -> bool:
        """Save job to CSV. Returns True if new entry was added."""
        import csv
        from pathlib import Path

        if job.job_id in self._existing_ids:
            return False

        file_exists = Path(self.filepath).exists()
        with open(self.filepath, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=SHEET_HEADERS)
            if not file_exists:
                writer.writeheader()
            writer.writerow(dict(zip(SHEET_HEADERS, [
                job.job_id, job.title, job.company, job.location,
                job.country, job.source, job.score, job.status,
                job.easy_apply, f"{job.salary_currency} {job.salary_min}-{job.salary_max}" if job.salary_min else "N/A",
                job.posted_date.strftime("%Y-%m-%d") if job.posted_date else "",
                job.applied_date.strftime("%Y-%m-%d %H:%M") if job.applied_date else "",
                job.apply_url or job.url,
                job.cover_letter[:300] if job.cover_letter else "",
            ])))

        self._existing_ids.add(job.job_id)
        logger.info(f"CSV saved: {job.title} @ {job.company}")
        return True

    def save_jobs(self, jobs: list) -> int:
        return sum(1 for job in jobs if self.save_job(job))

    def connect(self) -> bool:
        return True  # Always available

    def update_job_status(self, job_id: str, status: str, applied_date=None):
        pass  # Would require rewriting the CSV; skip for simplicity