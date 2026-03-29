"""
Job Hunter Agent - Main Orchestrator
Coordinates scraping, AI scoring, form filling, and tracking.

Usage:
    # Run once
    python agent.py

    # Run on a schedule (every day at 9am)
    python agent.py --schedule

    # Dry run (scrape and score, but don't apply)
    python agent.py --dry-run

    # Only specific country
    python agent.py --country Canada
"""

import argparse
import asyncio
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import List

# Load .env only in development (if file exists)
# In production (Docker), env vars are injected directly
from dotenv import load_dotenv
_env_file = Path(__file__).parent / ".env"
if _env_file.exists():
    load_dotenv(_env_file)
    # logger.debug(".env loaded (development mode)")

from config.settings import SEARCH_CONFIG, ANTHROPIC_API_KEY, GOOGLE_SHEETS_CREDENTIALS, \
    GOOGLE_SHEET_ID, LINKEDIN_EMAIL, LINKEDIN_PASSWORD
from scrapers.base_scraper import JobPosting
from scrapers.linkedin_scraper import LinkedInScraper
from scrapers.indeed_scraper import IndeedScraper
from scrapers.country_scrapers import CountryScraper
from ai_engine.cover_letter import AIEngine
from applier.linkedin_applier import LinkedInApplier
from applier.external_applier import ExternalApplier
from tracker.sheets_tracker import SheetsTracker, LocalCSVTracker
from tracker.local_cache import LocalRunCache

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("agent.log"),
    ]
)
logger = logging.getLogger("JobHunterAgent")


