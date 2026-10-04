"""One APScheduler job per enabled profile; re-synced whenever config changes."""

import logging
import threading
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

from . import history, pipeline, storage
from .models import Profile
from .window import normalize_days, parse_time

log = logging.getLogger(__name__)


def once_moment(profile: Profile) -> datetime | None:
    s = profile.schedule
    if s.mode != "once" or not s.once_date:
        return None
    hour, minute = parse_time(s.time)
    return datetime.combine(date.fromisoformat(s.once_date), time(hour, minute),
                            tzinfo=ZoneInfo(s.timezone))


def make_trigger(profile: Profile) -> CronTrigger | DateTrigger:
    s = profile.schedule
    if s.mode == "once":
        return DateTrigger(run_date=once_moment(profile))
    if s.mode == "now":
        raise ValueError("This report has no schedule")
    hour, minute = parse_time(s.time)
    return CronTrigger(day_of_week=normalize_days(s.days), hour=hour, minute=minute,
                       timezone=ZoneInfo(s.timezone))


def previous_fire(profile: Profile, now: datetime, within: timedelta) -> datetime | None:
    """Latest scheduled time in (now - within, now]."""
    if profile.schedule.mode == "now":
        return None
    if profile.schedule.mode == "once":
        moment = once_moment(profile)
        return moment if now - within < moment <= now else None
    trigger = make_trigger(profile)
    cursor, last = now - within, None
    while True:
        nxt = trigger.get_next_fire_time(last, cursor)
        if not nxt or nxt > now:
            return last
        last, cursor = nxt, nxt + timedelta(seconds=1)


class Scheduler:
    def __init__(self):
        self.sched = BackgroundScheduler(job_defaults={"misfire_grace_time": 3600,
                                                       "coalesce": True, "max_instances": 1})
        self._lock = threading.Lock()
        self.on_run_finished = None  # callback(profile, result)

    def start(self, catch_up: bool = True) -> None:
        history.mark_interrupted()
        self.sched.start()
        self.sync()
        storage.on_change(self.sync)
        if catch_up:
            threading.Thread(target=self.catch_up, daemon=True).start()

    def shutdown(self) -> None:
        if self.sched.running:
            self.sched.shutdown(wait=False)

    def sync(self) -> None:
        with self._lock:
            paused = storage.get_settings().paused
            wanted = {}
            now = datetime.now().astimezone()
            for p in storage.list_profiles():
                if not p.enabled or paused or p.schedule.mode == "now":
                    continue
                # A past one-time send is either done or left to catch_up, never re-armed here.
                if p.schedule.mode == "once" and once_moment(p) <= now:
                    continue
                wanted[p.id] = p
            for job in self.sched.get_jobs():
                if job.id not in wanted:
                    job.remove()
            for pid, profile in wanted.items():
                try:
                    trigger = make_trigger(profile)
                except Exception as exc:
                    log.error("Bad schedule for %s: %s", profile.name, exc)
                    continue
                job = self.sched.get_job(pid)
                s = profile.schedule
                signature = f"{s.mode}|{s.time}|{s.days}|{s.once_date}|{s.timezone}"
                if job and job.kwargs.get("signature") == signature:
                    continue
                self.sched.add_job(self._fire, trigger, id=pid, replace_existing=True,
                                   kwargs={"profile_id": pid, "signature": signature,
                                           "trigger": "schedule"})
                log.info("Scheduled '%s' at %s (%s)", profile.name, s.time,
                         f"once on {s.once_date}" if s.mode == "once" else s.days)

    def _fire(self, profile_id: str, trigger: str = "schedule", signature: str = "",
              day=None) -> None:
        try:
            profile = storage.get_profile(profile_id)
        except KeyError:
            return
        if trigger != "manual" and (not profile.enabled or storage.get_settings().paused):
            return
        if trigger == "schedule":
            today = datetime.now(ZoneInfo(profile.schedule.timezone)).date().isoformat()
            early = history.sent_for_day(profile.id, today)
            if early:
                log.info("Skipping scheduled '%s': today's report was already sent at %s",
                         profile.name, early["started_at"])
                return
        try:
            result = pipeline.run(profile, trigger=trigger, day=day)
        except pipeline.ProfileBusy:
            return
        log.info("Profile '%s' finished: %s %s", profile.name, result.status, result.error)
        if self.on_run_finished:
            try:
                self.on_run_finished(profile, result)
            except Exception:
                log.exception("run callback failed")

    def catch_up(self) -> None:
        """Send reports whose scheduled time passed while the app was not running."""
        if storage.get_settings().paused:
            return
        for profile in storage.list_profiles():
            if not (profile.enabled and profile.schedule.catch_up):
                continue
            tz = ZoneInfo(profile.schedule.timezone)
            now = datetime.now(tz)
            missed = previous_fire(profile, now, timedelta(hours=20))
            if not missed or now - missed < timedelta(minutes=1):
                continue
            last = history.last_run(profile.id, statuses=("sent", "skipped"))
            if last and last["report_day"] and last["report_day"] >= missed.date().isoformat():
                continue
            log.info("Catching up missed report '%s' (%s)", profile.name, missed)
            self._fire(profile.id, trigger="catch_up", day=missed.date())

    def next_runs(self) -> dict[str, str | None]:
        out = {}
        for job in self.sched.get_jobs():
            out[job.id] = job.next_run_time.isoformat() if job.next_run_time else None
        return out

    def upcoming(self, profile: Profile) -> dict:
        """Next send that will really happen, plus today's send skipped by an early one."""
        job = self.sched.get_job(profile.id) if self.sched.running else None
        nxt = job.next_run_time if job else None
        skipped = None
        if nxt:
            day = nxt.astimezone(ZoneInfo(profile.schedule.timezone)).date().isoformat()
            early = history.sent_for_day(profile.id, day)
            if early:
                skipped = {"at": nxt.isoformat(), "sent_at": early["started_at"],
                           "run_id": early["id"]}
                nxt = make_trigger(profile).get_next_fire_time(nxt, nxt + timedelta(seconds=1))
        return {"next_run": nxt.isoformat() if nxt else None, "skipped_run": skipped}

    def run_now(self, profile_id: str, trigger: str = "manual", day=None) -> None:
        threading.Thread(target=self._fire, kwargs={"profile_id": profile_id, "trigger": trigger,
                                                    "day": day}, daemon=True).start()
