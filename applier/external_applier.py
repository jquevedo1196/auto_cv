"""
Job Hunter Agent - External Portal Applier
Automates job applications on external career portals (Seek, StepStone,
Arbetsformedlingen, OCC Mundial, and company career pages).

Strategy:
  1. Open the apply URL in a Playwright browser
  2. Detect common application form patterns
  3. Fill name, email, phone, cover letter, upload CV
  4. Submit if confident, otherwise save a screenshot for manual review

This is best-effort automation — external portals have wildly different
forms. When auto-fill isn't possible, the job is logged for manual review.

Usage:
    applier = ExternalApplier(cv_pdf_path="assets/Resume_DevOps_SRE.pdf")
    result = await applier.apply(job)
"""

import asyncio
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Optional, List

from playwright.async_api import async_playwright, Browser, BrowserContext, Page, ElementHandle

from scrapers.base_scraper import JobPosting
from config.cv_data import CV_DATA

logger = logging.getLogger(__name__)

DEBUG_DIR = Path("debug_screenshots")

# ── Field patterns → values ─────────────────────────────────────
# Maps regex patterns (matched against label/placeholder/name/id) to answers.
FIELD_MAP: dict[str, str] = {
    # Name fields
    r"first.?name|given.?name|nombre":          CV_DATA["name"].split()[0],  # "Jesús"
    r"last.?name|family.?name|apellido":        " ".join(CV_DATA["name"].split()[1:]),
    r"full.?name|your.?name|nombre.?completo":  CV_DATA["name"],

    # Contact
    r"e.?mail|correo":                          CV_DATA["email"],
    r"phone|tel[eé]fono|mobile|celular":        CV_DATA["phone"],

    # Location
    r"city|ciudad":                             "Mexico City",
    r"country|pa[ií]s":                         "Mexico",
    r"address|direcci[oó]n":                    "Mexico City, Mexico",
    r"zip|postal|c[oó]digo postal":             "06600",

    # Professional
    r"linkedin":                                "https://www.linkedin.com/in/jenriqueqt",
    r"github":                                  "https://github.com/jenriqueqt",
    r"portfolio|website|sitio.?web":            "https://www.linkedin.com/in/jenriqueqt",
    r"current.?title|job.?title|puesto":        CV_DATA["title"],
    r"years.*experience|a[ñn]os.*experiencia":  "9",

    # Salary
    r"salary|sueldo|salario|compensation":      "Negotiable",

    # Availability
    r"notice.?period|periodo.?de.?aviso":       "4 weeks",
    r"start.?date|fecha.*inicio|disponibilidad":"Within 4-6 weeks",

    # Work auth
    r"visa|work.?permit|permiso.?trabajo":      "Yes, I will require sponsorship",
    r"authorized|autorizado":                   "Yes",
    r"relocat|reubicar":                        "Yes",
}


