import copy
from datetime import date

import pytest
from fastapi.testclient import TestClient

from rabshoot_engine import connectors, drafts, history, pipeline, storage
from rabshoot_engine.api import create_app
from rabshoot_engine.drafts import DraftContent
from rabshoot_engine.mail import smtp
from rabshoot_engine.models import Profile, Schedule

ME = "me@x.com"
PROJECT = {"name": "api", "source": "gitlab", "url": "https://git.x/api", "files": [],
           "commits": [{"title": "fix", "author": "me", "url": "https://git.x/c", "short_id": "abc1"}],
           "merge_requests": [], "issues": [], "changes": ["Fixed the login timeout"]}
CONV = {"name": "#team", "threads": [{}], "message_count": 2, "points": ["Release moves to Monday"]}


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
    monkeypatch.setattr(pipeline, "collect_slack", lambda *a: [copy.deepcopy(CONV)])
    return sent


def _profile() -> Profile:
    return storage.save_profile(Profile(name="Team", schedule=Schedule(
        time="18:00", days="*", timezone="Africa/Cairo")))


def _html(msg) -> str:
    return msg.get_body(("html",)).get_content()


def test_preview_returns_an_editable_draft(mail):
    result = pipeline.run(_profile(), trigger="preview", send=False)
    content = result.as_dict(include_html=True)["draft"]["content"]
    assert [(i["key"], i["points"]) for i in content["items"]] == [
        ("p0", ["Fixed the login timeout"]), ("c0", ["Release moves to Monday"])]
    assert content["subject"] and not mail


def test_edited_draft_is_sent_as_edited_and_counts_as_todays_send(mail):
    profile = _profile()
    preview = pipeline.run(profile, trigger="preview", send=False)
    content = DraftContent(**preview.draft["content"])
    content.items[0].points = ["[Major] Rewrote the login flow", "  "]
    content.note = "Off tomorrow.\nBack Sunday."
    content.subject = "My day"

    result = pipeline.send_draft(profile, drafts.get(preview.draft["id"]), content)

    assert result.status == "sent"
    msg, to = mail[-1]
    assert to == ["team@x.com"] and msg["Subject"] == "My day"
    html = _html(msg)
    assert "Rewrote the login flow" in html and "Fixed the login timeout" not in html
    assert "Off tomorrow.<br>Back Sunday." in html
    assert "edited before sending" in result.steps[-1]["message"]
    run = history.get_run(result.run_id)
    assert run["trigger"] == "manual" and run["status"] == "sent"
    assert history.sent_for_day(profile.id, run["report_day"])


def test_draft_test_send_goes_only_to_me(mail):
    profile = _profile()
    preview = pipeline.run(profile, trigger="preview", send=False)
    result = pipeline.send_draft(profile, drafts.get(preview.draft["id"]),
                                 DraftContent(**preview.draft["content"]), test_to=ME)
    msg, to = mail[-1]
    assert result.status == "sent" and to == [ME] and msg["Subject"].startswith("[Test] ")
    assert not history.sent_for_day(profile.id, history.get_run(result.run_id)["report_day"])


def test_apply_keeps_raw_data_unless_points_are_added():
    raw = {k: v for k, v in PROJECT.items() if k != "changes"}
    draft = drafts.save("prof", date(2026, 1, 1), "S", [raw], [], [])
    projects, _ = drafts.apply(draft, draft.content)
    assert "changes" not in projects[0]
    draft.content.items[0].points = ["Added by hand"]
    projects, _ = drafts.apply(draft, draft.content)
    assert projects[0]["changes"] == ["Added by hand"]
    assert "changes" not in draft.projects[0]


def test_merge_ai_takes_known_items_only():
    content = DraftContent(subject="S", items=[drafts.DraftItem(key="p0", points=["a"]),
                                               drafts.DraftItem(key="c0", points=["b"])])
    merged = drafts.merge_ai(content, {"subject": "New", "note": "Hi", "items": [
        {"key": "p0", "points": ["a shorter"]}, {"key": "zz", "points": ["invented"]}]})
    assert merged.subject == "New" and merged.note == "Hi"
    assert [i.points for i in merged.items] == [["a shorter"], ["b"]]


def test_draft_api_render_ai_and_expiry(mail, monkeypatch):
    profile = _profile()
    profile.ai_connection_id = "ai1"
    storage.save_profile(profile)
    preview = pipeline.run(profile, trigger="preview", send=False)
    did, content = preview.draft["id"], preview.draft["content"]
    c = TestClient(create_app("t"), headers={"Authorization": "Bearer t"})

    content["note"] = "Short day"
    r = c.post(f"/drafts/{did}/render", json={"content": content})
    assert r.status_code == 200 and "Short day" in r.json()["html"]

    class FakeAI:
        def edit_report(self, report, instruction):
            assert instruction == "shorter" and report["items"][0]["key"] == "p0"
            return {"items": [{"key": "p0", "points": ["Login fixed"]}]}

    monkeypatch.setattr(connectors, "ai_client", lambda conn, language: FakeAI())
    r = c.post(f"/drafts/{did}/ai", json={"content": content, "instruction": "shorter"})
    assert r.status_code == 200
    assert r.json()["content"]["items"][0]["points"] == ["Login fixed"]
    assert "Login fixed" in r.json()["html"]

    assert c.post(f"/drafts/{did}/ai", json={"content": content, "instruction": " "}).status_code == 400
    assert c.post("/drafts/nope/render", json={"content": content}).status_code == 404
