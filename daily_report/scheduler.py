import logging
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from . import ai, delivery, gitlab_source, render, slack_source
from .config import DayWindow, load_config, normalize_days, parse_time

log = logging.getLogger(__name__)

REPORT_JOB = "daily_report"
WATCH_JOB = "config_watcher"


def build_report(cfg: dict, day: date | None = None) -> tuple[DayWindow, render.Report]:
    tz = cfg["schedule"].get("timezone", "UTC")
    window = DayWindow.for_day(day, tz) if day else DayWindow.today(tz)

    try:
        gitlab = gitlab_source.collect(cfg, window)
    except Exception as exc:
        log.exception("GitLab collection failed")
        gitlab = {"projects": [{"name": "GitLab", "url": cfg.get("gitlab", {}).get("url", ""),
                                "error": str(exc), "commits": [], "merge_requests": [],
                                "issues": []}]}
    try:
        slack = slack_source.collect(cfg, window)
    except Exception as exc:
        log.exception("Slack collection failed")
        slack = {"conversations": [{"id": "", "name": "Slack", "error": str(exc),
                                    "threads": [], "message_count": 0}]}

    try:
        ai.enrich(cfg, gitlab, slack)
    except Exception:
        log.exception("AI summarization failed, sending the raw report")

    return window, render.render(cfg, window, gitlab, slack)


def run_report(config_path: Path, day: date | None = None,
               dry_run: bool = False) -> render.Report:
    cfg = load_config(config_path)
    window, report = build_report(cfg, day)
    if dry_run:
        return report
    failures = delivery.deliver(cfg, window, report)
    if failures:
        log.error("Report for %s had delivery failures: %s", window.day, failures)
    return report


def make_trigger(cfg: dict) -> CronTrigger:
    sched = cfg["schedule"]
    hour, minute = parse_time(sched["time"])
    return CronTrigger(
        hour=hour,
        minute=minute,
        day_of_week=normalize_days(sched.get("days", "*")),
        timezone=sched.get("timezone", "UTC"),
    )


def _schedule_key(cfg: dict) -> tuple:
    s = cfg["schedule"]
    return s["time"], s.get("timezone", "UTC"), s.get("days", "*")


def serve(config_path: Path) -> None:
    cfg = load_config(config_path)
    scheduler = BlockingScheduler()
    state = {"mtime": config_path.stat().st_mtime, "key": _schedule_key(cfg)}

    scheduler.add_job(
        run_report,
        make_trigger(cfg),
        args=[config_path],
        id=REPORT_JOB,
        misfire_grace_time=3600,
        coalesce=True,
        max_instances=1,
    )

    def watch_config() -> None:
        try:
            mtime = config_path.stat().st_mtime
            if mtime == state["mtime"]:
                return
            state["mtime"] = mtime
            new_cfg = load_config(config_path)
        except Exception as exc:
            log.error("Ignoring invalid config change: %s", exc)
            return

        key = _schedule_key(new_cfg)
        if key != state["key"]:
            state["key"] = key
            job = scheduler.reschedule_job(REPORT_JOB, trigger=make_trigger(new_cfg))
            log.info("Schedule changed to %s %s (%s). Next run: %s", *key, job.next_run_time)
        else:
            log.info("Config reloaded (schedule unchanged)")

    interval = int(cfg["schedule"].get("reload_interval_seconds", 30))
    scheduler.add_job(watch_config, "interval", seconds=interval, id=WATCH_JOB)

    log.info("Scheduler started: %s %s (%s). Next run: %s", *state["key"], next_run(cfg))
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("Scheduler stopped")


def next_run(cfg: dict) -> datetime | None:
    tz = ZoneInfo(cfg["schedule"].get("timezone", "UTC"))
    return make_trigger(cfg).get_next_fire_time(None, datetime.now(tz))
