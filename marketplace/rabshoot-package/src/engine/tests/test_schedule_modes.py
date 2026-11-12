from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from rabshoot_engine import history, pipeline, storage
from rabshoot_engine.models import Profile, Schedule
from rabshoot_engine.scheduler import Scheduler, previous_fire

TZ = "Africa/Cairo"


def _once(at: datetime, **kw) -> Profile:
    return storage.save_profile(Profile(name="Once", schedule=Schedule(
        mode="once", once_date=at.date().isoformat(), time=at.strftime("%H:%M"), timezone=TZ, **kw)))


def test_once_requires_a_valid_date():
    with pytest.raises(ValidationError):
        Schedule(mode="once")
    with pytest.raises(ValidationError):
        Schedule(mode="once", once_date="2026-13-40")
    assert Schedule(mode="now").mode == "now"


def test_once_in_the_future_is_scheduled_exactly_once():
    at = (datetime.now(ZoneInfo(TZ)) + timedelta(days=2)).replace(second=0, microsecond=0)
    profile = _once(at)
    sched = Scheduler()
    sched.start(catch_up=False)
    try:
        nxt = datetime.fromisoformat(sched.upcoming(profile)["next_run"])
        assert nxt == at
    finally:
        sched.shutdown()


def test_now_mode_and_past_once_have_no_job():
    past = _once(datetime.now(ZoneInfo(TZ)) - timedelta(hours=2))
    manual = storage.save_profile(Profile(name="Manual", schedule=Schedule(mode="now", timezone=TZ)))
    sched = Scheduler()
    sched.start(catch_up=False)
    try:
        assert sched.upcoming(past)["next_run"] is None
        assert sched.upcoming(manual)["next_run"] is None
    finally:
        sched.shutdown()


def test_missed_once_is_caught_up_but_never_twice(monkeypatch):
    at = datetime.now(ZoneInfo(TZ)) - timedelta(hours=2)
    profile = _once(at)
    assert previous_fire(profile, datetime.now(ZoneInfo(TZ)), timedelta(hours=20)) is not None
    calls = []

    def fake_run(p, trigger, day=None):
        calls.append(trigger)
        run_id = history.start_run(p.id, p.name, trigger, day.isoformat())
        history.finish_run(run_id, "sent")
        return pipeline.RunResult(status="sent")

    monkeypatch.setattr(pipeline, "run", fake_run)
    sched = Scheduler()
    sched.catch_up()
    sched.catch_up()
    assert calls == ["catch_up"]


def test_now_mode_is_never_caught_up(monkeypatch):
    storage.save_profile(Profile(name="Manual", schedule=Schedule(mode="now", timezone=TZ)))
    monkeypatch.setattr(pipeline, "run", lambda *a, **k: pytest.fail("must not send"))
    Scheduler().catch_up()