class JobHunterAgent:
    """Main agent that orchestrates the full job search and application pipeline."""

    def __init__(self, dry_run: bool = False, country_filter: str = None, no_ai: bool = False):
        self.dry_run = dry_run
        self.country_filter = country_filter
        self.no_ai = no_ai
        self.config = SEARCH_CONFIG

        # Initialize AI engine
        self.ai = AIEngine(api_key=ANTHROPIC_API_KEY)

        # Initialize tracker (Google Sheets if configured, else CSV fallback)
        if GOOGLE_SHEET_ID and GOOGLE_SHEETS_CREDENTIALS:
            self.tracker = SheetsTracker(GOOGLE_SHEETS_CREDENTIALS, GOOGLE_SHEET_ID)
        else:
            logger.warning("Google Sheets not configured, using local CSV tracker")
            self.tracker = LocalCSVTracker()

        self.linkedin_scraper: LinkedInScraper = None
        self.indeed_scraper: IndeedScraper = None
        self.country_scraper: CountryScraper = None

        # Stats for this run
        self.stats = {
            "jobs_found":   0,
            "jobs_scored":  0,
            "jobs_applied": 0,
            "errors":       0,
        }

    async def run(self):
        """Main execution flow."""
        logger.info("=" * 60)
        logger.info("🚀 Job Hunter Agent Starting")
        logger.info(f"   Mode: {'DRY RUN' if self.dry_run else 'LIVE'}{' + NO AI' if self.no_ai else ''}")
        logger.info(f"   Countries: {self.country_filter or 'ALL'}")
        # Assign run_id early so it appears in logs and is used for caching
        if hasattr(self.tracker, 'run_id'):
            logger.info(f"   Run ID: {self.tracker.run_id}")
        logger.info("=" * 60)

        # Connect tracker
        self.tracker.connect()

        # Check daily application limit
        applied_today = 0
        if hasattr(self.tracker, 'get_applied_count_today'):
            applied_today = self.tracker.get_applied_count_today()
        logger.info(f"Applications already sent today: {applied_today}")

        if applied_today >= self.config.max_daily_applications and not self.dry_run:
            logger.warning(f"Daily limit of {self.config.max_daily_applications} reached. Stopping.")
            return

        # Initialize scrapers
        self.linkedin_scraper = LinkedInScraper(
            self.config, LINKEDIN_EMAIL, LINKEDIN_PASSWORD
        )
        self.indeed_scraper = IndeedScraper(self.config)
        self.country_scraper = CountryScraper(self.config)

        all_jobs: List[JobPosting] = []

        # Determine which countries to search
        countries = self.config.countries
        if self.country_filter:
            countries = [c for c in countries if c["name"].lower() == self.country_filter.lower()]
            if not countries:
                logger.error(f"Country '{self.country_filter}' not found in config")
                return

        # ── PHASE 1: SCRAPE ──────────────────────────────────
        logger.info("\n📡 PHASE 1: Scraping jobs...")
        for country in countries:
            for keyword in self.config.keywords:
                try:
                    # LinkedIn — Easy Apply jobs (will be auto-applied)
                    ea_jobs = await self.linkedin_scraper.search(
                        keyword, country, easy_apply_filter=True
                    )
                    all_jobs.extend(ea_jobs)

                    # LinkedIn — all jobs without filter (catches high-score non-EA jobs
                    # for manual review). ea_jobs were extended first above, so any job
                    # that appears in both searches keeps its easy_apply=True value
                    # when agent.py deduplicates by job_id.
                    all_jobs_search = await self.linkedin_scraper.search(
                        keyword, country, easy_apply_filter=False
                    )
                    all_jobs.extend(all_jobs_search)

                    # Indeed (all countries — localized domains)
                    indeed_jobs = await self.indeed_scraper.search(keyword, country)
                    all_jobs.extend(indeed_jobs)

                    # Country-specific portals (Seek, StepStone, Pracuj, Arbetsformedlingen)
                    if country["name"] != "Canada":  # Canada covered well by LinkedIn + Indeed
                        local_jobs = await self.country_scraper.search(keyword, country)
                        all_jobs.extend(local_jobs)

                    await asyncio.sleep(2)  # Rate limiting

                except Exception as e:
                    logger.error(f"Scraping error for {keyword} in {country['name']}: {e}")
                    self.stats["errors"] += 1

        # Deduplicate by job_id
        seen = set()
        unique_jobs = []
        for job in all_jobs:
            if job.job_id not in seen:
                seen.add(job.job_id)
                unique_jobs.append(job)

        # Filter out jobs already in the tracker (seen in previous runs)
        already_tracked = getattr(self.tracker, '_existing_ids', set())
        already_applied = getattr(self.tracker, '_applied_ids', set())

        new_jobs = [j for j in unique_jobs if j.job_id not in already_tracked]
        skipped = len(unique_jobs) - len(new_jobs)
        if skipped:
            logger.info(f"   ⏭️  Skipped {skipped} jobs already in tracker from previous runs")

        self.stats["jobs_found"] = len(new_jobs)
        logger.info(f"\n✅ Found {len(new_jobs)} new unique jobs ({len(unique_jobs) - len(new_jobs)} already seen)")

        # ── PHASE 2: FETCH DETAILS ────────────────────────────
        logger.info("\n🔍 PHASE 2: Fetching job details...")
        jobs_needing_details = [j for j in new_jobs[:50] if not j.description]
        logger.info(f"   Fetching details for {len(jobs_needing_details)} jobs...")

        # LinkedIn uses a single shared page object — must be sequential, not parallel
        for i, job in enumerate(jobs_needing_details):
            try:
                if job.source == "linkedin":
                    updated = await self.linkedin_scraper.get_job_details(job)
                else:
                    updated = await self.country_scraper.get_job_details(job)
                job.__dict__.update(updated.__dict__)
            except Exception as e:
                logger.debug(f"Detail fetch error for {job.title}: {e}")
            if (i + 1) % 5 == 0 or (i + 1) == len(jobs_needing_details):
                logger.info(f"   Fetched {i + 1}/{len(jobs_needing_details)}")

        # ── PHASE 3: AI SCORING + COVER LETTERS ──────────────
        if self.no_ai:
            logger.info("\n⏭️  PHASE 3: Skipping AI (--no-ai flag) — all jobs marked score=99")
            qualified_jobs = new_jobs
            for job in qualified_jobs:
                job.score = 99
                job.status = "no-ai-review"
            self.stats["jobs_scored"] = len(qualified_jobs)
        else:
            logger.info("\n🤖 PHASE 3: AI scoring and cover letter generation...")
            qualified_jobs = []

            for job in new_jobs:
                try:
                    job = self.ai.process_job(job, self.config.min_score_to_apply)
                    self.stats["jobs_scored"] += 1

                    if job.score >= self.config.min_score_to_apply:
                        qualified_jobs.append(job)

                except Exception as e:
                    logger.error(f"AI processing error for {job.title}: {e}")
                    self.stats["errors"] += 1

            logger.info(f"✅ {len(qualified_jobs)} jobs qualified (score ≥ {self.config.min_score_to_apply})")

        # Save all new jobs to tracker
        self.tracker.save_jobs(new_jobs)

        # ── PHASE 4: APPLY ────────────────────────────────────
        if self.dry_run:
            easy = [j for j in qualified_jobs if j.easy_apply]
            manual = [j for j in qualified_jobs if not j.easy_apply]
            logger.info(f"\n🚫 DRY RUN: Skipping applications")
            logger.info(f"   🤖 Easy Apply (would auto-apply): {len(easy)}")
            logger.info(f"   ✍️  Manual apply (you do these):  {len(manual)}")
            if easy:
                logger.info("\n  Easy Apply jobs:")
                for j in easy:
                    logger.info(f"    [{j.score}/100] {j.title} @ {j.company} → {j.url}")
            if manual:
                logger.info("\n  Manual apply jobs:")
                for j in manual:
                    logger.info(f"    [{j.score}/100] {j.title} @ {j.company} → {j.url}")
            self._print_summary(qualified_jobs)
            await self._close_scrapers()
            return

        logger.info("\n📤 PHASE 4: Applying to jobs...")
        easy_apply_jobs = [j for j in qualified_jobs if j.easy_apply]
        manual_jobs = [j for j in qualified_jobs if not j.easy_apply]
        logger.info(f"   🤖 Easy Apply jobs: {len(easy_apply_jobs)}")
        logger.info(f"   🌐 External portal jobs: {len(manual_jobs)}")

        # ── 4A: LinkedIn Easy Apply ──────────────────────────
        linkedin_applier = LinkedInApplier(
            self.linkedin_scraper._page,
            cv_pdf_path="assets/Resume_DevOps_SRE.pdf",
        )

        for job in easy_apply_jobs:
            if applied_today >= self.config.max_daily_applications:
                logger.warning("Daily application limit reached")
                break

            try:
                success = await linkedin_applier.apply(job)
                if success:
                    self.stats["jobs_applied"] += 1
                    applied_today += 1
                    self.tracker.update_job_status(job.job_id, "applied", job.applied_date)
                await asyncio.sleep(3)  # Be respectful with rate limiting

            except Exception as e:
                logger.error(f"Easy Apply error for {job.title}: {e}")
                self.stats["errors"] += 1

        # ── 4B: External portal applications ─────────────────
        if manual_jobs and applied_today < self.config.max_daily_applications:
            logger.info(f"\n🌐 Applying to {len(manual_jobs)} external portal jobs...")
            external_applier = ExternalApplier(
                cv_pdf_path="assets/Resume_DevOps_SRE.pdf",
            )
            try:
                await external_applier.launch()

                for job in manual_jobs:
                    if applied_today >= self.config.max_daily_applications:
                        logger.warning("Daily application limit reached")
                        break

                    try:
                        success = await external_applier.apply(job)
                        if success:
                            self.stats["jobs_applied"] += 1
                            applied_today += 1
                            self.tracker.update_job_status(
                                job.job_id, "applied", job.applied_date
                            )
                        else:
                            # Form was opened but not submitted — log for manual follow-up
                            logger.info(
                                f"   ✍️  Manual follow-up needed: "
                                f"[{job.score}/100] {job.title} @ {job.company}"
                            )
                            logger.info(f"      → {job.apply_url or job.url}")
                        await asyncio.sleep(3)

                    except Exception as e:
                        logger.error(f"External apply error for {job.title}: {e}")
                        self.stats["errors"] += 1

            finally:
                await external_applier.close()
        elif manual_jobs:
            logger.info(f"\n📋 {len(manual_jobs)} external jobs skipped (daily limit reached)")
            for job in manual_jobs:
                logger.info(f"   [{job.score}/100] {job.title} @ {job.company} → {job.apply_url or job.url}")

        # ── DONE ─────────────────────────────────────────────
        self._print_summary(qualified_jobs)
        await self._close_scrapers()

    def _print_summary(self, qualified_jobs: List[JobPosting]):
        """Print a summary of the run."""
        logger.info("\n" + "=" * 60)
        logger.info("📊 RUN SUMMARY")
        logger.info(f"   Jobs found:   {self.stats['jobs_found']}")
        logger.info(f"   Jobs scored:  {self.stats['jobs_scored']}")
        logger.info(f"   Jobs applied: {self.stats['jobs_applied']}")
        logger.info(f"   Errors:       {self.stats['errors']}")
        logger.info("\n🏆 TOP 5 MATCHES:")
        top_jobs = sorted(qualified_jobs, key=lambda j: j.score, reverse=True)[:5]
        for job in top_jobs:
            logger.info(f"   [{job.score}/100] {job.title} @ {job.company} ({job.country})")
            logger.info(f"   → {job.url}")
        logger.info("=" * 60)

    async def _close_scrapers(self):
        if self.linkedin_scraper:
            await self.linkedin_scraper.close()
        if self.indeed_scraper:
            await self.indeed_scraper.close()
        if self.country_scraper:
            await self.country_scraper.close()


