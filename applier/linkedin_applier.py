"""
Job Hunter Agent - LinkedIn Applier
Automates the full LinkedIn Easy Apply flow using Playwright.

Handles:
  - Multi-step Easy Apply modal (up to 12 steps)
  - Text / number / email inputs
  - Dropdowns (select elements)
  - Radio button questions (Yes/No, etc.)
  - Checkbox questions
  - File uploads (CV PDF)
  - Cover letter textarea
  - Review & submit step
  - Screenshot-on-failure for debugging

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

# Directory where debug screenshots are saved on failure
DEBUG_DIR = Path("debug_screenshots")

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
            # LinkedIn SPA needs time to fully render job detail + Easy Apply button
            await asyncio.sleep(4)

            # Click the Easy Apply button to open the modal
            if not await self._open_modal():
                logger.warning("Easy Apply button not found or could not be clicked")
                await self._save_debug_screenshot(job, "no_button")
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
                await self._save_debug_screenshot(job, "incomplete")

            return submitted

        except Exception as e:
            logger.error(f"Easy Apply error ({job.url}): {e}", exc_info=True)
            await self._save_debug_screenshot(job, "error")
            return False

    # ── Modal navigation ─────────────────────────────────────

    async def _open_modal(self) -> bool:
        """Click the Easy Apply button and wait for the modal to appear."""
        # Strategy 1: Wait for any known Easy Apply button selector
        ea_wait_selector = ", ".join([
            "button[aria-label*='Easy Apply']",
            "button[aria-label*='Solicitud sencilla']",
            ".jobs-apply-button",
            ".jobs-s-apply button",
            # LinkedIn 2025+ classes
            ".jobs-apply-button--top-card",
            ".job-details-jobs-unified-top-card__content--two-pane button",
            ".artdeco-button--primary[aria-label*='pply']",
        ])
        try:
            await self.page.wait_for_selector(ea_wait_selector, timeout=8_000)
        except Exception:
            pass  # Proceed with fallback strategies

        # Strategy 2: CSS selectors with visibility check (broadened for 2025+ LinkedIn)
        css_selectors = [
            "button[aria-label*='Easy Apply']",
            "button[aria-label*='Solicitud sencilla']",
            ".jobs-apply-button",
            ".jobs-s-apply button",
            ".jobs-apply-button--top-card",
            ".artdeco-button--primary[aria-label*='pply']",
            # Broader: any primary button in the job detail top card
            ".job-details-jobs-unified-top-card__content button.artdeco-button--primary",
            ".jobs-unified-top-card button.artdeco-button--primary",
        ]
        for sel in css_selectors:
            try:
                btn = await self.page.query_selector(sel)
                if btn and await btn.is_visible():
                    btn_text = (await btn.inner_text()).strip().lower()
                    # Make sure it's actually an apply button, not some random primary button
                    if any(kw in btn_text for kw in ["apply", "solicitud", "postular"]):
                        await btn.click()
                        if await self._wait_for_modal():
                            return True
            except Exception:
                continue

        # Strategy 3: JS fallback — find button by textContent in any language
        try:
            clicked = await self.page.evaluate("""
                () => {
                    const keywords = ['Easy Apply', 'Solicitud sencilla', 'Postularme'];
                    for (const kw of keywords) {
                        const btns = Array.from(document.querySelectorAll('button, [role="button"]'));
                        const btn = btns.find(b => {
                            const t = (b.textContent || '').trim();
                            return t.includes(kw) && b.offsetParent !== null;
                        });
                        if (btn) { btn.click(); return kw; }
                    }
                    return null;
                }
            """)
            if clicked:
                logger.debug(f"JS fallback found button with '{clicked}'")
                if await self._wait_for_modal():
                    return True
        except Exception:
            pass

        # Strategy 4: Look for any visible button whose aria-label contains 'pply'
        # (handles "Apply", "Easy Apply", "Apply now", etc.)
        try:
            btns = await self.page.query_selector_all("button:visible, [role='button']:visible")
            for btn in btns:
                aria = (await btn.get_attribute("aria-label") or "").lower()
                text = (await btn.inner_text() or "").strip().lower()
                combined = f"{aria} {text}"
                if "pply" in combined and "applied" not in combined:
                    await btn.click()
                    if await self._wait_for_modal():
                        return True
        except Exception:
            pass

        return False

    async def _wait_for_modal(self, timeout: float = 4.0) -> bool:
        """Wait for the Easy Apply modal to appear after clicking the button."""
        modal_selectors = [
            "[data-test-modal]",
            ".jobs-easy-apply-modal",
            ".artdeco-modal[role='dialog']",
            ".jobs-easy-apply-content",
            # 2025+ LinkedIn modal
            "[aria-labelledby*='easy-apply']",
            ".artdeco-modal--layer-default",
        ]
        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
            for sel in modal_selectors:
                try:
                    modal = await self.page.query_selector(sel)
                    if modal and await modal.is_visible():
                        logger.debug(f"Modal detected via: {sel}")
                        return True
                except Exception:
                    continue
            await asyncio.sleep(0.3)
        return False

    async def _process_modal(self, job: JobPosting) -> bool:
        """Iterate through modal steps until Submit or give up."""
        max_steps = 12

        for step in range(1, max_steps + 1):
            logger.debug(f"Modal step {step}")

            # Fill all fields on the current step
            await self._fill_step(job)
            await asyncio.sleep(0.5)

            # Handle any validation errors — try to dismiss them
            await self._handle_errors()

            # Determine the primary action button
            action = await self._get_action_button()
            if action is None:
                logger.warning("No action button found — aborting")
                await self._save_debug_screenshot(job, f"step{step}_no_button")
                return False

            label = (await action.get_attribute("aria-label") or "").lower()
            text = (await action.inner_text() or "").strip().lower()
            combined = f"{label} {text}"

            if "submit" in combined or "enviar" in combined:
                await action.click()
                await asyncio.sleep(2)
                return await self._confirm_submission()

            elif "review" in combined or "revisar" in combined:
                await action.click()
                await asyncio.sleep(1.5)

            elif any(w in combined for w in ["next", "continue", "siguiente", "continuar"]):
                await action.click()
                await asyncio.sleep(1.5)

            else:
                # Unknown button — try clicking it anyway
                logger.debug(f"Unknown button: label='{label}' text='{text}', clicking anyway")
                await action.click()
                await asyncio.sleep(1.5)

        logger.warning(f"Reached max steps ({max_steps}) without submitting")
        return False

    async def _handle_errors(self) -> None:
        """Dismiss inline validation errors that block progress."""
        try:
            # LinkedIn shows inline errors in .artdeco-inline-feedback
            errors = await self.page.query_selector_all(
                ".artdeco-inline-feedback--error:visible, "
                ".fb-dash-form-element__error-field:visible"
            )
            if errors:
                error_texts = []
                for e in errors[:3]:
                    t = await e.inner_text()
                    error_texts.append(t.strip())
                logger.warning(f"Form validation errors: {error_texts}")
        except Exception:
            pass

    async def _confirm_submission(self) -> bool:
        """Check if LinkedIn's post-submission confirmation is visible."""
        await asyncio.sleep(1)

        # Check for confirmation indicators
        confirmation_checks = [
            # Confirmation text
            "h3:has-text('submitted')",
            "h3:has-text('Application submitted')",
            "h3:has-text('Solicitud enviada')",
            "[data-test-modal][aria-label*='submitted']",
            "[data-test-modal][aria-label*='enviada']",
            ".artdeco-modal__header h2:has-text('submitted')",
            # 2025+ confirmation
            ".jpac-modal-header h2",
            ".artdeco-modal h2:has-text('application')",
        ]
        for sel in confirmation_checks:
            try:
                el = await self.page.query_selector(sel)
                if el and await el.is_visible():
                    return True
            except Exception:
                pass

        # JS text check — look for "submitted" or "enviada" text anywhere in modal
        try:
            found = await self.page.evaluate("""
                () => {
                    const modal = document.querySelector('[data-test-modal], .artdeco-modal, .jobs-easy-apply-modal');
                    if (!modal) return false;
                    const text = modal.textContent.toLowerCase();
                    return text.includes('submitted') || text.includes('enviada') || text.includes('received');
                }
            """)
            if found:
                return True
        except Exception:
            pass

        # Fallback: modal disappeared = likely submitted
        modal = await self.page.query_selector(
            "[data-test-modal], .jobs-easy-apply-modal, .artdeco-modal[role='dialog']"
        )
        if modal is None:
            logger.debug("Modal disappeared — assuming submission succeeded")
            return True

        # Modal still open = probably not submitted
        return False

    async def _get_action_button(self) -> Optional[ElementHandle]:
        """Return the primary action button on the current modal step."""
        # Priority: Submit > Review > Next > Continue > any primary in footer
        priority_selectors = [
            "button[aria-label*='Submit application']",
            "button[aria-label*='Enviar solicitud']",
            "button[aria-label*='Review your application']",
            "button[aria-label*='Revisar']",
            "button[aria-label*='Continue to next step']",
            "button[aria-label*='Siguiente']",
            "button[aria-label*='Next']",
            # Generic modal footer primary button (catches all LinkedIn variants)
            ".jobs-easy-apply-modal footer button.artdeco-button--primary",
            ".artdeco-modal footer button.artdeco-button--primary",
            "[data-test-modal] footer button.artdeco-button--primary",
        ]
        for sel in priority_selectors:
            try:
                btn = await self.page.query_selector(sel)
                if btn and await btn.is_visible():
                    return btn
            except Exception:
                continue

        # JS fallback: find the primary button in any visible modal footer
        try:
            btn_handle = await self.page.evaluate_handle("""
                () => {
                    const modals = document.querySelectorAll(
                        '.artdeco-modal, [data-test-modal], .jobs-easy-apply-modal'
                    );
                    for (const modal of modals) {
                        const footer = modal.querySelector('footer, .artdeco-modal__actionbar');
                        if (!footer) continue;
                        const btns = footer.querySelectorAll('button');
                        // Return the last primary-looking button (usually Submit/Next)
                        for (const b of Array.from(btns).reverse()) {
                            if (b.offsetParent !== null &&
                                (b.classList.contains('artdeco-button--primary') ||
                                 b.getAttribute('data-control-name')?.includes('submit'))) {
                                return b;
                            }
                        }
                        // If no primary button, return any visible button
                        for (const b of btns) {
                            if (b.offsetParent !== null) return b;
                        }
                    }
                    return null;
                }
            """)
            if btn_handle:
                el = btn_handle.as_element()
                if el:
                    return el
        except Exception:
            pass

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
        # Use broader modal selectors that cover 2025+ LinkedIn modals
        modal_scopes = [
            ".jobs-easy-apply-modal",
            ".artdeco-modal",
            "[data-test-modal]",
        ]
        for scope in modal_scopes:
            inputs = await self.page.query_selector_all(
                f"{scope} input[type='text']:visible, "
                f"{scope} input[type='number']:visible, "
                f"{scope} input[type='email']:visible, "
                f"{scope} input[type='tel']:visible, "
                f"{scope} input[type='url']:visible"
            )
            if inputs:
                break
        else:
            inputs = []

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
                else:
                    logger.debug(f"No answer found for field: '{label}'")
            except Exception as e:
                logger.debug(f"Text fill error: {e}")

    async def _fill_selects(self) -> None:
        """Handle <select> dropdowns."""
        modal_scopes = [
            ".jobs-easy-apply-modal",
            ".artdeco-modal",
            "[data-test-modal]",
        ]
        for scope in modal_scopes:
            selects = await self.page.query_selector_all(f"{scope} select:visible")
            if selects:
                break
        else:
            selects = []

        for sel_el in selects:
            try:
                # Skip if already selected (non-default value)
                current_val = await sel_el.input_value()
                if current_val and current_val.strip():
                    continue

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
                                logger.debug(f"Select fallback: '{label}' → first option")
                                break
            except Exception as e:
                logger.debug(f"Select fill error: {e}")

    async def _fill_radios(self) -> None:
        """Handle radio button groups (Yes/No questions, etc.)."""
        modal_scopes = [
            ".jobs-easy-apply-modal",
            ".artdeco-modal",
            "[data-test-modal]",
        ]
        for scope in modal_scopes:
            fieldsets = await self.page.query_selector_all(f"{scope} fieldset:visible")
            if fieldsets:
                break
        else:
            fieldsets = []

        for fieldset in fieldsets:
            try:
                # Try legend first, then span/label as question text
                legend = await fieldset.query_selector("legend, span.fb-dash-form-element__label")
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
                else:
                    # If no label match, try selecting by value
                    for radio in radios:
                        val = await radio.get_attribute("value")
                        if val and answer.lower() in val.lower():
                            await radio.click()
                            logger.debug(f"Radio by value: '{question}' → '{val}'")
                            break
            except Exception as e:
                logger.debug(f"Radio fill error: {e}")

    async def _fill_checkboxes(self) -> None:
        """Check required checkboxes (e.g. terms agreement)."""
        modal_scopes = [
            ".jobs-easy-apply-modal",
            ".artdeco-modal",
            "[data-test-modal]",
        ]
        for scope in modal_scopes:
            checkboxes = await self.page.query_selector_all(
                f"{scope} input[type='checkbox']:visible"
            )
            if checkboxes:
                break
        else:
            checkboxes = []

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

        modal_scopes = [
            ".jobs-easy-apply-modal",
            ".artdeco-modal",
            "[data-test-modal]",
        ]
        for scope in modal_scopes:
            file_inputs = await self.page.query_selector_all(f"{scope} input[type='file']")
            if file_inputs:
                break
        else:
            file_inputs = []

        for inp in file_inputs:
            try:
                # Check if a file is already uploaded (button text says "Replace")
                parent = await inp.query_selector("xpath=..")
                if parent:
                    parent_text = (await parent.inner_text()).strip().lower()
                    if "replace" in parent_text or "uploaded" in parent_text:
                        logger.debug("CV already uploaded, skipping")
                        continue

                await inp.set_input_files(str(self.cv_pdf_path))
                await asyncio.sleep(1.5)  # wait for upload to process
                logger.debug("CV uploaded")
            except Exception as e:
                logger.debug(f"CV upload error: {e}")

    async def _fill_cover_letter(self, cover_letter: str) -> None:
        """Paste cover letter into cover letter textarea if present."""
        modal_scopes = [
            ".jobs-easy-apply-modal",
            ".artdeco-modal",
            "[data-test-modal]",
        ]
        for scope in modal_scopes:
            textareas = await self.page.query_selector_all(f"{scope} textarea:visible")
            if textareas:
                break
        else:
            textareas = []

        for ta in textareas:
            try:
                label = await self._get_field_label(ta)
                label_lower = (label or "").lower()
                is_cover = any(
                    kw in label_lower
                    for kw in ["cover letter", "message", "tell us", "additional info",
                               "why do you want", "why are you", "carta de presentación",
                               "mensaje", "cuéntanos"]
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
        if not label:
            return None
        label_lower = label.lower()
        for pattern, answer in EASY_APPLY_ANSWERS.items():
            if re.search(pattern, label_lower):
                return answer
        return None

    # ── Debug helpers ────────────────────────────────────────

    async def _save_debug_screenshot(self, job: JobPosting, suffix: str = "debug") -> None:
        """Save a screenshot for debugging Easy Apply failures."""
        try:
            DEBUG_DIR.mkdir(exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_company = re.sub(r'[^\w\-]', '_', job.company)[:20]
            filename = DEBUG_DIR / f"ea_{safe_company}_{suffix}_{ts}.png"
            await self.page.screenshot(path=str(filename), full_page=False)
            logger.info(f"Debug screenshot saved: {filename}")

            # Also dump visible buttons for diagnosis
            buttons = await self.page.evaluate("""
                () => Array.from(document.querySelectorAll('button')).filter(b => b.offsetParent !== null).map(b => ({
                    text: b.textContent.trim().slice(0, 60),
                    aria: b.getAttribute('aria-label'),
                    cls: b.className.slice(0, 60),
                })).slice(0, 20)
            """)
            if buttons:
                logger.debug(f"Visible buttons on page: {buttons}")
        except Exception as e:
            logger.debug(f"Screenshot error: {e}")
