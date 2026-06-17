"""
Job Hunter Agent - AI Engine
Uses Claude API to:
1. Score job relevance (0-100) against Jesús's profile
2. Generate personalized cover letters for each job
"""

import json
import logging
import re
from typing import Tuple

import anthropic

from config.cv_data import CV_DATA
from scrapers.base_scraper import JobPosting

logger = logging.getLogger(__name__)


class AIEngine:
    """Handles all AI-powered operations using Claude."""

    def __init__(self, api_key: str):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.scoring_model = "claude-haiku-4-5-20251001"
        self.cover_letter_model = "claude-sonnet-4-20250514"

    # ─────────────────────────────────────────────────────────
    # 1. SCORE JOB RELEVANCE
    # ─────────────────────────────────────────────────────────
    def score_job(self, job: JobPosting) -> int:
        """
        Score a job's relevance to Jesús's profile on a 0-100 scale.
        Returns integer score.
        """
        prompt = f"""You are a recruiter evaluating a job opportunity for a candidate.

CANDIDATE PROFILE:
- Name: {CV_DATA['name']}
- Current Role: {CV_DATA['title']} at Oracle
- Years of Experience: 9+
- Top Skills: {', '.join(CV_DATA['skills']['devops_sre'][:6])}
- Cloud: {', '.join(CV_DATA['skills']['cloud'])}
- Certifications: {', '.join(CV_DATA['skills']['certifications'])}
- Education: {CV_DATA['education'][1]['degree']} + Master's AI in progress
- Open to: Full relocation to {', '.join(CV_DATA['target_countries'])}

JOB TO EVALUATE:
- Title: {job.title}
- Company: {job.company}
- Location: {job.location}, {job.country}
- Description: {job.description[:1500] if job.description else 'No description available'}

Score this job's fit for the candidate on a scale from 0 to 100.
Consider: title match, required skills overlap, seniority alignment, company type.

VISA & SPONSORSHIP SCORING RULES (candidate needs work authorization outside Mexico):
- If the description says "must be authorized to work", "no visa sponsorship", "US citizens only", or similar → SUBTRACT 30 points
- If the company appears to be a small startup (<50 employees based on description) → SUBTRACT 15 points (unlikely to sponsor)
- If the job mentions "relocation assistance", "visa sponsorship available", or "relocation package" → ADD 15 points
- If the company is a large well-known employer (>500 employees, FAANG, major banks, large consultancies) → ADD 10 points

Respond with ONLY a JSON object like this:
{{"score": 85, "reason": "Strong AWS/K8s match, senior role, fintech background aligns"}}
"""
        try:
            response = self.client.messages.create(
                model=self.scoring_model,
                max_tokens=200,
                messages=[{"role": "user", "content": prompt}]
            )
            text = response.content[0].text.strip()
            # Parse JSON response
            text = re.sub(r"```json|```", "", text).strip()
            data = json.loads(text)
            score = int(data.get("score", 50))
            logger.info(f"Job scored {score}/100: {job.title} @ {job.company} — {data.get('reason', '')}")
            return max(0, min(100, score))
        except Exception as e:
            logger.error(f"Error scoring job: {e}")
            return 50  # default neutral score

    # ─────────────────────────────────────────────────────────
    # 2. GENERATE COVER LETTER
    # ─────────────────────────────────────────────────────────
    def generate_cover_letter(self, job: JobPosting, company_context: str = "") -> str:
        """
        Generate a personalized cover letter for a specific job.
        Tailored to the country's culture and the job's requirements.
        """
        # Country-specific tone guidance
        country_tone = {
            "Canada":         "warm, direct, and results-oriented. Mention openness to relocation.",
            "USA":            "confident, achievement-driven, and data-backed. Lead with impact metrics.",
            "Mexico":         "professional and warm. Highlight leadership and technical depth.",
            "Germany":        "formal, precise, and achievement-focused. Germans appreciate structure.",
            "Spain":          "warm, professional, and personable. Spaniards value human connection and team culture. Mention enthusiasm for the tech ecosystem.",
            "Portugal":       "friendly, professional, and modern. Portuguese tech culture is growing fast and values innovation and adaptability.",
            "Switzerland":    "precise, professional, and quality-focused. Swiss value reliability and engineering excellence.",
            "Netherlands":    "direct, pragmatic, and collaborative. Dutch value honesty and efficiency.",
            "United Kingdom": "professional yet personable. British tone is polished but not overly formal.",
            "Ireland":        "friendly, professional, and genuine. Irish tech culture is collaborative and down-to-earth.",
            "Sweden":         "professional but informal. Emphasize work-life balance values and innovation.",
            "Poland":         "professional, concise, and modern. Tech-forward tone.",
            "Latvia":         "professional and straightforward. Latvian tech culture values efficiency and technical competence. Be concise and results-focused.",
            "Australia":      "friendly, straightforward, and results-oriented. Aussies value authenticity and practical skills.",
            "New Zealand":    "friendly, collaborative, and straightforward. Kiwis value authenticity.",
            "Singapore":      "professional, concise, and globally minded. Emphasize scalability and multi-cloud experience.",
            "Saudi Arabia":   "professional and respectful. Emphasize large-scale infrastructure experience, reliability, and commitment to long-term impact. Mention enthusiasm for the country's tech transformation.",
        }.get(job.country, "professional and engaging")

        # Build experience summary
        recent_exp = CV_DATA["experience"][:3]
        exp_bullets = "\n".join([
            f"- {e['title']} at {e['company']} ({e['start']} – {e['end']})"
            for e in recent_exp
        ])

        achievements = "\n".join([f"• {a}" for a in CV_DATA["key_achievements"]])

        prompt = f"""Write a professional cover letter for this job application.

CANDIDATE:
- Name: {CV_DATA['name']}
- Email: {CV_DATA['email']}
- Current Role: {CV_DATA['title']} at Oracle (working on Oracle Cloud Infrastructure migrations)
- Experience: 9+ years in DevOps/SRE
- Location: Mexico City, open to full relocation to {job.country}

KEY ACHIEVEMENTS:
{achievements}

RECENT EXPERIENCE:
{exp_bullets}

TOP SKILLS: {', '.join(CV_DATA['skills']['devops_sre'][:8])}
CLOUD: {', '.join(CV_DATA['skills']['cloud'])}

JOB DETAILS:
- Title: {job.title}
- Company: {job.company}
- Location: {job.location}, {job.country}
- Description: {job.description[:2000] if job.description else 'DevOps/SRE role'}

{"COMPANY CONTEXT (use this to personalize — reference what the company does):" + chr(10) + company_context + chr(10) if company_context else ""}TONE GUIDANCE:
Write the letter in a {country_tone} tone.

REQUIREMENTS:
- 3-4 paragraphs, max 350 words
- Opening: express specific interest in THIS company and role
- Middle: connect 2-3 specific achievements to the job requirements
- Mention willingness to relocate to {job.country}
- Closing: clear call to action
- DO NOT use generic phrases like "I am writing to apply"
- Sign off as {CV_DATA['name']}

Write ONLY the cover letter body (no subject line, no metadata).
"""
        try:
            response = self.client.messages.create(
                model=self.cover_letter_model,
                max_tokens=800,
                messages=[{"role": "user", "content": prompt}]
            )
            letter = response.content[0].text.strip()
            logger.info(f"Cover letter generated for {job.title} @ {job.company} ({job.country})")
            return letter
        except Exception as e:
            logger.error(f"Error generating cover letter: {e}")
            return ""

    # ─────────────────────────────────────────────────────────
    # 3. PROCESS JOB (score + cover letter if score is high)
    # ─────────────────────────────────────────────────────────
    def process_job(self, job: JobPosting, min_score: int = 70, company_context: str = "") -> JobPosting:
        """Score a job and generate cover letter if score meets threshold."""
        job.score = self.score_job(job)
        job.status = "scored"

        if job.score >= min_score:
            logger.info(f"Score {job.score} >= {min_score}, generating cover letter...")
            job.cover_letter = self.generate_cover_letter(job, company_context)
        else:
            logger.info(f"Score {job.score} < {min_score}, skipping cover letter")

        return job
