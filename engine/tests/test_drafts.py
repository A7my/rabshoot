import copy

import pytest
from fastapi.testclient import TestClient

from rabshoot_engine import connectors, drafts, history, pipeline, storage
from rabshoot_engine.ai import AIClient
from rabshoot_engine.api import create_app
from rabshoot_engine.drafts import DraftContent
from rabshoot_engine.mail import smtp
from rabshoot_engine.models import Profile, Schedule
from rabshoot_engine.render import parse_blocks

ME = "me@x.com"
PROJECT = {"name": "api", "source": "gitlab", "url": "https://git.x/api", "files": [],
           "commits": [{"title": "fix", "author": "me", "url": "https://git.x/c", "short_id": "abc1"}],
           "merge_requests": [], "issues": [], "changes": ["Fixed the login timeout"]}


@pytest.fixture
def mail(monkeypatch):
    """Fakes collection, AI and SMTP; real rendering. Returns the sent (message, recipients) pairs."""
    sent = []
    monkeypatch.setattr(pipeline, "profile_problems", lambda p, c: [])
    monkeypatch.setattr(storage, "get_connection", lambda cid: None)
    monkeypatch.setattr(connectors, "email_credentials", lambda c: ({"address": ME}, "x"))
    monkeypatch.setattr(pipeline, "plan_email", lambda profile, meta, pw, subject: pipeline.EmailPlan(
        sender=ME, subject=subject, to=["team@x.com"], cc=[], bcc=[]))
    monkeypatch.setattr(pipeline, "summarize", lambda *a, **k: None)
    monkeypatch.setattr(smtp, "send", lambda meta, pw, msg, to: sent.append((msg, to)))
    monkeypatch.setattr(pipeline, "collect_code", lambda *a: [copy.deepcopy(PROJECT)])
    monkeypatch.setattr(pipeline, "collect_slack", lambda *a: [])
    return sent


def _profile() -> Profile:
    return storage.save_profile(Profile(name="Team", schedule=Schedule(
        time="18:00", days="*", timezone="Africa/Cairo")))


def _html(msg) -> str:
    return msg.get_body(("html",)).get_content()


def test_preview_returns_the_email_as_editable_text(mail):
    result = pipeline.run(_profile(), trigger="preview", send=False)
    content = result.as_dict(include_html=True)["draft"]["content"]
    assert content["subject"] and not mail
    assert "## Code changes" in content["body"] and "### api" in content["body"]
    assert "• Fixed the login timeout" in content["body"]


def test_edited_text_is_sent_and_counts_as_todays_send(mail):
    profile = _profile()
    preview = pipeline.run(profile, trigger="preview", send=False)
    content = DraftContent(subject="My day", body=(
        "Off tomorrow.\nBack Sunday.\n\n## Code changes\n### api\n• [Major] Rewrote the login flow\n"))

    result = pipeline.send_draft(profile, drafts.get(preview.draft["id"]), content)

    assert result.status == "sent"
    msg, to = mail[-1]
    assert to == ["team@x.com"] and msg["Subject"] == "My day"
    html = _html(msg)
    assert "Rewrote the login flow" in html and "MAJOR" in html
    assert "Fixed the login timeout" not in html and "Off tomorrow.<br>Back Sunday." in html
    assert "CODE CHANGES" in msg.get_body(("plain",)).get_content()
    assert "edited before sending" in result.steps[-1]["message"]
    run = history.get_run(result.run_id)
    assert run["trigger"] == "manual" and history.sent_for_day(profile.id, run["report_day"])


def test_unchanged_text_keeps_the_original_layout(mail):
    profile = _profile()
    preview = pipeline.run(profile, trigger="preview", send=False)
    pipeline.send_draft(profile, drafts.get(preview.draft["id"]), DraftContent(**preview.draft["content"]))
    assert 'href="https://git.x/api"' in _html(mail[-1][0])


def test_draft_test_send_goes_only_to_me(mail):
    profile = _profile()
    preview = pipeline.run(profile, trigger="preview", send=False)
    result = pipeline.send_draft(profile, drafts.get(preview.draft["id"]),
                                 DraftContent(**preview.draft["content"]), test_to=ME)
    msg, to = mail[-1]
    assert result.status == "sent" and to == [ME] and msg["Subject"].startswith("[Test] ")
    assert not history.sent_for_day(profile.id, history.get_run(result.run_id)["report_day"])


def test_parse_blocks():
    blocks = parse_blocks("Hello\nteam\n\nSecond\n## Code\n### api\n• one\n- two\n## Slack\n")
    assert [b["type"] for b in blocks] == ["p", "p", "h2", "h3", "list", "h2"]
    assert blocks[0]["lines"] == ["Hello", "team"] and blocks[4]["items"] == ["one", "two"]
    assert blocks[2]["color"] != blocks[5]["color"]


def test_polish_strips_code_fences_and_passes_the_request(monkeypatch):
    seen = {}

    def chat(self, prompt, system=None, waits=None):
        seen["prompt"] = prompt
        return "```text\n## Code changes\n• Fixed login.\n```"

    monkeypatch.setattr(AIClient, "chat", chat)
    text = AIClient("k").polish_report("## code\n• fixd login", "add a greeting")
    assert text == "## Code changes\n• Fixed login.\n"
    assert "add a greeting" in seen["prompt"] and "fixd login" in seen["prompt"]


def test_draft_api_render_ai_and_expiry(mail, monkeypatch):
    profile = _profile()
    profile.ai_connection_id = "ai1"
    storage.save_profile(profile)
    preview = pipeline.run(profile, trigger="preview", send=False)
    did, content = preview.draft["id"], preview.draft["content"]
    c = TestClient(create_app("t"), headers={"Authorization": "Bearer t"})

    content["body"] = "Short day today."
    r = c.post(f"/drafts/{did}/render", json={"content": content})
    assert r.status_code == 200 and "Short day today." in r.json()["html"]

    class FakeAI:
        def polish_report(self, body, instruction=""):
            assert body == "Short day today." and instruction == ""
            return "A short day today.\n"

    monkeypatch.setattr(connectors, "ai_client", lambda conn, language: FakeAI())
    r = c.post(f"/drafts/{did}/ai", json={"content": content})
    assert r.status_code == 200
    assert r.json()["content"]["body"] == "A short day today.\n" and "A short day today." in r.json()["html"]

    content["body"] = " "
    assert c.post(f"/drafts/{did}/ai", json={"content": content}).status_code == 400
    assert c.post("/drafts/nope/render", json={"content": content}).status_code == 404
