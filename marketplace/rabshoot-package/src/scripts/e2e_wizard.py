"""Dev E2E: click through the onboarding wizard with real accounts from .env (nothing is sent).

Run inside scripts/ui_session.sh with an EMPTY RABSHOOT_HOME.
"""

import re
import sys
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parent.parent
OUT = Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / ".rabshoot-dev" / "shots" / "wizard")
BASE = "http://localhost:4173/"


def dotenv() -> dict:
    env = {}
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"')
    return env


def main() -> None:
    env = dotenv()
    OUT.mkdir(parents=True, exist_ok=True)
    shot = lambda page, name: page.screenshot(path=str(OUT / f"{name}.png"), full_page=True)  # noqa: E731
    next_btn = lambda page: page.get_by_role("button", name=re.compile(r"^(Next|Finish setup)"))  # noqa: E731

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 860})
        page.set_default_timeout(30_000)
        page.goto(BASE)
        page.get_by_text("Let's start").wait_for()
        shot(page, "0-welcome")
        page.get_by_role("button", name="العربية").click()
        page.wait_for_timeout(300)
        shot(page, "0-welcome-ar")
        page.get_by_role("button", name="English").click()
        page.get_by_role("button", name="Let's start").click()

        # 1. sender
        page.get_by_placeholder("you@company.com").fill(env["SMTP_USER"])
        page.get_by_placeholder("xxxx xxxx xxxx xxxx").fill(env["SMTP_PASSWORD"])
        page.get_by_placeholder("Your name").fill("Daily Reporter")
        shot(page, "1-sender")
        page.get_by_role("button", name="Connect").click()
        expect(next_btn(page)).to_be_enabled(timeout=60_000)
        print("sender connected")
        next_btn(page).click()

        # 2. delivery: look at threads, then send to people
        page.get_by_text("Reply in a thread").click()
        page.get_by_text(re.compile(r"\d+ messages?")).first.wait_for(timeout=60_000)
        page.locator("button:has-text('message')").first.click()
        page.wait_for_timeout(300)
        shot(page, "2-thread")
        print("threads listed")
        page.get_by_text("Send to people").click()
        chips = page.get_by_placeholder("Type an email and press Enter").first
        chips.fill(env["SMTP_USER"])
        chips.press("Enter")
        shot(page, "2-recipients")
        next_btn(page).click()

        # 3. code
        page.get_by_text("GitLab.com", exact=True).click()
        shot(page, "3-code-guide")
        page.get_by_placeholder("glpat-…").fill(env["GITLAB_TOKEN"])
        page.get_by_role("button", name="Connect").click()
        page.get_by_text("Connected sources").wait_for()
        expect(next_btn(page)).to_be_enabled(timeout=60_000)
        page.get_by_text("Choose projects").click()
        page.get_by_text(re.compile("ago|minutes|hours|days")).first.wait_for(timeout=60_000)
        shot(page, "3-code-projects")
        page.get_by_text("All projects with activity that day").click()
        print("gitlab connected")
        next_btn(page).click()

        # 4. slack
        shot(page, "4-slack-guide")
        page.get_by_placeholder("xoxp-…").fill(env["SLACK_USER_TOKEN"])
        page.get_by_role("button", name="Connect").click()
        page.get_by_text("Which conversations should be included?").wait_for(timeout=60_000)
        page.get_by_text("tasks", exact=True).first.click()
        shot(page, "4-slack-picker")
        print("slack connected")
        next_btn(page).click()

        # 5. ai
        shot(page, "5-ai")
        page.get_by_placeholder("Paste your Gemini API key").fill(env["AI_API_KEY"])
        page.get_by_role("button", name="Connect").click()
        expect(next_btn(page)).to_be_enabled(timeout=180_000)
        print("ai connected")
        next_btn(page).click()

        # 6. schedule
        page.get_by_role("button", name="Sun – Thu").click()
        shot(page, "6-schedule")
        next_btn(page).click()

        # 7. preview (builds a real report, sends nothing)
        page.get_by_role("button", name="Build preview").click()
        page.locator("iframe").wait_for(timeout=240_000)
        page.wait_for_timeout(1000)
        shot(page, "7-preview")
        print("preview built")
        next_btn(page).click()
        page.get_by_text("Next send").wait_for(timeout=30_000)
        shot(page, "8-dashboard")
        print("wizard finished")
        browser.close()


if __name__ == "__main__":
    main()
