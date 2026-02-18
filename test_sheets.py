"""
test_sheets.py — Diagnóstico rápido del Google Sheets tracker.

Corre con:
    poetry run python test_sheets.py

Hace 4 cosas:
  1. Conecta a Google Sheets y muestra cuántas filas hay
  2. Escribe una fila de prueba
  3. Lee de vuelta esa fila y verifica que los datos son correctos
  4. Muestra las últimas 5 filas reales de tu sheet
"""

import sys
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
import os

load_dotenv(Path(__file__).parent / ".env")

from tracker.sheets_tracker import SheetsTracker, LocalCSVTracker
from scrapers.base_scraper import JobPosting

SHEET_ID   = os.getenv("GOOGLE_SHEET_ID", "1rvPeS_2IFKpgOhq0OFGeGpXqjrXFrVP3_X2Ha24ilsk")
CREDS_PATH = os.getenv("GOOGLE_SHEETS_CREDENTIALS", "credentials.json")

# ── ANSI colors ──────────────────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
RESET  = "\033[0m"
BOLD   = "\033[1m"

def ok(msg):   print(f"  {GREEN}✅ {msg}{RESET}")
def fail(msg): print(f"  {RED}❌ {msg}{RESET}")
def info(msg): print(f"  {CYAN}ℹ  {msg}{RESET}")
def warn(msg): print(f"  {YELLOW}⚠  {msg}{RESET}")

# ─────────────────────────────────────────────────────────────

def test_sheets():
    print(f"\n{BOLD}{'='*55}")
    print("  Google Sheets Tracker — Diagnostic Test")
    print(f"{'='*55}{RESET}\n")

    # ── 1. Config check ──────────────────────────────────────
    print(f"{BOLD}1. Configuration{RESET}")
    if not SHEET_ID:
        fail("GOOGLE_SHEET_ID not set in .env")
        sys.exit(1)
    else:
        ok(f"Sheet ID: {SHEET_ID[:20]}...")

    if not Path(CREDS_PATH).exists():
        fail(f"credentials.json not found at: {CREDS_PATH}")
        sys.exit(1)
    else:
        ok(f"Credentials file found: {CREDS_PATH}")

    # ── 2. Connect ───────────────────────────────────────────
    print(f"\n{BOLD}2. Connection{RESET}")
    tracker = SheetsTracker(CREDS_PATH, SHEET_ID)
    connected = tracker.connect()

    if not connected:
        fail("Could not connect to Google Sheets — check credentials and sheet sharing")
        sys.exit(1)
    ok("Connected successfully")

    # ── 3. Read existing rows ────────────────────────────────
    print(f"\n{BOLD}3. Existing data{RESET}")
    try:
        all_rows = tracker._sheet.get_all_values()
        total = len(all_rows) - 1  # exclude header
        ok(f"Sheet has {total} job entries")

        if total > 0:
            print(f"\n  {BOLD}Last 5 entries:{RESET}")
            headers = all_rows[0]
            data_rows = all_rows[1:]
            for row in data_rows[-5:]:
                row_dict = dict(zip(headers, row))
                score  = row_dict.get("Score",  "?")
                status = row_dict.get("Status", "?")
                title  = row_dict.get("Title",  "?")[:40]
                company = row_dict.get("Company", "?")[:25]
                country = row_dict.get("Country", "?")
                print(f"  {CYAN}[{score:>3}/100]{RESET} {title} @ {company} ({country}) — {status}")
        else:
            warn("Sheet is empty — run the agent first with --dry-run")
    except Exception as e:
        fail(f"Error reading sheet: {e}")

    # ── 4. Write test row ────────────────────────────────────
    print(f"\n{BOLD}4. Write test{RESET}")
    test_job = JobPosting(
        title="[TEST] Senior DevOps Engineer",
        company="Test Company Inc.",
        location="Auckland",
        country="New Zealand",
        url="https://www.seek.co.nz/job/TEST123",
        apply_url="https://www.seek.co.nz/job/TEST123",
        source="test",
        score=99,
        status="test",
        easy_apply=False,
        posted_date=datetime.now(),
        cover_letter="This is a test cover letter entry. Safe to delete.",
    )

    saved = tracker.save_job(test_job)
    if saved:
        ok(f"Test row written successfully (job_id: {test_job.job_id})")
    else:
        warn("Test row was skipped (already exists — that's fine)")

    # ── 5. Read back the test row ────────────────────────────
    print(f"\n{BOLD}5. Read-back verification{RESET}")
    try:
        cell = tracker._sheet.find(test_job.job_id)
        if cell:
            row_data = tracker._sheet.row_values(cell.row)
            ok(f"Test row found at row {cell.row}")
            info(f"Title:   {row_data[1]}")
            info(f"Company: {row_data[2]}")
            info(f"Country: {row_data[4]}")
            info(f"Score:   {row_data[6]}")
            info(f"Status:  {row_data[7]}")
        else:
            fail("Test row not found after writing — something went wrong")
    except Exception as e:
        fail(f"Read-back error: {e}")

    # ── 6. Update status test ────────────────────────────────
    print(f"\n{BOLD}6. Status update test{RESET}")
    try:
        tracker.update_job_status(test_job.job_id, "test-updated", datetime.now())
        cell = tracker._sheet.find(test_job.job_id)
        if cell:
            status_val = tracker._sheet.cell(cell.row, 8).value
            if status_val == "test-updated":
                ok("Status update works correctly")
            else:
                warn(f"Status update may have failed — got: '{status_val}'")
    except Exception as e:
        fail(f"Status update error: {e}")

    # ── Done ─────────────────────────────────────────────────
    print(f"\n{BOLD}{'='*55}")
    print(f"  {GREEN}All tests passed! Google Sheets is working.{RESET}")
    print(f"  {CYAN}👉 Open your sheet to see the [TEST] row — delete it when done.{RESET}")
    sheet_url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}"
    print(f"  {CYAN}   {sheet_url}{RESET}")
    print(f"{BOLD}{'='*55}{RESET}\n")


def test_csv_fallback():
    """Test the CSV fallback tracker (no Google credentials needed)."""
    print(f"\n{BOLD}Testing CSV fallback tracker...{RESET}")
    tracker = LocalCSVTracker("test_jobs.csv")

    job = JobPosting(
        title="[TEST] Platform Engineer",
        company="Test Corp",
        location="Toronto",
        country="Canada",
        url="https://linkedin.com/jobs/TEST456",
        apply_url="https://linkedin.com/jobs/TEST456",
        source="test",
        score=85,
        status="test",
    )
    saved = tracker.save_job(job)
    if saved and Path("test_jobs.csv").exists():
        ok("CSV tracker works — test_jobs.csv created")
        Path("test_jobs.csv").unlink()  # cleanup
    else:
        warn("CSV already existed or save failed")


if __name__ == "__main__":
    if not SHEET_ID:
        warn("No GOOGLE_SHEET_ID found — testing CSV fallback only")
        test_csv_fallback()
    else:
        test_sheets()