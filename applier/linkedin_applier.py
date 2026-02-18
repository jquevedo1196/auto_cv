"""
Job Hunter Agent - LinkedIn Applier
Automates the full LinkedIn Easy Apply flow using Playwright.

Handles:
  - Multi-step Easy Apply modal (up to 10 steps)
  - Text / number / email inputs
  - Dropdowns (select elements)
  - Radio button questions (Yes/No, etc.)
  - Checkbox questions
  - File uploads (CV PDF)
  - Cover letter textarea
  - Review & submit step

Usage:
    applier = LinkedInApplier(page, cv_pdf_path="assets/Resume_DevOps_SRE.pdf")
    success = await applier.apply(job)
"""

import asyncio
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from playwright.async_api import Page, ElementHandle

from scrapers.base_scraper import JobPosting
from config.cv_data import CV_DATA

logger = logging.getLogger(__name__)

# ── Pre-configured answers for common Easy Apply questions ──────────────────
# Keys are regex patterns matched against the question/label text (lowercase).
# Values are the answer string to fill in or select.
EASY_APPLY_ANSWERS: dict[str, str] = {
    # Work authorization
    r"authorized to work":                  "Yes",
    r"legally authorized":                  "Yes",
    r"require.*sponsor":                    "Yes",
    r"visa.*sponsor":                       "Yes",
    r"work.*permit":                        "Yes, I will require sponsorship",
    r"citizenship":                         "Mexican",
    r"nationality":                         "Mexican",

    # Relocation
    r"willing to relocate":                 "Yes",
    r"open to relocation":                  "Yes",
    r"relocate":                            "Yes",

    # Work mode
    r"remote.*hybrid.*on.?site":            "Hybrid",
    r"work.*arrangement":                   "Hybrid",
    r"on.?site.*remote":                    "Hybrid",

    # Experience (years)
    r"years.*experience.*devops":           "9",
    r"years.*experience.*cloud":            "7",
    r"years.*experience.*kubernetes":       "5",
    r"years.*experience.*aws":              "7",
    r"years.*experience.*terraform":        "5",
    r"years.*experience.*python":           "7",
    r"years.*experience.*ci.?cd":          "9",
    r"years.*total.*experience":            "9",
    r"years of experience":                 "9",
    r"how many years":                      "9",

    # Contact
    r"phone":                               CV_DATA["phone"],
    r"mobile":                              CV_DATA["phone"],

    # LinkedIn / profiles
    r"linkedin.*url|linkedin.*profile":     "https://www.linkedin.com/in/jenriqueqt",
    r"github":                              "https://github.com/jenriqueqt",
    r"portfolio|website":                   "https://www.linkedin.com/in/jenriqueqt",

    # Salary
    r"salary.*expect|desired.*salary|compensation": "Negotiable / Market rate",
    r"annual.*salary":                      "120000",

    # Availability
    r"notice.*period":                      "4 weeks",
    r"start.*date|earliest.*start":        "Within 4-6 weeks",
    r"available.*start":                    "Within 4-6 weeks",

    # Education
    r"highest.*education|degree":           "Bachelor's Degree",

    # Gender / diversity (voluntary — can leave blank but some forms require)
    r"gender":                              "Prefer not to say",
    r"ethnicity|race":                      "Prefer not to say",
    r"veteran":                             "No",
    r"disability":                          "No",

    # Misc
    r"agree.*terms|terms.*condition":       "Yes",
    r"background.*check":                   "Yes",
    r"drug.*test":                          "Yes",
    r"18 years|over 18":                    "Yes",
}


