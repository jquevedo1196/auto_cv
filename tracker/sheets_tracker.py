"""
Job Hunter Agent - Google Sheets Tracker
Saves all job applications to a Google Sheet for tracking.

Flow:
  1. Jobs are ALWAYS saved to LocalRunCache first (safety net).
  2. Then uploaded to Google Sheets in batches with retry/reconnect.
  3. Successfully uploaded jobs are marked as "synced" in the cache.
  4. On connect(), any unsynced jobs from previous runs are retried.
  5. Old fully-synced runs are purged after 7 days.
"""

import logging
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from tracker.local_cache import LocalRunCache

logger = logging.getLogger(__name__)

# Column headers for the tracking sheet
SHEET_HEADERS = [
    "Job ID", "Title", "Company", "Location", "Country", "Source",
    "Score", "Status", "Easy Apply", "Salary", "Posted Date",
    "Applied Date", "URL", "Cover Letter Preview", "Resume Version"
]

try:
    import gspread
    from google.oauth2.service_account import Credentials
    GSPREAD_AVAILABLE = True
except ImportError:
    GSPREAD_AVAILABLE = False
    logger.warning("gspread not installed. Run: pip install gspread google-auth")


class SheetsTracker:
    """Tracks job applications in Google Sheets with local cache as safety net."""

    SCOPES = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]

    def __init__(self, credentials_path: str, sheet_id: str, cache_path: str = None):
        self.credentials_path = credentials_path
        self.sheet_id = sheet_id
        self._client = None
        self._sheet = None
        self._existing_ids: set = set()
        self._applied_ids: set = set()

        # Local cache — always available even if Sheets fails
        self.cache = LocalRunCache(cache_path)
        self._run_id: Optional[str] = None

    @property
    def run_id(self) -> str:
        """Current run ID. Generated lazily on first access."""
        if self._run_id is None:
            self._run_id = LocalRunCache.generate_run_id()
            self.cache.start_run(self._run_id)
        return self._run_id

    def connect(self) -> bool:
        """Connect to Google Sheets and sync any pending local jobs."""
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
                self._sheet.update("A1", [SHEET_HEADERS])
                self._sheet.format("A1:N1", {
                    "textFormat": {"bold": True},
                    "backgroundColor": {"red": 0.2, "green": 0.2, "blue": 0.8},
                })

            # Cache existing job IDs to avoid duplicates
            existing_rows = self._sheet.get_all_values()
            if len(existing_rows) > 1:
                self._existing_ids = {row[0] for row in existing_rows[1:] if row}
                self._applied_ids = {
                    row[0] for row in existing_rows[1:]
                    if row and len(row) > 7 and row[7] in ("applied", "interview", "offer", "rejected")
                }
                logger.info(
                    f"Connected to Google Sheets. {len(self._existing_ids)} existing entries "
                    f"({len(self._applied_ids)} already applied)."
                )

            # Sync pending jobs from previous failed runs
            self._sync_pending_from_cache()

            # Purge old synced entries from local cache
            self.cache.purge_old_synced()

            return True

        except Exception as e:
            logger.error(f"Google Sheets connection error: {e}")
            return False

    def _reconnect(self) -> bool:
        """Re-authenticate and reconnect to the sheet (refreshes stale SSL sessions)."""
        try:
            logger.info("Reconnecting to Google Sheets...")
            creds = Credentials.from_service_account_file(
                self.credentials_path, scopes=self.SCOPES
            )
            self._client = gspread.authorize(creds)
            spreadsheet = self._client.open_by_key(self.sheet_id)
            self._sheet = spreadsheet.worksheet("Applications")
            logger.info("Reconnected to Google Sheets successfully ✅")
            return True
        except Exception as e:
            logger.error(f"Reconnection failed: {e}")
            return False

    # ── sync from local cache ──────────────────────────────────

    def _sync_pending_from_cache(self):
        """Upload any unsynced jobs from local cache to Google Sheets."""
        pending = self.cache.get_pending_jobs()
        if not pending:
            return

        # Filter out jobs that are already in Sheets (uploaded by another means)
        truly_pending = [p for p in pending if p["job_id"] not in self._existing_ids]

        # Mark already-in-sheets jobs as synced (no need to re-upload)
        already_there = [p["job_id"] for p in pending if p["job_id"] in self._existing_ids]
        if already_there:
            self.cache.mark_synced(already_there)
            logger.info(
                f"Local cache: {len(already_there)} jobs already in Sheets, marked synced"
            )

        if not truly_pending:
            return

        logger.info(
            f"🔄 Syncing {len(truly_pending)} pending jobs from local cache to Sheets..."
        )

        rows = [p["row"] for p in truly_pending]
        synced_ids = self._upload_rows_batched(rows)

        if synced_ids:
            self.cache.mark_synced(synced_ids)
            self._existing_ids.update(synced_ids)
            logger.info(f"✅ Synced {len(synced_ids)}/{len(truly_pending)} pending jobs")

    # ── save jobs (main entry point) ───────────────────────────

    def save_job(self, job) -> bool:
        """Save a single job to cache + sheet. Returns True if saved."""
        if job.job_id in self._existing_ids:
            return False

        # Always save to local cache first
        self.cache.save_jobs(self.run_id, [job], self._job_to_row)

        if not self._sheet:
            logger.warning("Sheet not connected — job saved to local cache only")
            return True

        try:
            row = self._job_to_row(job)
            self._sheet.append_row(row, value_input_option="RAW")
            self._existing_ids.add(job.job_id)
            self.cache.mark_synced([job.job_id])
            logger.info(f"Saved to sheet: {job.title} @ {job.company} ({job.country})")
            return True
        except Exception as e:
            logger.error(f"Error saving job to sheet (cached locally): {e}")
            return True  # still True because it's in the local cache

    def save_jobs(self, jobs: list) -> int:
        """
        Save multiple jobs:
          1. Write ALL to local cache immediately (crash-safe).
          2. Upload to Google Sheets in batches with retry.
          3. Mark successfully uploaded jobs as synced in cache.
        """
        # Filter duplicates
        new_jobs = [j for j in jobs if j.job_id not in self._existing_ids]
        if not new_jobs:
            return 0

        # Step 1: Save to local cache FIRST (always succeeds)
        self.cache.save_jobs(self.run_id, new_jobs, self._job_to_row)
        logger.info(f"💾 {len(new_jobs)} jobs saved to local cache (run: {self.run_id})")

        if not self._sheet:
            logger.warning("Sheet not connected — all jobs saved to local cache only")
            return len(new_jobs)

        # Step 2: Upload to Google Sheets
        rows = [self._job_to_row(job) for job in new_jobs]
        synced_ids = self._upload_rows_batched(rows)

        # Step 3: Mark synced
        if synced_ids:
            self.cache.mark_synced(synced_ids)
            self._existing_ids.update(synced_ids)

        failed = len(new_jobs) - len(synced_ids)
        if failed:
            logger.warning(
                f"⚠️  {failed} jobs failed to upload to Sheets "
                f"but are safe in local cache (run: {self.run_id}). "
                f"They will be retried on next run."
            )

        return len(new_jobs)

    def _upload_rows_batched(self, rows: List[list]) -> List[str]:
        """
        Upload rows to Google Sheets in batches with retry.
        Returns list of successfully uploaded job_ids (row[0]).
        """
        BATCH_SIZE = 50
        MAX_RETRIES = 3
        synced_ids = []

        for i in range(0, len(rows), BATCH_SIZE):
            batch = rows[i: i + BATCH_SIZE]
            for attempt in range(1, MAX_RETRIES + 1):
                try:
                    self._sheet.append_rows(batch, value_input_option="RAW")
                    batch_ids = [row[0] for row in batch]
                    synced_ids.extend(batch_ids)
                    logger.info(
                        f"Batch uploaded {len(batch)} jobs to Sheets "
                        f"({len(synced_ids)}/{len(rows)} total)"
                    )
                    break
                except Exception as e:
                    logger.warning(
                        f"Batch upload attempt {attempt}/{MAX_RETRIES} failed: {e}"
                    )
                    if attempt < MAX_RETRIES:
                        time.sleep(2 ** attempt)
                        self._reconnect()
                    else:
                        logger.error(
                            f"Batch upload failed after {MAX_RETRIES} retries. "
                            f"{len(batch)} rows will be retried on next run."
                        )

        return synced_ids

    # ── status updates ─────────────────────────────────────────

    def update_job_status(self, job_id: str, status: str, applied_date: Optional[datetime] = None):
        """Update the status of an existing job entry."""
        if not self._sheet:
            return

        try:
            cell = self._sheet.find(job_id)
            if cell:
                row = cell.row
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
        resume_version = ""
        if hasattr(job, "resume_path") and job.resume_path:
            resume_version = Path(job.resume_path).name
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
            resume_version,
        ]


class LocalCSVTracker:
    """
    Fallback tracker that saves to a local CSV file
    when Google Sheets is not configured.
    """

    def __init__(self, filepath: str = "job_applications.csv"):
        self.filepath = filepath
        self._existing_ids: set = set()
        self._applied_ids: set = set()
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
