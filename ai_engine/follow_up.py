"""
Job Hunter Agent - Follow-up Generator
Generates short follow-up messages for applications without response after 5-7 days.
"""

import logging
from datetime import datetime, timedelta
from typing import List

import anthropic

from config.cv_data import CV_DATA

logger = logging.getLogger(__name__)


class FollowUpGenerator:
    """Generates follow-up messages for stale applications."""

    def __init__(self, api_key: str):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = "claude-sonnet-4-20250514"

    def get_stale_applications(self, tracker, min_days: int = 5, max_days: int = 14) -> List[dict]:
        """
        Query tracker for applications that were sent 5-14 days ago
        and still have status='applied' (no response).
        """
        if not hasattr(tracker, 'get_jobs_by_status'):
            logger.debug("Tracker doesn't support get_jobs_by_status, skipping follow-ups")
            return []

        applied_jobs = tracker.get_jobs_by_status("applied")
        now = datetime.now()
        stale = []

        for job in applied_jobs:
            applied_date = job.get("applied_date")
            if not applied_date:
                continue
            if isinstance(applied_date, str):
                try:
                    applied_date = datetime.fromisoformat(applied_date)
                except ValueError:
                    continue

            days_since = (now - applied_date).days
            if min_days <= days_since <= max_days:
                job["days_since_applied"] = days_since
                stale.append(job)

        return stale

    def generate_follow_up(self, job: dict) -> str:
        """Generate a short, professional follow-up message for a stale application."""
        prompt = f"""Write a very short follow-up message (3-4 sentences max) for a job application.

CONTEXT:
- Candidate: {CV_DATA['name']}, {CV_DATA['title']}
- Applied to: {job.get('title', 'DevOps role')} at {job.get('company', 'the company')}
- Days since application: {job.get('days_since_applied', 7)}
- Original application included a tailored cover letter and resume

REQUIREMENTS:
- Be brief and respectful of their time
- Reaffirm interest in the specific role
- Mention one concrete value-add (pick from: 9+ years DevOps/SRE, Oracle cloud migrations, 35% CI/CD improvement)
- End with a soft call to action (happy to discuss further, available for a call)
- DO NOT be pushy or desperate
- Sign off as {CV_DATA['name']}

Write ONLY the message body (no subject line).
"""
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=300,
                messages=[{"role": "user", "content": prompt}]
            )
            message = response.content[0].text.strip()
            logger.info(f"Follow-up generated for {job.get('title')} @ {job.get('company')}")
            return message
        except Exception as e:
            logger.error(f"Error generating follow-up: {e}")
            return ""

    def process_follow_ups(self, tracker) -> List[dict]:
        """
        Find stale applications and generate follow-up messages.
        Returns list of jobs with their follow-up messages.
        """
        stale = self.get_stale_applications(tracker)
        if not stale:
            logger.info("No stale applications needing follow-up")
            return []

        logger.info(f"Found {len(stale)} applications needing follow-up")
        results = []

        for job in stale[:5]:  # Limit to 5 follow-ups per run
            message = self.generate_follow_up(job)
            if message:
                results.append({
                    "job": job,
                    "follow_up_message": message,
                })

        return results
