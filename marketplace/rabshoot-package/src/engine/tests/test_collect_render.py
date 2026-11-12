from datetime import date

import pytest

from rabshoot_engine import ai

from rabshoot_engine.mail.imap import ThreadParent, reply_all_recipients, reply_subject
from rabshoot_engine.models import CodeSource, Profile, SlackSelection
from rabshoot_engine.pipeline import EmailPlan, build_message
from rabshoot_engine.render import render
from rabshoot_engine.sources import github
from rabshoot_engine.window import DayWindow

WINDOW = DayWindow.for_day(date(2026, 9, 28), "UTC")


class FakeGitHub:
    def repos(self, max_pages=10):
        return [
            {"full_name": "acme/api", "html_url": "https://github.com/acme/api",
             "pushed_at": "2026-09-28T10:00:00Z", "updated_at": "2026-09-28T10:00:00Z"},
            {"full_name": "acme/old", "html_url": "https://github.com/acme/old",
             "pushed_at": "2025-01-01T00:00:00Z", "updated_at": "2025-01-01T00:00:00Z"},
        ]

    def branches(self, name):
        return [{"name": "main"}, {"name": "feature"}]

    def commits(self, name, since, until, sha=None):
        base = {"sha": "a" * 40, "html_url": "u", "parents": [{}], "author": {"login": "mo"},
                "commit": {"message": "Add login\n\nbody",
                           "author": {"name": "Mo", "email": "mo@x.com",
                                      "date": "2026-09-28T09:00:00Z"},
                           "committer": {"date": "2026-09-28T09:00:00Z"}}}
        merge = {**base, "sha": "b" * 40, "parents": [{}, {}]}
        return [base, merge]  # same commit on both branches → de-duplicated

    def commit(self, name, sha):
        return {"files": [{"filename": "src/auth.py", "status": "added",
                           "patch": "+def login():\n+    return True"}]}

    def pulls(self, name, since):
        return [{"number": 7, "title": "Login", "user": {"login": "mo"},
                 "created_at": "2026-09-28T08:00:00Z", "updated_at": "2026-09-28T11:00:00Z",
                 "merged_at": "2026-09-28T11:00:00Z", "closed_at": "2026-09-28T11:00:00Z",
                 "state": "closed", "html_url": "https://github.com/acme/api/pull/7",
                 "base": {"ref": "main"}}]

    def issues(self, name, since):
        return []


def test_github_collect_normalizes_and_dedupes():
    projects = github.collect(FakeGitHub(), CodeSource(connection_id="c"), WINDOW,
                              want_diffs=True, max_diff_chars=10_000)
    assert [p["name"] for p in projects] == ["acme/api"]
    p = projects[0]
    assert len(p["commits"]) == 1 and p["commits"][0]["title"] == "Add login"
    assert p["merge_requests"][0]["action"] == "merged"
    assert p["merge_requests"][0]["ref"] == "#7"
    assert "src/auth.py" in p["diff_text"]


def _data():
    projects = [{"source": "gitlab", "name": "acme / web", "url": "https://gitlab.com/acme/web",
                 "commits": [{"id": "1", "short_id": "abc", "title": "wip", "author": "Mo",
                              "url": "u", "created_at": ""}],
                 "merge_requests": [], "issues": [],
                 "files": [{"path": "a.py", "status": "modified", "added": 3, "removed": 1}],
                 "changes": ["[Major] Added payments API", "Fixed <script> escaping"]}]
    convs = [{"id": "C1", "name": "#tasks", "message_count": 2, "threads": [{}],
              "points": ["Ahmed will deploy tomorrow"]}]
    return projects, convs


def test_render_branded_email():
    projects, convs = _data()
    profile = Profile(slack=SlackSelection(connection_id="s", conversations=[{"id": "C1"}]))
    report = render(profile, WINDOW, projects, convs)
    assert report.subject == "Daily Report — 2026-09-28"
    assert "MAJOR" in report.html and "Added payments API" in report.html
    assert "&lt;script&gt;" in report.html  # escaped
    assert "Ahmed will deploy tomorrow" in report.text
    assert "Sent with" in report.html
    assert "cid:rabshoot-mark" not in report.html_for_display()


class _Resp:
    def __init__(self, status, body):
        self.status_code, self._body = status, body
        self.ok = status == 200
        self.text = str(body)

    def json(self):
        return self._body


def test_ai_outage_never_leaks_raw_messages(monkeypatch):
    monkeypatch.setattr(ai, "RETRY_WAITS", (0, 0))
    busy = [{"error": {"code": 503, "message": "This model is currently experiencing high demand."}}]
    calls = []
    client = ai.AIClient("key", model="m1", fallback_models=["m2"])
    monkeypatch.setattr(client.session, "post", lambda url, json, timeout: calls.append(json["model"]) or _Resp(503, busy))

    arabic = "تم رفع التحديث على السيرفر"
    conv = {"id": "C1", "name": "#tasks", "message_count": 1,
            "threads": [{"user": "Ahmed", "text": arabic, "time": "10:00", "date": "", "from_earlier": False,
                         "replies": []}]}
    stats = ai.enrich(client, [], [conv])
    assert stats["failed"] == 1 and conv["ai_failed"]
    assert calls == ["m1", "m2", "m1", "m2"]  # every model, every round
    assert "high demand" in stats["errors"][0]

    profile = Profile(slack=SlackSelection(connection_id="s", conversations=[{"id": "C1"}]))
    report = render(profile, WINDOW, [], [conv])
    assert arabic not in report.html and arabic not in report.text
    assert "AI summary was unavailable" in report.html

    calls.clear()
    with pytest.raises(RuntimeError):
        client.chat("again")
    assert calls == ["m1", "m2"]  # after an outage, later items fail fast


def test_ai_recovers_on_a_later_round(monkeypatch):
    monkeypatch.setattr(ai, "RETRY_WAITS", (0, 0))
    replies = iter([_Resp(503, {}), _Resp(200, {"choices": [{"message": {"content": '{"points": ["Deployed"]}'}}]})])
    client = ai.AIClient("key", model="m1", fallback_models=[])
    monkeypatch.setattr(client.session, "post", lambda url, json, timeout: next(replies))
    conv = {"id": "C1", "name": "#tasks", "message_count": 1,
            "threads": [{"user": "A", "text": "x", "time": "", "date": "", "from_earlier": False, "replies": []}]}
    assert ai.enrich(client, [], [conv])["ok"] == 1 and conv["points"] == ["Deployed"]


def test_message_has_thread_headers_and_inline_logo():
    projects, convs = _data()
    report = render(Profile(), WINDOW, projects, convs)
    parent = ThreadParent(message_id="<m1@x>", references="<m0@x>", subject="Daily Report",
                          reply_to=["boss@x.com"], to=["me@x.com", "team@x.com"], cc=["hr@x.com"])
    to, cc = reply_all_recipients(parent, "me@x.com")
    assert to == ["boss@x.com", "team@x.com"] and cc == ["hr@x.com"]
    plan = EmailPlan(sender="me@x.com", subject=reply_subject("RE: Re: Daily Report"),
                     to=to, cc=cc, bcc=[], parent=parent)
    msg = build_message(plan, report, "Mohamed")
    assert msg["Subject"] == "Re: Daily Report"
    assert msg["In-Reply-To"] == "<m1@x>" and msg["References"] == "<m0@x> <m1@x>"
    assert msg["From"] == "Mohamed <me@x.com>"
    types = [part.get_content_type() for part in msg.walk()]
    assert "text/plain" in types and "text/html" in types
    if report.branding and "cid:rabshoot-mark" in report.html:
        assert "image/png" in types