class LinkedInApplier:
    """Automates LinkedIn Easy Apply for a given JobPosting."""

    def __init__(self, page: Page, cv_pdf_path: str = "assets/Resume_DevOps_SRE.pdf"):
        self.page = page
        self.cv_pdf_path = Path(cv_pdf_path)

    # ── Public API ───────────────────────────────────────────

    async def apply(self, job: JobPosting) -> bool:
        """
        Attempt the full Easy Apply flow for a job.
        Returns True if application was submitted, False otherwise.
        """
        logger.info(f"Starting Easy Apply → {job.title} @ {job.company} ({job.country})")

        try:
            await self.page.goto(job.url, wait_until="domcontentloaded", timeout=30_000)
            await asyncio.sleep(3)

            # Click the Easy Apply button to open the modal
            if not await self._open_modal():
                logger.warning("Easy Apply button not found or could not be clicked")
                return False

            # Step through the modal form
            submitted = await self._process_modal(job)

            if submitted:
                job.applied = True
                job.applied_date = datetime.now()
                job.status = "applied"
                logger.info(f"✅ SUBMITTED: {job.title} @ {job.company}")
            else:
                logger.warning(f"Could not complete Easy Apply for {job.title}")

            return submitted

        except Exception as e:
            logger.error(f"Easy Apply error ({job.url}): {e}", exc_info=True)
            return False

    # ── Modal navigation ─────────────────────────────────────

    async def _open_modal(self) -> bool:
        """Click the Easy Apply button and wait for the modal to appear."""
        # Step 1 — wait for the button to appear in the DOM (LinkedIn SPA renders it late)
        try:
            await self.page.wait_for_selector(
                "button[aria-label*='Easy Apply'], "
                "button[aria-label*='Solicitud sencilla'], "
                ".jobs-apply-button",
                timeout=5_000,
            )
        except Exception:
            pass  # Proceed anyway; JS fallback below will handle it

        # Step 2 — CSS selectors with visibility check
        css_selectors = [
            "button[aria-label*='Easy Apply']",
            "button[aria-label*='Solicitud sencilla']",
            ".jobs-apply-button",
            ".jobs-s-apply button",
        ]
        for sel in css_selectors:
            try:
                btn = await self.page.query_selector(sel)
                if btn and await btn.is_visible():
                    await btn.click()
                    await asyncio.sleep(2)
                    modal = await self.page.query_selector(
                        "[data-test-modal], .jobs-easy-apply-modal"
                    )
                    if modal:
                        return True
            except Exception:
                continue

        # Step 3 — JS fallback: find button by textContent regardless of language/aria-label format
        try:
            clicked = await self.page.evaluate("""
                () => {
                    const btn = Array.from(document.querySelectorAll('button')).find(b => {
                        const t = b.textContent.trim();
                        return t.includes('Easy Apply') || t.includes('Solicitud sencilla');
                    });
                    if (btn) { btn.click(); return true; }
                    return false;
                }
            """)
            if clicked:
                await asyncio.sleep(2)
                modal = await self.page.query_selector(
                    "[data-test-modal], .jobs-easy-apply-modal"
                )
                return modal is not None
        except Exception:
            pass

        return False

    async def _process_modal(self, job: JobPosting) -> bool:
        """Iterate through modal steps until Submit or give up."""
        max_steps = 12

        for step in range(1, max_steps + 1):
            logger.debug(f"Modal step {step}")

            # Fill all fields on the current step
            await self._fill_step(job)
            await asyncio.sleep(0.5)

            # Determine the primary action button
            action = await self._get_action_button()
            if action is None:
                logger.warning("No action button found — aborting")
                return False

            label = (await action.get_attribute("aria-label") or "").lower()

            if "submit" in label:
                await action.click()
                await asyncio.sleep(2)
                # Confirm success (LinkedIn shows a confirmation screen)
                return await self._confirm_submission()

            elif any(w in label for w in ["next", "continue", "review"]):
                await action.click()
                await asyncio.sleep(1.5)

            else:
                # Unknown button — try clicking it anyway
                logger.debug(f"Unknown button label: '{label}', clicking anyway")
                await action.click()
                await asyncio.sleep(1.5)

        logger.warning(f"Reached max steps ({max_steps}) without submitting")
        return False

    async def _confirm_submission(self) -> bool:
        """Check if LinkedIn's post-submission confirmation is visible."""
        confirmation_selectors = [
            "[data-test-modal][aria-label*='Application submitted']",
            ".artdeco-modal__header h2[aria-label*='submitted']",
            "h3:has-text('Application submitted')",
            ".jobs-easy-apply-modal [aria-label*='submitted']",
        ]
        for sel in confirmation_selectors:
            try:
                el = await self.page.query_selector(sel)
                if el:
                    return True
            except Exception:
                pass

        # Fallback: modal disappeared = likely submitted
        modal = await self.page.query_selector(
            "[data-test-modal], .jobs-easy-apply-modal"
        )
        return modal is None

    async def _get_action_button(self) -> Optional[ElementHandle]:
        """Return the primary action button on the current modal step."""
        # Priority: Submit > Review > Next > Continue
        priority_selectors = [
            "button[aria-label*='Submit application']",
            "button[aria-label*='Review your application']",
            "button[aria-label*='Continue to next step']",
            "button[aria-label*='Next']",
            ".jobs-easy-apply-modal footer button.artdeco-button--primary",
        ]
        for sel in priority_selectors:
            try:
                btn = await self.page.query_selector(sel)
                if btn and await btn.is_visible():
                    return btn
            except Exception:
                continue
        return None

    # ── Field filling ────────────────────────────────────────

    async def _fill_step(self, job: JobPosting) -> None:
        """Fill all visible form fields on the current modal step."""
        await self._fill_text_inputs()
        await self._fill_selects()
        await self._fill_radios()
        await self._fill_checkboxes()
        await self._upload_cv()
        if job.cover_letter:
            await self._fill_cover_letter(job.cover_letter)

    async def _fill_text_inputs(self) -> None:
        """Fill text, number, email, tel, and url inputs."""
        inputs = await self.page.query_selector_all(
            ".jobs-easy-apply-modal input[type='text']:visible, "
            ".jobs-easy-apply-modal input[type='number']:visible, "
            ".jobs-easy-apply-modal input[type='email']:visible, "
            ".jobs-easy-apply-modal input[type='tel']:visible, "
            ".jobs-easy-apply-modal input[type='url']:visible"
        )
        for inp in inputs:
            try:
                # Skip if already filled
                current = await inp.input_value()
                if current.strip():
                    continue

                label = await self._get_field_label(inp)
                answer = self._match_answer(label)
                if answer:
                    await inp.fill(answer)
                    logger.debug(f"Text filled: '{label}' → '{answer}'")
            except Exception as e:
                logger.debug(f"Text fill error: {e}")

    async def _fill_selects(self) -> None:
        """Handle <select> dropdowns."""
        selects = await self.page.query_selector_all(
            ".jobs-easy-apply-modal select:visible"
        )
        for sel_el in selects:
            try:
                label = await self._get_field_label(sel_el)
                answer = self._match_answer(label)
                if answer:
                    # Try exact label match first, then value, then partial
                    options = await sel_el.query_selector_all("option")
                    matched = False
                    for opt in options:
                        opt_text = (await opt.inner_text()).strip().lower()
                        if answer.lower() in opt_text or opt_text in answer.lower():
                            opt_val = await opt.get_attribute("value")
                            await sel_el.select_option(value=opt_val)
                            logger.debug(f"Select filled: '{label}' → '{answer}'")
                            matched = True
                            break
                    if not matched:
                        # Pick first non-empty option as fallback
                        for opt in options[1:]:
                            opt_val = await opt.get_attribute("value")
                            if opt_val and opt_val != "":
                                await sel_el.select_option(value=opt_val)
                                break
            except Exception as e:
                logger.debug(f"Select fill error: {e}")

    async def _fill_radios(self) -> None:
        """Handle radio button groups (Yes/No questions, etc.)."""
        fieldsets = await self.page.query_selector_all(
            ".jobs-easy-apply-modal fieldset:visible"
        )
        for fieldset in fieldsets:
            try:
                legend = await fieldset.query_selector("legend")
                question = (await legend.inner_text()).strip() if legend else ""
                answer = self._match_answer(question)
                if not answer:
                    continue

                # Find radio whose label matches the answer
                radios = await fieldset.query_selector_all("input[type='radio']")
                for radio in radios:
                    radio_id = await radio.get_attribute("id")
                    label_el = await self.page.query_selector(f"label[for='{radio_id}']")
                    label_text = (await label_el.inner_text()).strip() if label_el else ""
                    if answer.lower() in label_text.lower():
                        await radio.click()
                        logger.debug(f"Radio clicked: '{question}' → '{answer}'")
                        break
            except Exception as e:
                logger.debug(f"Radio fill error: {e}")

    async def _fill_checkboxes(self) -> None:
        """Check required checkboxes (e.g. terms agreement)."""
        checkboxes = await self.page.query_selector_all(
            ".jobs-easy-apply-modal input[type='checkbox']:visible"
        )
        for cb in checkboxes:
            try:
                checked = await cb.is_checked()
                if checked:
                    continue
                label = await self._get_field_label(cb)
                answer = self._match_answer(label)
                # Only auto-check if our answer map says "Yes" or "True"
                if answer and answer.lower() in ("yes", "true", "i agree"):
                    await cb.check()
                    logger.debug(f"Checkbox checked: '{label}'")
            except Exception as e:
                logger.debug(f"Checkbox error: {e}")

    async def _upload_cv(self) -> None:
        """Upload CV PDF to any visible file input."""
        if not self.cv_pdf_path.exists():
            logger.warning(f"CV not found at {self.cv_pdf_path}, skipping upload")
            return

        file_inputs = await self.page.query_selector_all(
            ".jobs-easy-apply-modal input[type='file']"
        )
        for inp in file_inputs:
            try:
                await inp.set_input_files(str(self.cv_pdf_path))
                await asyncio.sleep(1.5)  # wait for upload to process
                logger.debug("CV uploaded")
            except Exception as e:
                logger.debug(f"CV upload error: {e}")

    async def _fill_cover_letter(self, cover_letter: str) -> None:
        """Paste cover letter into cover letter textarea if present."""
        textareas = await self.page.query_selector_all(
            ".jobs-easy-apply-modal textarea:visible"
        )
        for ta in textareas:
            try:
                label = await self._get_field_label(ta)
                label_lower = (label or "").lower()
                is_cover = any(
                    kw in label_lower
                    for kw in ["cover letter", "message", "tell us", "additional info",
                               "why do you want", "why are you"]
                )
                if is_cover:
                    current = await ta.input_value()
                    if not current.strip():
                        # LinkedIn has a character limit; trim gracefully
                        await ta.fill(cover_letter[:2000])
                        logger.debug("Cover letter filled")
            except Exception as e:
                logger.debug(f"Cover letter fill error: {e}")

    # ── Label resolution ─────────────────────────────────────

    async def _get_field_label(self, element: ElementHandle) -> str:
        """
        Resolve the human-readable label for a form element.
        Tries (in order): aria-label → placeholder → associated <label> → parent text.
        """
        try:
            aria = await element.get_attribute("aria-label")
            if aria and aria.strip():
                return aria.strip()

            placeholder = await element.get_attribute("placeholder")
            if placeholder and placeholder.strip():
                return placeholder.strip()

            el_id = await element.get_attribute("id")
            if el_id:
                label_el = await self.page.query_selector(f"label[for='{el_id}']")
                if label_el:
                    text = (await label_el.inner_text()).strip()
                    if text:
                        return text

            # Walk up to the closest label-like parent
            parent = await element.query_selector("xpath=..")
            if parent:
                text = (await parent.inner_text()).strip()
                # Keep only the first line (label, not the full option list)
                return text.split("\n")[0].strip()

        except Exception:
            pass

        return ""

    # ── Answer matching ──────────────────────────────────────

    @staticmethod
    def _match_answer(label: str) -> Optional[str]:
        """Return the best-matching answer for a form field label."""
        label_lower = label.lower()
        for pattern, answer in EASY_APPLY_ANSWERS.items():
            if re.search(pattern, label_lower):
                return answer
        return None