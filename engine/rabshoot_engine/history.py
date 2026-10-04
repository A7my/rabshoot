"""SQLite run history; the rendered email of each run is kept as an HTML file."""

import json
import sqlite3
import threading
from contextlib import contextmanager

from . import paths
from .models import new_id, now_iso

_lock = threading.Lock()

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    profile_id TEXT NOT NULL,
    profile_name TEXT,
    trigger TEXT,
    report_day TEXT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    error TEXT,
    subject TEXT,
    recipients TEXT,
    steps TEXT,
    html_path TEXT,
    text_path TEXT
);
CREATE INDEX IF NOT EXISTS runs_profile ON runs(profile_id, started_at);
"""

_JSON_FIELDS = ("recipients", "steps")


@contextmanager
def _db():
    with _lock:
        conn = sqlite3.connect(paths.data_dir() / "history.db")
        conn.row_factory = sqlite3.Row
        try:
            conn.executescript(_SCHEMA)
            yield conn
            conn.commit()
        finally:
            conn.close()


def _row(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    item = dict(row)
    for key in _JSON_FIELDS:
        item[key] = json.loads(item[key]) if item.get(key) else []
    return item


def start_run(profile_id: str, profile_name: str, trigger: str, report_day: str) -> str:
    run_id = new_id("run")
    with _db() as db:
        db.execute(
            "INSERT INTO runs (id, profile_id, profile_name, trigger, report_day, started_at,"
            " status) VALUES (?, ?, ?, ?, ?, ?, 'running')",
            (run_id, profile_id, profile_name, trigger, report_day, now_iso()),
        )
    return run_id


def finish_run(run_id: str, status: str, *, error: str = "", subject: str = "",
               recipients: list[str] | None = None, steps: list[dict] | None = None,
               html: str = "", text: str = "") -> None:
    html_path = text_path = ""
    if html:
        html_path = str(paths.reports_dir() / f"{run_id}.html")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html)
    if text:
        text_path = str(paths.reports_dir() / f"{run_id}.md")
        with open(text_path, "w", encoding="utf-8") as f:
            f.write(text)
    with _db() as db:
        db.execute(
            "UPDATE runs SET finished_at=?, status=?, error=?, subject=?, recipients=?, steps=?,"
            " html_path=?, text_path=? WHERE id=?",
            (now_iso(), status, error, subject, json.dumps(recipients or []),
             json.dumps(steps or []), html_path, text_path, run_id),
        )


def list_runs(profile_id: str | None = None, limit: int = 100) -> list[dict]:
    with _db() as db:
        if profile_id:
            rows = db.execute("SELECT * FROM runs WHERE profile_id=? ORDER BY started_at DESC"
                              " LIMIT ?", (profile_id, limit)).fetchall()
        else:
            rows = db.execute("SELECT * FROM runs ORDER BY started_at DESC LIMIT ?",
                              (limit,)).fetchall()
    return [_row(r) for r in rows]


def get_run(run_id: str) -> dict | None:
    with _db() as db:
        return _row(db.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone())


def last_run(profile_id: str, statuses: tuple[str, ...] = ("sent",),
             triggers: tuple[str, ...] = ("schedule", "catch_up", "manual")) -> dict | None:
    marks = ",".join("?" * len(statuses))
    tmarks = ",".join("?" * len(triggers))
    with _db() as db:
        return _row(db.execute(
            f"SELECT * FROM runs WHERE profile_id=? AND status IN ({marks})"
            f" AND trigger IN ({tmarks}) ORDER BY started_at DESC LIMIT 1",
            (profile_id, *statuses, *triggers),
        ).fetchone())


def sent_for_day(profile_id: str, report_day: str) -> dict | None:
    """The first real (non-test) report already sent for that day, if any."""
    with _db() as db:
        return _row(db.execute(
            "SELECT * FROM runs WHERE profile_id=? AND report_day=? AND status='sent'"
            " AND trigger IN ('schedule','catch_up','manual') ORDER BY started_at LIMIT 1",
            (profile_id, report_day),
        ).fetchone())


def mark_interrupted() -> None:
    """Runs left 'running' by a crash or shutdown."""
    with _db() as db:
        db.execute("UPDATE runs SET status='failed', error='Interrupted (app closed)',"
                   " finished_at=? WHERE status='running'", (now_iso(),))
