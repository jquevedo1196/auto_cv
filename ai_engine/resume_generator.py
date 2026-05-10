"""
Job Hunter Agent - Resume Generator
Generates tailored PDF resumes per job using Claude Sonnet + Jinja2 + WeasyPrint.
"""

import json
import logging
import re
from pathlib import Path
from typing import Optional

import anthropic
from jinja2 import Environment, FileSystemLoader

from config.cv_data import CV_DATA
from scrapers.base_scraper import JobPosting

logger = logging.getLogger(__name__)

ASSETS_DIR = Path(__file__).parent.parent / "assets"
GENERATED_DIR = ASSETS_DIR / "generated"
TEMPLATE_DIR = ASSETS_DIR


class ResumeGenerator:
    """Generates job-tailored PDF resumes using AI content selection + HTML/PDF rendering."""

    def __init__(self, api_key: str):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = "claude-sonnet-4-20250514"
        self.jinja_env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)))
        GENERATED_DIR.mkdir(parents=True, exist_ok=True)

    def generate_tailored_resume(self, job: JobPosting) -> Optional[Path]:
        """
        Generate a tailored PDF resume for a specific job.
        Returns the path to the generated PDF, or None on failure.
        """
        tailored_content = self._get_tailored_content(job)
        if not tailored_content:
            return None

        html = self._render_html(tailored_content, job)
        pdf_path = self._html_to_pdf(html, job.job_id)
        return pdf_path

    def _get_tailored_content(self, job: JobPosting) -> Optional[dict]:
        """Ask Claude to select and reorder CV content for this specific job."""
        all_bullets = []
        for exp in CV_DATA["experience"]:
            for bullet in exp["bullets"]:
                all_bullets.append(f"[{exp['company']}] {bullet}")

        prompt = f"""You are an expert resume writer optimizing a resume for ATS systems and recruiters.

TARGET JOB:
- Title: {job.title}
- Company: {job.company}
- Location: {job.location}, {job.country}
- Description: {job.description[:2000] if job.description else 'DevOps/SRE role'}

CANDIDATE DATA:
- Name: {CV_DATA['name']}
- Current Title: {CV_DATA['title']}
- All skills: {json.dumps(CV_DATA['skills'])}
- All experience bullets (with company tags):
{chr(10).join(all_bullets)}

YOUR TASK:
1. Write a 2-3 sentence professional summary tailored to THIS specific job (mention key matching skills)
2. For each job in the candidate's experience, select the 2-4 most relevant bullets that match the target job's requirements. Reword them slightly to incorporate keywords from the job description while keeping them truthful.
3. Select the top 8-10 skills most relevant to this job, ordered by relevance
4. Identify 3-5 keywords from the job description that should appear in the resume

Respond with ONLY a JSON object:
{{
    "summary": "tailored 2-3 sentence summary",
    "experience": [
        {{
            "title": "job title",
            "company": "company name",
            "start": "start date",
            "end": "end date",
            "bullets": ["selected and optimized bullet 1", "bullet 2", ...]
        }}
    ],
    "skills": ["skill1", "skill2", ...],
    "keywords_incorporated": ["keyword1", "keyword2", ...]
}}
"""
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}]
            )
            text = response.content[0].text.strip()
            text = re.sub(r"```json|```", "", text).strip()
            data = json.loads(text)
            logger.info(
                f"Resume tailored for {job.title} @ {job.company} "
                f"(keywords: {', '.join(data.get('keywords_incorporated', []))})"
            )
            return data
        except Exception as e:
            logger.error(f"Error tailoring resume content: {e}")
            return None

    def _render_html(self, content: dict, job: JobPosting) -> str:
        """Render tailored content into an ATS-friendly HTML resume."""
        template = self.jinja_env.get_template("resume_template.html")
        return template.render(
            name=CV_DATA["name"],
            email=CV_DATA["email"],
            phone=CV_DATA["phone"],
            location=CV_DATA["location"],
            languages=CV_DATA["languages"],
            summary=content["summary"],
            skills=content["skills"],
            experience=content["experience"],
            education=CV_DATA["education"],
            certifications=CV_DATA["skills"].get("certifications", []),
        )

    def _html_to_pdf(self, html: str, job_id: str) -> Optional[Path]:
        """Convert HTML to PDF using WeasyPrint."""
        try:
            from weasyprint import HTML
            pdf_path = GENERATED_DIR / f"{job_id}_resume.pdf"
            HTML(string=html).write_pdf(str(pdf_path))
            logger.info(f"Resume PDF generated: {pdf_path.name}")
            return pdf_path
        except ImportError:
            logger.error("WeasyPrint not installed. Run: poetry add weasyprint")
            html_path = GENERATED_DIR / f"{job_id}_resume.html"
            html_path.write_text(html)
            logger.info(f"Saved HTML fallback: {html_path.name}")
            return None
        except Exception as e:
            logger.error(f"PDF generation error: {e}")
            return None
