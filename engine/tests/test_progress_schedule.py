from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from rabshoot_engine import history, pipeline, storage
from rabshoot_engine.models import Profile, Schedule
from rabshoot_engine.scheduler import Scheduler


def test_progress_moves_forward_and_expires(monkeypatch):
    tracker = pipeline.Progress("p1", "manual", sending=True)
    tracker.update("code", 1, 4, "group/api", share=(0, 2))
    snap = pipeline.progress("p1")
    assert snap["stage"] == "code" and (snap["current"], snap["total"]) == (2, 4)
    assert 5 < snap["percent"] < 25 and snap["item"] == "group/api"

    tracker.update("code", 0, 0, share=(0, 2))  # never goes backwards
    assert pipeline.progress("p1")["percent"] == snap["percent"]

    tracker.update("ai", 2, 4, "Payments")
    assert 58 < pipeline.progress("p1")["percent"] < 88
    tracker.finish("sent")
    assert pipeline.progress("p1")["percent"] == 100

    monkeypatch.setattr(pipeline, "FINISHED_VISIBLE_SECONDS", 0)
    assert pipeline.progress("p1") is None


def test_run_reports_live_stages(monkeypatch):
    seen = []
    profile = storage.save_profile(Profile(name="Team"))
    monkeypatch.setattr(pipeline, "profile_problems", lambda p, c: [])

    def fake_build(p, day, tracker):
        for stage in ("code", "slack", "ai", "render"):
            tracker.update(stage)
            seen.append(pipeline.progress(p.id)["stage"])
        raise RuntimeError("stop here")

    monkeypatch.setattr(pipeline, "build", fake_build)
    result = pipeline.run(profile, trigger="preview", send=False)
    assert seen == ["code", "slack", "ai", "render"]
    assert result.status == "failed"
    final = pipeline.progress(profile.id)
    assert final["status"] == "failed" and final["error"] == "stop here" and final["run_id"]


def _daily_profile() -> Profile:
    return storage.save_profile(Profile(name="Team", schedule=Schedule(
        time="18:00", days="*", timezone="Africa/Cairo")))


def test_early_manual_send_skips_todays_scheduled_send(monkeypatch):
    profile = _daily_profile()
    sched = Scheduler()
    sched.start(catch_up=False)
    try:
        before = sched.upcoming(profile)
        nxt = datetime.fromisoformat(before["next_run"])
        assert before["skipped_run"] is None

        run_id = history.start_run(profile.id, profile.name, "manual", nxt.date().isoformat())
        history.finish_run(run_id, "sent")
        after = sched.upcoming(profile)
        assert after["skipped_run"]["run_id"] == run_id
        assert datetime.fromisoformat(after["next_run"]).date() == nxt.date() + timedelta(days=1)

        today = datetime.now(ZoneInfo("Africa/Cairo")).date().isoformat()
        run_id = history.start_run(profile.id, profile.name, "manual", today)
        history.finish_run(run_id, "sent")
        calls = []
        monkeypatch.setattr(pipeline, "run", lambda *a, **k: calls.append(k))
        sched._fire(profile.id, trigger="schedule")
        assert calls == []
    finally:
        sched.shutdown()


def test_test_sends_and_failures_do_not_skip_the_schedule(monkeypatch):
    profile = _daily_profile()
    today = datetime.now(ZoneInfo("Africa/Cairo")).date().isoformat()
    for trigger, status in (("test", "sent"), ("manual", "failed"), ("preview", "previewed")):
        history.finish_run(history.start_run(profile.id, profile.name, trigger, today), status)
    calls = []
    monkeypatch.setattr(pipeline, "run", lambda p, **k: calls.append(k) or pipeline.RunResult())
    Scheduler()._fire(profile.id, trigger="schedule")
    assert calls and calls[0]["trigger"] == "schedule"
