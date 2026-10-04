"""Dev helper: README screenshots from fake data (no accounts needed).

scripts/ui_session.sh .rabshoot-dev/progress-home .venv/bin/python scripts/readme_shots.py
"""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "engine"))

from playwright.sync_api import sync_playwright  # noqa: E402

from rabshoot_engine.models import Profile, SlackSelection  # noqa: E402
from rabshoot_engine.render import render  # noqa: E402
from rabshoot_engine.window import DayWindow  # noqa: E402

BASE = "http://localhost:4173/"
OUT = Path(__file__).resolve().parent.parent / "docs" / "images"


def sample_email() -> str:
    def commit(i, title):
        return {"id": str(i), "short_id": f"a1b2c{i}", "title": title, "author": "Sara",
                "url": "#", "created_at": "2026-10-01T10:00:00Z"}

    projects = [
        {"source": "gitlab", "name": "acme / payments-api", "url": "#",
         "commits": [commit(1, "Add refund endpoint"), commit(2, "Validate currency codes"),
                     commit(3, "Retry failed webhooks")],
         "merge_requests": [{"ref": "!42", "title": "Refunds v1", "action": "merged", "url": "#",
                             "author": "Sara"}],
         "issues": [{"ref": "#118", "title": "Webhook timeouts", "action": "closed", "url": "#"}],
         "files": [{"path": "src/refunds.py", "status": "added", "added": 120, "removed": 0}],
         "changes": ["[Major] New refund endpoint: partial and full refunds with an audit trail",
                     "Webhooks now retry 3 times with backoff instead of failing once",
                     "Currency codes are validated before a payment is created"]},
        {"source": "github", "name": "acme/mobile-app", "url": "#",
         "commits": [commit(4, "Dark mode for settings")], "merge_requests": [], "issues": [],
         "files": [], "changes": ["Settings screen supports dark mode"]},
    ]
    convs = [{"id": "C1", "name": "#backend", "message_count": 14, "threads": [{}],
              "points": ["Release of refunds moved to Sunday after QA sign-off",
                         "Ahmed will rotate the staging database password tomorrow"]}]
    profile = Profile(slack=SlackSelection(connection_id="s", conversations=[{"id": "C1"}]))
    window = DayWindow.for_day(date(2026, 10, 1), "Africa/Cairo")
    return render(profile, window, projects, convs).html_for_display()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 760, "height": 400})
        page.set_content(sample_email())
        page.wait_for_timeout(500)
        page.screenshot(path=str(OUT / "email.png"), full_page=True)

        page = browser.new_page(viewport={"width": 1280, "height": 800})
        page.goto(BASE + "#/")
        page.wait_for_load_state("networkidle")
        pid = page.evaluate("""async () => {
            const r = await fetch('http://127.0.0.1:8765/profiles', {headers: {Authorization: 'Bearer dev'}});
            const d = await r.json(); return d.length ? d[0].id : '';
        }""")
        shots = [("dashboard", "#/", "text=Today"), ("schedule", f"#/profiles/{pid}?tab=schedule", "input[type=time]"),
                 ("old-report", f"#/profiles/{pid}/old-report", "input[type=date]"),
                 ("wizard", "#/profiles/new", "text=Sender email")]
        for name, path, ready in shots:
            page.evaluate("localStorage.clear()")
            page.goto(BASE + "?lang=en" + path)
            page.wait_for_selector(ready)
            page.wait_for_timeout(1000)
            page.screenshot(path=str(OUT / f"{name}.png"))
            print("saved", name)
        browser.close()


if __name__ == "__main__":
    main()
