"""
Job Hunter Agent - Form Filler / Applier
Automates LinkedIn Easy Apply using Playwright.
For non-Easy Apply jobs, opens the browser and pre-fills where possible.
"""

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from playwright.async_api import Page

from scrapers.base_scraper import JobPosting
from config.cv_data import CV_DATA

logger = logging.getLogger(__name__)

# Path to your CV PDF
CV_PDF_PATH = Path(__file__).parent.parent / "assets" / "Resume_DevOps_SRE.pdf"

# Standard answers for common Easy Apply questions
EASY_APPLY_ANSWERS = {
    # Work authorization
    "authorized to work":           "Yes",
    "require sponsorship":          "Yes",  # Jesús needs sponsorship for most countries
    "visa sponsorship":             "Yes",
    "work permit":                  "No, I will require visa/work permit sponsorship",

    # Experience
    "years of experience":          "9",
    "years.*devops":                "6",
    "years.*kubernetes":            "5",
    "years.*aws":                   "7",
    "years.*terraform":             "5",
    "years.*python":                "7",

    # Location
    "willing to relocate":          "Yes",
    "open to relocation":           "Yes",
    "remote.*hybrid.*onsite":       "Hybrid",

    # General
    "salary.*expectation":          "Negotiable / Market rate",
    "notice period":                "4 weeks",
    "earliest start":               "Within 4-6 weeks",
    "linkedin profile":             "https://www.linkedin.com/in/jenriqueqt",
    "github":                       "https://github.com/jenriqueqt",

    # Phone
    "phone":                        CV_DATA["phone"],
    "mobile":                       CV_DATA["phone"],
}


class FormFiller:
    """Handles job application form filling."""

    def __init__(self, page: Page):
        self.page = page

    async def apply_easy_apply(self, job: JobPosting) -> bool:
        """
        Attempt to complete LinkedIn Easy Apply for a job.
        Returns True if application was submitted successfully.
        """
        logger.info(f"Starting Easy Apply for: {job.title} @ {job.company}")

        try:
            # Navigate to job page
            await self.page.goto(job.url)
            await self.page.wait_for_load_state("networkidle")
            await asyncio.sleep(2)

            # Click Easy Apply button
            easy_apply_btn = await self.page.query_selector(
                "button.jobs-apply-button[aria-label*='Easy Apply']"
            )
            if not easy_apply_btn:
                logger.warning("Easy Apply button not found")
                return False

            await easy_apply_btn.click()
            await asyncio.sleep(2)

            # Handle multi-step form
            max_steps = 10
            step = 0

            while step < max_steps:
                step += 1
                logger.debug(f"Processing form step {step}")

                # Fill any text/textarea fields
                await self._fill_text_fields()

                # Handle file upload (CV)
                await self._upload_cv()

                # Handle dropdowns
                await self._fill_dropdowns()

                # Handle radio buttons
                await self._fill_radio_buttons()

                # Fill cover letter if there's a textarea asking for it
                if job.cover_letter:
                    await self._fill_cover_letter(job.cover_letter)

                # Check for Next / Submit button
                next_btn = await self.page.query_selector(
                    "button[aria-label='Continue to next step'], "
                    "button[aria-label='Review your application'], "
                    "button[aria-label='Submit application']"
                )

                if not next_btn:
                    logger.warning("No navigation button found, stopping")
                    break

                btn_label = await next_btn.get_attribute("aria-label") or ""

                if "Submit application" in btn_label:
                    await next_btn.click()
                    await asyncio.sleep(2)
                    logger.info(f"✅ Application SUBMITTED: {job.title} @ {job.company}")
                    job.applied = True
                    job.applied_date = datetime.now()
                    job.status = "applied"
                    return True
                else:
                    await next_btn.click()
                    await asyncio.sleep(1.5)

            logger.warning(f"Could not complete Easy Apply after {max_steps} steps")
            return False

        except Exception as e:
            logger.error(f"Easy Apply error for {job.url}: {e}")
            return False

    async def _fill_text_fields(self):
        """Fill visible text input fields based on label matching."""
        inputs = await self.page.query_selector_all(
            "input[type='text']:visible, input[type='tel']:visible, "
            "input[type='email']:visible, input[type='number']:visible"
        )

        for inp in inputs:
            try:
                # Get associated label
                label = await self._get_label_for_input(inp)
                if not label:
                    continue

                # Find matching answer
                answer = self._find_answer(label)
                if answer:
                    current = await inp.input_value()
                    if not current:  # Don't overwrite if already filled
                        await inp.fill(answer)
                        logger.debug(f"Filled '{label}' → '{answer}'")
            except Exception:
                pass

    async def _fill_cover_letter(self, cover_letter: str):
        """Fill cover letter textarea if present."""
        textareas = await self.page.query_selector_all("textarea:visible")
        for ta in textareas:
            try:
                label = await self._get_label_for_input(ta)
                label_lower = (label or "").lower()
                if any(kw in label_lower for kw in ["cover letter", "message", "tell us", "additional"]):
                    current = await ta.input_value()
                    if not current:
                        await ta.fill(cover_letter[:2000])  # most forms limit chars
                        logger.debug("Filled cover letter textarea")
            except Exception:
                pass

    async def _upload_cv(self):
        """Upload CV PDF if a file input is present."""
        if not CV_PDF_PATH.exists():
            logger.warning(f"CV file not found at {CV_PDF_PATH}, skipping upload")
            return

        file_inputs = await self.page.query_selector_all("input[type='file']:visible")
        for file_input in file_inputs:
            try:
                await file_input.set_input_files(str(CV_PDF_PATH))
                await asyncio.sleep(1)
                logger.debug("CV uploaded")
            except Exception as e:
                logger.debug(f"File upload error: {e}")

    async def _fill_dropdowns(self):
        """Handle select dropdowns."""
        selects = await self.page.query_selector_all("select:visible")
        for select in selects:
            try:
                label = await self._get_label_for_input(select)
                answer = self._find_answer(label or "")
                if answer:
                    await select.select_option(label=answer)
            except Exception:
                pass

    async def _fill_radio_buttons(self):
        """Handle yes/no radio button questions."""
        # Look for fieldsets with radio buttons
        fieldsets = await self.page.query_selector_all("fieldset:visible")
        for fieldset in fieldsets:
            try:
                legend = await fieldset.query_selector("legend")
                question = (await legend.inner_text()).strip() if legend else ""
                answer = self._find_answer(question)

                if answer:
                    radios = await fieldset.query_selector_all(
                        f"input[type='radio'][value='{answer}']"
                    )
                    if radios:
                        await radios[0].click()
            except Exception:
                pass

    async def _get_label_for_input(self, element) -> Optional[str]:
        """Get the label text associated with a form element."""
        try:
            # Try aria-label
            aria = await element.get_attribute("aria-label")
            if aria:
                return aria

            # Try placeholder
            placeholder = await element.get_attribute("placeholder")
            if placeholder:
                return placeholder

            # Try associated <label>
            element_id = await element.get_attribute("id")
            if element_id:
                label_el = await self.page.query_selector(f"label[for='{element_id}']")
                if label_el:
                    return (await label_el.inner_text()).strip()
        except Exception:
            pass
        return None

    def _find_answer(self, label: str) -> Optional[str]:
        """Find the best answer for a form field based on its label."""
        label_lower = label.lower()
        for pattern, answer in EASY_APPLY_ANSWERS.items():
            import re
            if re.search(pattern, label_lower):
                return answer
        return None