class ExternalApplier:
    """Automates applications on external job portals."""

    def __init__(self, cv_pdf_path: str = "assets/Resume_DevOps_SRE.pdf"):
        self.cv_pdf_path = Path(cv_pdf_path)
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None

    # ── Lifecycle ────────────────────────────────────────────

    async def launch(self):
        """Launch a dedicated browser for external sites."""
        if self._browser:
            return

        self._playwright = await async_playwright().start()
        _headless = not bool(os.environ.get("BROWSER_VISIBLE"))
        self._browser = await self._playwright.chromium.launch(
            headless=_headless,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        self._context = await self._browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1440, "height": 900},
            locale="en-US",
        )
        self._page = await self._context.new_page()
        logger.info("External applier browser launched")

    async def close(self):
        """Close the browser."""
        try:
            if self._browser:
                await self._browser.close()
            if self._playwright:
                await self._playwright.stop()
        except Exception:
            pass
        self._browser = None
        self._page = None

    # ── Public API ───────────────────────────────────────────

    async def apply(self, job: JobPosting) -> bool:
        """
        Attempt to apply to an external job.
        Returns True if application was submitted or the form was meaningfully filled.
        """
        if not self._page:
            await self.launch()

        apply_url = job.apply_url or job.url
        logger.info(f"External apply → {job.title} @ {job.company} ({job.source})")
        logger.info(f"  URL: {apply_url}")

        try:
            await self._page.goto(apply_url, wait_until="domcontentloaded", timeout=30_000)
            await asyncio.sleep(3)

            # Detect if this is a portal we know
            current_url = self._page.url.lower()
            handler = self._get_portal_handler(current_url)

            if handler:
                result = await handler(job)
            else:
                result = await self._generic_apply(job)

            if result:
                job.applied = True
                job.applied_date = datetime.now()
                job.status = "applied"
                logger.info(f"✅ SUBMITTED (external): {job.title} @ {job.company}")
            else:
                job.status = "form-filled"
                logger.info(f"📋 Form filled but not submitted: {job.title} @ {job.company}")
                await self._save_screenshot(job, "filled_not_submitted")

            return result

        except Exception as e:
            logger.error(f"External apply error ({apply_url}): {e}")
            await self._save_screenshot(job, "error")
            return False

    # ── Portal-specific handlers ─────────────────────────────

    def _get_portal_handler(self, url: str):
        """Return a portal-specific handler if we recognize the URL."""
        handlers = {
            "seek.co.nz": self._apply_seek,
            "seek.com.au": self._apply_seek,
            "stepstone.de": self._apply_stepstone,
            "arbetsformedlingen.se": self._apply_arbetsformedlingen,
            "occ.com.mx": self._apply_occ,
            "greenhouse.io": self._apply_greenhouse,
            "lever.co": self._apply_lever,
            "workday": self._apply_workday,
            "icims": self._apply_generic_ats,
            "smartrecruiters": self._apply_generic_ats,
            "ashbyhq": self._apply_generic_ats,
        }
        for pattern, handler in handlers.items():
            if pattern in url:
                logger.debug(f"Detected portal: {pattern}")
                return handler
        return None

    async def _apply_seek(self, job: JobPosting) -> bool:
        """Seek NZ/AU — Quick Apply flow."""
        try:
            # Look for "Quick apply" or "Apply" button
            apply_btn = await self._find_button(["Quick apply", "Apply", "Apply now"])
            if apply_btn:
                await apply_btn.click()
                await asyncio.sleep(2)

            # Seek's quick apply has: name, email, phone, CV upload, cover letter
            await self._fill_all_visible_fields()
            await self._upload_cv_to_file_inputs()
            await self._fill_cover_letter_textarea(job.cover_letter)

            # Look for submit
            submit_btn = await self._find_button(["Submit", "Apply", "Send application"])
            if submit_btn:
                await submit_btn.click()
                await asyncio.sleep(2)
                return True
        except Exception as e:
            logger.debug(f"Seek apply error: {e}")
        return False

    async def _apply_stepstone(self, job: JobPosting) -> bool:
        """StepStone DE — Apply flow."""
        try:
            apply_btn = await self._find_button(["Jetzt bewerben", "Apply now", "Apply"])
            if apply_btn:
                await apply_btn.click()
                await asyncio.sleep(2)

            await self._fill_all_visible_fields()
            await self._upload_cv_to_file_inputs()
            await self._fill_cover_letter_textarea(job.cover_letter)

            submit_btn = await self._find_button(["Bewerbung absenden", "Submit", "Send"])
            if submit_btn:
                await submit_btn.click()
                await asyncio.sleep(2)
                return True
        except Exception as e:
            logger.debug(f"StepStone apply error: {e}")
        return False

    async def _apply_arbetsformedlingen(self, job: JobPosting) -> bool:
        """Arbetsformedlingen SE — Swedish job board."""
        try:
            apply_btn = await self._find_button(["Ansök", "Apply", "Skicka ansökan"])
            if apply_btn:
                await apply_btn.click()
                await asyncio.sleep(2)

            await self._fill_all_visible_fields()
            await self._upload_cv_to_file_inputs()

            submit_btn = await self._find_button(["Skicka", "Submit", "Send"])
            if submit_btn:
                await submit_btn.click()
                await asyncio.sleep(2)
                return True
        except Exception as e:
            logger.debug(f"Arbetsformedlingen apply error: {e}")
        return False

    async def _apply_occ(self, job: JobPosting) -> bool:
        """OCC Mundial MX — Mexican job portal."""
        try:
            apply_btn = await self._find_button(["Postularme", "Aplicar", "Apply"])
            if apply_btn:
                await apply_btn.click()
                await asyncio.sleep(2)

            await self._fill_all_visible_fields()
            await self._upload_cv_to_file_inputs()

            submit_btn = await self._find_button(["Enviar", "Postularme", "Submit"])
            if submit_btn:
                await submit_btn.click()
                await asyncio.sleep(2)
                return True
        except Exception as e:
            logger.debug(f"OCC apply error: {e}")
        return False

    async def _apply_greenhouse(self, job: JobPosting) -> bool:
        """Greenhouse ATS — very common in tech."""
        try:
            await self._fill_all_visible_fields()
            await self._upload_cv_to_file_inputs()
            await self._fill_cover_letter_textarea(job.cover_letter)

            submit_btn = await self._find_button(["Submit Application", "Submit", "Apply"])
            if submit_btn:
                await submit_btn.click()
                await asyncio.sleep(2)
                return True
        except Exception as e:
            logger.debug(f"Greenhouse apply error: {e}")
        return False

    async def _apply_lever(self, job: JobPosting) -> bool:
        """Lever ATS — common in startups."""
        try:
            # Lever usually shows the form directly
            await self._fill_all_visible_fields()
            await self._upload_cv_to_file_inputs()
            await self._fill_cover_letter_textarea(job.cover_letter)

            submit_btn = await self._find_button(["Submit application", "Submit", "Apply"])
            if submit_btn:
                await submit_btn.click()
                await asyncio.sleep(2)
                return True
        except Exception as e:
            logger.debug(f"Lever apply error: {e}")
        return False

    async def _apply_workday(self, job: JobPosting) -> bool:
        """Workday ATS — common in enterprise."""
        try:
            # Workday often requires clicking "Apply" first
            apply_btn = await self._find_button(["Apply", "Apply Manually"])
            if apply_btn:
                await apply_btn.click()
                await asyncio.sleep(3)

            await self._fill_all_visible_fields()
            await self._upload_cv_to_file_inputs()

            submit_btn = await self._find_button(["Submit", "Next", "Continue"])
            if submit_btn:
                await submit_btn.click()
                await asyncio.sleep(2)
                return True
        except Exception as e:
            logger.debug(f"Workday apply error: {e}")
        return False

    async def _apply_generic_ats(self, job: JobPosting) -> bool:
        """Generic ATS handler (iCIMS, SmartRecruiters, Ashby, etc.)."""
        return await self._generic_apply(job)

    # ── Generic apply flow ───────────────────────────────────

    async def _generic_apply(self, job: JobPosting) -> bool:
        """
        Best-effort generic application:
        1. Look for an Apply button and click it
        2. Fill all recognizable form fields
        3. Upload CV
        4. Look for Submit button
        """
        try:
            # Step 1: Look for and click any Apply button
            apply_btn = await self._find_button([
                "Apply", "Apply now", "Apply for this job",
                "Postularme", "Aplicar", "Bewerben",
                "Ansök", "Quick apply",
            ])
            if apply_btn:
                await apply_btn.click()
                await asyncio.sleep(3)

            # Step 2: Fill fields
            filled_count = await self._fill_all_visible_fields()
            await self._upload_cv_to_file_inputs()
            await self._fill_cover_letter_textarea(job.cover_letter)

            if filled_count == 0:
                logger.info(f"No fillable fields found — saving for manual review")
                return False

            # Step 3: Submit
            submit_btn = await self._find_button([
                "Submit", "Submit application", "Send application",
                "Apply", "Apply now", "Enviar", "Absenden", "Skicka",
            ])
            if submit_btn:
                await submit_btn.click()
                await asyncio.sleep(2)
                logger.info(f"Clicked submit button on external form")
                return True

            logger.info(f"Filled {filled_count} fields but no submit button found")
            return False

        except Exception as e:
            logger.error(f"Generic apply error: {e}")
            return False

    # ── Form filling helpers ─────────────────────────────────

    async def _fill_all_visible_fields(self) -> int:
        """Fill all visible input/select fields. Returns count of fields filled."""
        filled = 0

        # Text inputs
        inputs = await self._page.query_selector_all(
            "input[type='text']:visible, input[type='email']:visible, "
            "input[type='tel']:visible, input[type='url']:visible, "
            "input[type='number']:visible, input:not([type]):visible"
        )
        for inp in inputs:
            try:
                current = await inp.input_value()
                if current.strip():
                    continue

                label = await self._resolve_label(inp)
                answer = self._match_field(label)
                if answer:
                    await inp.fill(answer)
                    filled += 1
                    logger.debug(f"Filled: '{label}' → '{answer}'")
            except Exception:
                continue

        # Selects
        selects = await self._page.query_selector_all("select:visible")
        for sel in selects:
            try:
                label = await self._resolve_label(sel)
                answer = self._match_field(label)
                if answer:
                    options = await sel.query_selector_all("option")
                    for opt in options:
                        opt_text = (await opt.inner_text()).strip().lower()
                        if answer.lower() in opt_text:
                            opt_val = await opt.get_attribute("value")
                            await sel.select_option(value=opt_val)
                            filled += 1
                            break
            except Exception:
                continue

        return filled

    async def _upload_cv_to_file_inputs(self) -> bool:
        """Upload CV to any visible file input on the page."""
        if not self.cv_pdf_path.exists():
            logger.warning(f"CV not found at {self.cv_pdf_path}")
            return False

        file_inputs = await self._page.query_selector_all("input[type='file']")
        uploaded = False
        for inp in file_inputs:
            try:
                await inp.set_input_files(str(self.cv_pdf_path))
                await asyncio.sleep(1.5)
                uploaded = True
                logger.debug("CV uploaded to external form")
            except Exception as e:
                logger.debug(f"CV upload error: {e}")

        return uploaded

    async def _fill_cover_letter_textarea(self, cover_letter: str) -> None:
        """Fill cover letter in any textarea that looks like a cover letter field."""
        if not cover_letter:
            return

        textareas = await self._page.query_selector_all("textarea:visible")
        for ta in textareas:
            try:
                current = await ta.input_value()
                if current.strip():
                    continue

                label = await self._resolve_label(ta)
                label_lower = (label or "").lower()
                is_cover = any(kw in label_lower for kw in [
                    "cover letter", "message", "tell us", "additional",
                    "why do you want", "motivation", "carta de presentación",
                    "mensaje", "cover", "letter", "notes",
                ])
                if is_cover or len(textareas) == 1:
                    # If there's only one textarea, assume it's for a cover letter/message
                    await ta.fill(cover_letter[:3000])
                    logger.debug("Cover letter filled on external form")
                    return
            except Exception:
                continue

    # ── Button finder ────────────────────────────────────────

    async def _find_button(self, texts: List[str]) -> Optional[ElementHandle]:
        """Find a visible button/link whose text matches any of the given patterns."""
        try:
            btns = await self._page.query_selector_all(
                "button:visible, [role='button']:visible, "
                "a.btn:visible, a[class*='button']:visible, "
                "input[type='submit']:visible"
            )
            for text_pattern in texts:
                pattern_lower = text_pattern.lower()
                for btn in btns:
                    try:
                        btn_text = (await btn.inner_text() or "").strip().lower()
                        aria = (await btn.get_attribute("aria-label") or "").lower()
                        value = (await btn.get_attribute("value") or "").lower()
                        combined = f"{btn_text} {aria} {value}"
                        if pattern_lower in combined:
                            return btn
                    except Exception:
                        continue
        except Exception:
            pass
        return None

    # ── Label resolution ─────────────────────────────────────

    async def _resolve_label(self, element: ElementHandle) -> str:
        """Resolve the label for a form element using multiple strategies."""
        try:
            # aria-label
            aria = await element.get_attribute("aria-label")
            if aria and aria.strip():
                return aria.strip()

            # placeholder
            placeholder = await element.get_attribute("placeholder")
            if placeholder and placeholder.strip():
                return placeholder.strip()

            # name attribute (often descriptive)
            name = await element.get_attribute("name")
            if name and name.strip():
                # Convert camelCase/snake_case to space-separated
                readable = re.sub(r'([a-z])([A-Z])', r'\1 \2', name)
                readable = readable.replace('_', ' ').replace('-', ' ')
                return readable.strip()

            # Associated <label>
            el_id = await element.get_attribute("id")
            if el_id:
                label_el = await self._page.query_selector(f"label[for='{el_id}']")
                if label_el:
                    text = (await label_el.inner_text()).strip()
                    if text:
                        return text

            # Parent label
            parent_label = await element.query_selector("xpath=ancestor::label")
            if parent_label:
                text = (await parent_label.inner_text()).strip()
                return text.split("\n")[0].strip()

            # Sibling or nearby text
            parent = await element.query_selector("xpath=..")
            if parent:
                text = (await parent.inner_text()).strip()
                return text.split("\n")[0].strip()

        except Exception:
            pass
        return ""

    @staticmethod
    def _match_field(label: str) -> Optional[str]:
        """Match a field label to a value from FIELD_MAP."""
        if not label:
            return None
        label_lower = label.lower()
        for pattern, value in FIELD_MAP.items():
            if re.search(pattern, label_lower):
                return value
        return None

    # ── Debug helpers ────────────────────────────────────────

    async def _save_screenshot(self, job: JobPosting, suffix: str = "debug") -> None:
        """Save a screenshot for debugging."""
        try:
            DEBUG_DIR.mkdir(exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_company = re.sub(r'[^\w\-]', '_', job.company)[:20]
            filename = DEBUG_DIR / f"ext_{safe_company}_{suffix}_{ts}.png"
            await self._page.screenshot(path=str(filename), full_page=False)
            logger.info(f"Debug screenshot: {filename}")
        except Exception as e:
            logger.debug(f"Screenshot error: {e}")
