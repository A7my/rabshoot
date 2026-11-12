from datetime import datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from rabshoot_engine import connectors, history, pipeline, storage
from rabshoot_engine.mail import smtp
from rabshoot_engine.models import Profile, Schedule
from rabshoot_engine.scheduler import Scheduler

ME = "me@x.com"
ACTIVE_CONV = {"name": "#team", "threads": [{}], "message_count": 3}


@pytest.fixture
def sends(monkeypatch):
    """Fakes collection, AI, rendering and SMTP; returns the list of sent messages."""
    sent = []
    monkeypatch.setattr(pipeline, "profile_problems", lambda p, c: [])
    monkeypatch.setattr(storage, "get_connection", lambda cid: None)
    monkeypatch.setattr(connectors, "email_credentials", lambda c: ({"address": ME}, "x"))
    monkeypatch.setattr(pipeline, "plan_email", lambda *a, **k: pipeline.EmailPlan(
        sender=ME, subject="Daily", to=["team@x.com"], cc=[], bcc=[]))
    monkeypatch.setattr(pipeline, "summarize", lambda *a, **k: None)
    monkeypatch.setattr(pipeline, "render", lambda *a: SimpleNamespace(
        subject="Daily", html_for_display=lambda: "", text="",
        stats={"projects": 0, "slack_messages": 0}))
    monkeypatch.setattr(pipeline, "build_message", lambda *a: "msg")
    monkeypatch.setattr(smtp, "send", lambda meta, pw, msg, to: sent.append(to))
    monkeypatch.setattr(pipeline, "collect_code", lambda *a: [])
    monkeypatch.setattr(pipeline, "collect_slack", lambda *a: [])
    return sent


def _profile(**schedule) -> Profile:
    schedule = {"time": "18:00", "days": "*", "timezone": "Africa/Cairo", **schedule}
    return storage.save_profile(Profile(name="Team", schedule=Schedule(**schedule)))


def test_scheduled_send_is_skipped_on_a_quiet_day(sends):
    result = pipeline.run(_profile(), trigger="schedule")
    assert result.status == "skipped" and not sends
    assert history.get_run(result.run_id)["status"] == "skipped"


def test_scheduled_send_goes_out_when_there_is_activity(sends, monkeypatch):
    monkeypatch.setattr(pipeline, "collect_slack", lambda *a: [ACTIVE_CONV])
    assert pipeline.run(_profile(), trigger="schedule").status == "sent" and sends


def test_manual_and_opted_out_sends_ignore_the_quiet_day_rule(sends):
    assert pipeline.run(_profile(), trigger="manual").status == "sent"
    assert pipeline.run(_profile(skip_empty=False), trigger="schedule").status == "sent"
    assert len(sends) == 2


def test_quiet_day_with_a_broken_source_fails_instead_of_skipping(sends, monkeypatch):
    def broken(profile, window, result, tracker=None):
        result.step("code", "error", "GitLab: token expired")
        return []

    monkeypatch.setattr(pipeline, "collect_code", broken)
    result = pipeline.run(_profile(), trigger="schedule")
    assert result.status == "failed" and "token expired" in result.error and not sends


def test_preview_warns_about_a_quiet_day(sends):
    result = pipeline.run(_profile(), trigger="preview", send=False)
    assert result.status == "previewed"
    assert any(s["status"] == "warn" and "skipped" in s["message"] for s in result.steps)


def test_skipped_day_is_not_caught_up_again(sends, monkeypatch):
    at = datetime.now(ZoneInfo("Africa/Cairo")) - timedelta(hours=2)
    profile = _profile(mode="once", once_date=at.date().isoformat(), time=at.strftime("%H:%M"))
    fired = []
    sched = Scheduler()
    monkeypatch.setattr(sched, "_fire", lambda pid, **k: fired.append(k))
    sched.catch_up()
    assert len(fired) == 1
    pipeline.run(profile, trigger="catch_up", day=fired[0]["day"])
    fired.clear()
    sched.catch_up()
    assert not fired