# ─────────────────────────────────────────────────────────────
# SCHEDULER (every Wednesday at 08:10 Mexico City time)
# ─────────────────────────────────────────────────────────────
def run_scheduled():
    """Run agent on a weekly schedule (Wednesdays at 08:10 MX)."""
    try:
        from apscheduler.schedulers.blocking import BlockingScheduler
    except ImportError:
        logger.error("APScheduler not installed. Run: pip install apscheduler")
        return

    scheduler = BlockingScheduler(timezone="America/Mexico_City")

    @scheduler.scheduled_job("cron", day_of_week="wed", hour=10, minute=15)
    def scheduled_run():
        logger.info("⏰ Scheduled run triggered")
        agent = JobHunterAgent()
        asyncio.run(agent.run())

    logger.info("⏰ Scheduler started — agent will run every Wednesday at 10:15 Mexico City time")
    scheduler.start()


# ─────────────────────────────────────────────────────────────
# ENTRY POINTS (used by Poetry scripts and __main__)
# ─────────────────────────────────────────────────────────────
def main():
    """Poetry entrypoint: poetry run job-hunter"""
    parser = argparse.ArgumentParser(description="Job Hunter Agent — DevOps/SRE International Search")
    parser.add_argument("--dry-run",  action="store_true", help="Scrape and score, but don't apply")
    parser.add_argument("--no-ai",    action="store_true", help="Skip AI scoring (no Anthropic API calls)")
    parser.add_argument("--schedule", action="store_true", help="Run on daily schedule")
    parser.add_argument("--country",  type=str, default=None, help="Filter to specific country")
    parser.add_argument("--sync",     action="store_true", help="Only sync pending local cache to Google Sheets (no scraping)")
    args = parser.parse_args()

    if args.sync:
        _sync_pending()
    elif args.schedule:
        run_scheduled()
    else:
        agent = JobHunterAgent(
            dry_run=args.dry_run,
            country_filter=args.country,
            no_ai=args.no_ai,
        )
        asyncio.run(agent.run())


def _sync_pending():
    """Sync any pending local cache entries to Google Sheets without scraping."""
    logger.info("🔄 Sync-only mode: uploading pending local cache to Google Sheets...")
    if GOOGLE_SHEET_ID and GOOGLE_SHEETS_CREDENTIALS:
        tracker = SheetsTracker(GOOGLE_SHEETS_CREDENTIALS, GOOGLE_SHEET_ID)
        pending_before = tracker.cache.pending_count()
        if pending_before == 0:
            logger.info("✅ No pending jobs in local cache. Nothing to sync.")
            return
        logger.info(f"   Found {pending_before} pending jobs in local cache")
        tracker.connect()  # connect() automatically syncs pending
        pending_after = tracker.cache.pending_count()
        logger.info(f"✅ Sync complete. Remaining pending: {pending_after}")
    else:
        logger.error("Google Sheets not configured. Set GOOGLE_SHEET_ID and GOOGLE_SHEETS_CREDENTIALS.")


def main_dry_run():
    """Poetry entrypoint: poetry run job-hunter-dry"""
    agent = JobHunterAgent(dry_run=True)
    asyncio.run(agent.run())


if __name__ == "__main__":
    main()