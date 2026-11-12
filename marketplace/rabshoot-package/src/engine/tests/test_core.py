import os
import stat
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from rabshoot_engine import history, storage
from rabshoot_engine.models import (CodeSource, Connection, Delivery, Profile, Schedule,
                                    ThreadRef, profile_problems)
from rabshoot_engine.scheduler import previous_fire
from rabshoot_engine.sources.diffutil import FileDiff, combine, mask_secrets
from rabshoot_engine.sources.slack import SmallTalkFilter, manifest_url
from rabshoot_engine.window import DayWindow, normalize_days


def test_normalize_days_wraps():
    assert normalize_days("sun-thu") == "sun,mon,tue,wed,thu"
    assert normalize_days("mon-fri") == "mon,tue,wed,thu,fri"
    assert normalize_days("*") == "*"
    with pytest.raises(ValueError):
        normalize_days("funday")


def test_schedule_validation():
    assert Schedule(time="9:05").time == "09:05"
    with pytest.raises(ValidationError):
        Schedule(time="25:00")
    with pytest.raises(ValidationError):
        Schedule(timezone="Mars/Olympus")


def test_delivery_rejects_bad_email():
    with pytest.raises(ValidationError):
        Delivery(to=["not-an-email"])
    assert Delivery(to=["a@b.co", "a@b.co", " "]).to == ["a@b.co"]


def test_profile_problems_required_steps():
    email = Connection(type="email", meta={"address": "me@x.com"})
    gl = Connection(type="gitlab")
    ai = Connection(type="ai")
    conns = {c.id: c for c in (email, gl, ai)}
    p = Profile()
    assert set(profile_problems(p, conns)) == {"sender", "recipients", "code_source", "ai"}
    p.sender_connection_id = email.id
    p.delivery = Delivery(mode="thread", thread=ThreadRef(subject="Daily"))
    p.code_sources = [CodeSource(connection_id=gl.id)]
    p.ai_connection_id = ai.id
    assert profile_problems(p, conns) == []


def test_storage_roundtrip_and_private_secret_file(isolated_home):
    conn = storage.save_connection(Connection(type="ai", label="Gemini"), {"key": "abc"})
    assert storage.get_secret(conn.id) == {"key": "abc"}
    secret_file = isolated_home / "config" / "secrets.json"
    if os.name == "posix":
        assert stat.S_IMODE(secret_file.stat().st_mode) == 0o600
    assert "abc" not in (isolated_home / "config" / "connections.json").read_text()

    profile = storage.save_profile(Profile(name="Team"))
    assert storage.get_profile(profile.id).name == "Team"
    storage.delete_connection(conn.id)
    assert storage.get_secret(conn.id) == {}
    storage.delete_profile(profile.id)
    assert storage.list_profiles() == []


def test_history_records_runs():
    run_id = history.start_run("prof_1", "Team", "manual", "2026-09-28")
    history.finish_run(run_id, "sent", subject="S", recipients=["a@b.co"],
                       steps=[{"key": "email", "status": "ok", "message": "x"}], html="<p>x</p>")
    run = history.get_run(run_id)
    assert run["status"] == "sent" and run["recipients"] == ["a@b.co"]
    assert open(run["html_path"], encoding="utf-8").read() == "<p>x</p>"
    assert history.last_run("prof_1")["id"] == run_id


def test_small_talk_filter():
    f = SmallTalkFilter(["صباح الخير", "عامل ايه", "thanks", "تمام"], leftover_words=2)
    assert f.is_small_talk("صباح الخير 🌞")
    assert f.is_small_talk("صباح الخير يا احمد")
    assert f.is_small_talk("Thanks!")
    assert not f.is_small_talk("تمام هخلص الـ API النهارده بليل")
    assert not f.is_small_talk("Deployed the payment fix to staging")


def test_diff_masks_secrets_and_skips_env():
    text, files = combine([("abc123", [
        FileDiff(".env", "modified", "+API_KEY=supersecret"),
        FileDiff("app/config.py", "modified", '+token = "hunter2"\n+x = 1'),
    ])], max_chars=10_000)
    assert "supersecret" not in text and "hunter2" not in text
    assert ".env" not in text and "app/config.py" in text
    assert {f["path"] for f in files} == {".env", "app/config.py"}
    assert mask_secrets("password: abc") == "password: ***"


def test_previous_fire_for_catch_up():
    p = Profile(schedule=Schedule(time="18:00", days="*", timezone="Africa/Cairo"))
    now = datetime(2026, 9, 28, 9, 0, tzinfo=ZoneInfo("Africa/Cairo"))
    missed = previous_fire(p, now, timedelta(hours=20))
    assert missed and missed.hour == 18 and missed.date() == date(2026, 9, 27)
    assert previous_fire(p, now.replace(hour=17), timedelta(hours=2)) is None


def test_manifest_url_is_prefilled():
    url = manifest_url()
    assert url.startswith("https://api.slack.com/apps?new_app=1&manifest_json=")
    assert "channels%3Ahistory" in url


def test_day_window_timezone():
    w = DayWindow.for_day(date(2026, 9, 28), "Africa/Cairo")
    assert w.end - w.start == timedelta(days=1)
    assert w.start.utcoffset() == timedelta(hours=3)
