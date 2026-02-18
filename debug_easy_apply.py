"""
debug_easy_apply.py
Abre una URL de LinkedIn job y muestra todos los botones que encuentra.
Así podemos ver exactamente cómo se llama el botón de Easy Apply.

Uso:
    poetry run python debug_easy_apply.py
"""

import asyncio
import json
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

SESSION_FILE = Path("linkedin_session.json")

# Pega aquí 2-3 URLs de jobs que TÚ ves con Easy Apply en el browser
TEST_URLS = [
    "https://www.linkedin.com/jobs/view/4373033760/",  # Cloud Engineer @ Randstad (tiene Easy Apply)
    "https://www.linkedin.com/jobs/view/4364598710/",  # DevOps Kubernetes SME
]


async def debug():
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        )
        await context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

        # Load saved session
        if SESSION_FILE.exists():
            cookies = json.loads(SESSION_FILE.read_text())
            await context.add_cookies(cookies)
            print("✅ Session loaded\n")
        else:
            print("❌ No session file found — run save_linkedin_session.py first")
            return

        page = await context.new_page()

        for url in TEST_URLS:
            print(f"\n{'='*60}")
            print(f"URL: {url}")
            print('='*60)

            await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            await asyncio.sleep(5)  # LinkedIn SPA needs time to fully render

            print(f"Final URL: {page.url}")

            # Dump ALL buttons on the page
            buttons = await page.evaluate("""
                () => Array.from(document.querySelectorAll('button')).map(b => ({
                    text: b.textContent.trim().slice(0, 80),
                    ariaLabel: b.getAttribute('aria-label'),
                    className: b.className.slice(0, 80),
                    visible: b.offsetParent !== null,
                }))
            """)

            print(f"\nAll buttons found ({len(buttons)}):")
            for btn in buttons:
                marker = "⭐" if "apply" in (btn['text'] + (btn['ariaLabel'] or '')).lower() else "  "
                print(f"  {marker} text='{btn['text']}'  aria='{btn['ariaLabel']}'  visible={btn['visible']}")

            # Also check for any element containing "Easy Apply" text
            easy_apply_elements = await page.evaluate("""
                () => {
                    const all = document.querySelectorAll('*');
                    const matches = [];
                    for (const el of all) {
                        if (el.children.length === 0 && el.textContent.includes('Easy Apply')) {
                            matches.push({
                                tag: el.tagName,
                                text: el.textContent.trim(),
                                class: el.className,
                            });
                        }
                    }
                    return matches.slice(0, 10);
                }
            """)

            if easy_apply_elements:
                print(f"\n  'Easy Apply' text found in {len(easy_apply_elements)} elements:")
                for el in easy_apply_elements:
                    print(f"    <{el['tag']} class='{el['class']}'>{el['text']}</{el['tag']}>")
            else:
                print("\n  ⚠️  'Easy Apply' text NOT found anywhere on page")

            # Screenshot
            screenshot_path = f"debug_job_{url.split('/')[-2]}.png"
            await page.screenshot(path=screenshot_path)
            print(f"\n  Screenshot: {screenshot_path}")

        await browser.close()
        print("\n\nDone! Check the screenshots and button list above.")


if __name__ == "__main__":
    asyncio.run(debug())