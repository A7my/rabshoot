"""Dev helper: screenshot the UI served by `vite preview` (engine must be running).

PLAYWRIGHT_BROWSERS_PATH=.rabshoot-dev/browsers python scripts/ui_screenshots.py [base_url] [out_dir]
"""

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:4173/"
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else ".rabshoot-dev/shots")
PAGES = sys.argv[3].split(",") if len(sys.argv) > 3 else []

DEFAULT = [
    ("dashboard", "#/"),
    ("dashboard-ar", "?lang=ar#/"),
    ("profile-delivery", "#/profiles/{pid}?tab=delivery"),
    ("profile-code", "#/profiles/{pid}?tab=code"),
    ("profile-slack", "#/profiles/{pid}?tab=slack"),
    ("profile-schedule-ar", "?lang=ar#/profiles/{pid}?tab=schedule"),
    ("connections", "#/connections"),
    ("history", "#/history"),
    ("settings", "#/settings"),
    ("wizard-new", "#/profiles/new"),
]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 860}, device_scale_factor=1)
        page.goto(BASE + "#/")
        page.wait_for_load_state("networkidle")
        pid = page.evaluate("""async () => {
            const r = await fetch('http://127.0.0.1:8765/profiles', {headers: {Authorization: 'Bearer dev'}});
            const d = await r.json(); return d.length ? d[0].id : '';
        }""")
        for name, path in DEFAULT:
            if PAGES and name not in PAGES:
                continue
            page.evaluate("localStorage.clear()")
            page.goto(BASE + path.format(pid=pid))
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(1500)
            page.screenshot(path=str(OUT / f"{name}.png"), full_page=False)
            print("saved", name)
        browser.close()


if __name__ == "__main__":
    main()
