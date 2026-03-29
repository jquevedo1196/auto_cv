"""
Job Hunter Agent - Local Run Cache
Persists job results to a local JSON file as a safety net.

Each run is tagged with a unique run_id. If Google Sheets upload fails,
the next run (or a manual --sync) can retry uploading from the local cache.

Cache lifecycle:
  1. Jobs are saved locally immediately after scoring (before Sheets upload).
  2. After successful Sheets upload, those jobs are marked as synced.
  3. On connect(), any unsynced jobs from previous runs are retried.
  4. Synced entries are purged after RETENTION_DAYS to keep the file small.
"""

import json
import logging
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Set

logger = logging.getLogger(__name__)

# Keep synced entries for 7 days before purging (in case you need to debug)
RETENTION_DAYS = 7

# Default cache location (next to agent.py → data/run_cache.json)
DEFAULT_CACHE_PATH = Path(__file__).parent.parent / "data" / "run_cache.json"


class LocalRunCache:
    """
    Stores job results locally as JSON, keyed by run_id.

    File structure:
    {
        "runs": {
            "<run_id>": {
                "created_at": "2026-03-26T02:00:00",
                "jobs": {
                    "<job_id>": {
                        "synced": false,
                        "synced_at": null,
                        "row": [ ... sheet row data ... ]
                    }
                }
            }
        }
    }
    """

    def __init__(self, cache_path: Optional[str] = None):
        self.path = Path(cache_path) if cache_path else DEFAULT_CACHE_PATH
        self._data: Dict = {"runs": {}}
        self._load()

    # ── persistence ────────────────────────────────────────────

    def _load(self):
        """Load cache from disk."""
        if self.path.exists():
            try:
                self._data = json.loads(self.path.read_text(encoding="utf-8"))
                total = sum(
                    len(run["jobs"]) for run in self._data.get("runs", {}).values()
                )
                pending = self.pending_count()
                logger.info(
                    f"Local cache loaded: {total} jobs total, {pending} pending sync"
                )
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(f"Corrupted cache file, starting fresh: {e}")
                self._data = {"runs": {}}
        else:
            logger.debug("No local cache found, starting fresh")

    def _save(self):
        """Flush cache to disk atomically (write-then-rename)."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp.replace(self.path)  # atomic on POSIX

    # ── run management ─────────────────────────────────────────

    @staticmethod
    def generate_run_id() -> str:
        """Create a unique run identifier: date + short UUID."""
        date_part = datetime.now().strftime("%Y%m%d_%H%M%S")
        uid = uuid.uuid4().hex[:8]
        return f"run_{date_part}_{uid}"

    def start_run(self, run_id: str):
        """Register a new run in the cache."""
        if run_id not in self._data["runs"]:
            self._data["runs"][run_id] = {
                "created_at": datetime.now().isoformat(),
                "jobs": {},
            }
            self._save()
            logger.info(f"Local cache: started run {run_id}")

    # ── writing jobs ───────────────────────────────────────────

    def save_jobs(self, run_id: str, jobs: list, row_builder) -> int:
        """
        Save jobs to local cache. Returns count of newly cached jobs.

        Args:
            run_id:      Current run identifier.
            jobs:        List of JobPosting objects.
            row_builder: Callable(job) → list  (produces a sheet-compatible row).
        """
        if run_id not in self._data["runs"]:
            self.start_run(run_id)

        run_data = self._data["runs"][run_id]
        added = 0

        for job in jobs:
            jid = job.job_id
            if jid not in run_data["jobs"]:
                run_data["jobs"][jid] = {
                    "synced": False,
                    "synced_at": None,
                    "row": row_builder(job),
                }
                added += 1

        if added:
            self._save()
            logger.info(f"Local cache: saved {added} new jobs for run {run_id}")

        return added

    # ── sync helpers ───────────────────────────────────────────

    def get_pending_jobs(self) -> List[dict]:
        """
        Return all unsynced jobs across every run.

        Each item: {"run_id": str, "job_id": str, "row": list}
        """
        pending = []
        for run_id, run_data in self._data.get("runs", {}).items():
            for job_id, entry in run_data.get("jobs", {}).items():
                if not entry.get("synced", False):
                    pending.append({
                        "run_id": run_id,
                        "job_id": job_id,
                        "row": entry["row"],
                    })
        return pending

    def pending_count(self) -> int:
        """Count of jobs not yet synced to Google Sheets."""
        return sum(
            1
            for run in self._data.get("runs", {}).values()
            for entry in run.get("jobs", {}).values()
            if not entry.get("synced", False)
        )

    def mark_synced(self, job_ids: List[str]):
        """Mark jobs as successfully uploaded to Google Sheets."""
        now = datetime.now().isoformat()
        marked = 0
        for run_data in self._data["runs"].values():
            for jid in job_ids:
                if jid in run_data["jobs"] and not run_data["jobs"][jid]["synced"]:
                    run_data["jobs"][jid]["synced"] = True
                    run_data["jobs"][jid]["synced_at"] = now
                    marked += 1
        if marked:
            self._save()
            logger.debug(f"Local cache: marked {marked} jobs as synced")

    def mark_synced_by_rows(self, rows: List[list]):
        """Mark synced using the row data (job_id is row[0])."""
        ids = [row[0] for row in rows if row]
        self.mark_synced(ids)

    # ── cleanup ────────────────────────────────────────────────

    def purge_old_synced(self, retention_days: int = RETENTION_DAYS):
        """
        Remove fully-synced runs older than retention_days.
        Keeps unsynced runs forever (they still need to be uploaded).
        """
        cutoff = datetime.now() - timedelta(days=retention_days)
        to_delete = []

        for run_id, run_data in self._data["runs"].items():
            created = datetime.fromisoformat(run_data["created_at"])
            if created >= cutoff:
                continue  # too recent to purge

            # Only purge if ALL jobs in this run are synced
            all_synced = all(
                entry.get("synced", False)
                for entry in run_data["jobs"].values()
            )
            if all_synced:
                to_delete.append(run_id)

        for run_id in to_delete:
            del self._data["runs"][run_id]

        if to_delete:
            self._save()
            logger.info(
                f"Local cache: purged {len(to_delete)} fully-synced runs "
                f"older than {retention_days} days"
            )

    # ── all cached job IDs (for dedup in scraping phase) ──────

    def all_cached_job_ids(self) -> Set[str]:
        """Return every job_id in the cache (synced or not)."""
        ids = set()
        for run_data in self._data.get("runs", {}).values():
            ids.update(run_data.get("jobs", {}).keys())
        return ids
