"""
save_linkedin_session.py - Guarda cookies de LinkedIn para el agente.

Uso: poetry run python save_linkedin_session.py
"""

import json
from pathlib import Path
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv(Path(__file__).parent / ".env")
SESSION_FILE = Path("linkedin_session.json")


def save_session():
    print("\n" + "═" * 55)
    print("  LinkedIn Session Saver")
    print("═" * 55)
    print("\n  1. Se abrirá Chrome ahora")
    print("  2. Haz login en LinkedIn normalmente")
    print("  3. Cuando veas tu FEED, vuelve aquí y presiona ENTER")
    print("\n" + "═" * 55 + "\n")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=["--start-maximized", "--no-sandbox"],
        )
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()
        page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded")

        print("  Browser abierto en LinkedIn login.")
        print("  Haz login y cuando veas tu feed...\n")
        input("  ✋ Presiona ENTER aquí ▶  ")

        # Read URL from all open pages — LinkedIn may have opened new tabs
        all_pages = context.pages
        current_url = all_pages[-1].url  # last active page
        print(f"\n  URL detectada: {current_url}")

        # Save cookies regardless of URL — if user says they're logged in, trust them
        cookies = context.cookies("https://www.linkedin.com")
        li_cookies = [c for c in cookies if "linkedin" in c.get("domain", "")]

        if li_cookies:
            SESSION_FILE.write_text(json.dumps(cookies, indent=2))
            print(f"\n  ✅ {len(li_cookies)} cookies de LinkedIn guardadas en {SESSION_FILE}")
            print("  El agente las usará automáticamente.\n")
        else:
            # Save all cookies anyway as fallback
            all_cookies = context.cookies()
            if all_cookies:
                SESSION_FILE.write_text(json.dumps(all_cookies, indent=2))
                print(f"\n  ✅ {len(all_cookies)} cookies guardadas (sesión completa)")
                print("  El agente las usará automáticamente.\n")
            else:
                print("\n  ❌ No se encontraron cookies.")
                print("  Asegúrate de haber hecho login antes de presionar ENTER.\n")

        browser.close()


if __name__ == "__main__":
    save_session()