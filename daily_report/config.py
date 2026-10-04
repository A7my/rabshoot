import os
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

DEFAULT_CONFIG_PATH = Path(os.environ.get("REPORT_CONFIG", "config.yaml"))

_TIME_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> dict:
    with open(path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    validate(cfg)
    return cfg


def update_schedule(path: Path = DEFAULT_CONFIG_PATH, **values: str) -> dict:
    """Rewrite keys under `schedule:` in place, keeping the file's comments intact."""
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    in_schedule, pending = False, dict(values)
    for idx, line in enumerate(lines):
        if re.match(r"^\S", line):
            in_schedule = line.startswith("schedule:")
            continue
        if not in_schedule:
            continue
        m = re.match(r"^(\s+)(\w+):(\s*)(\"[^\"]*\"|'[^']*'|[^#\n]*?)(\s*#.*)?$",
                     line.rstrip("\n"))
        if m and m.group(2) in pending:
            indent, key, sep, _, comment = m.groups()
            lines[idx] = f'{indent}{key}:{sep or " "}"{pending.pop(key)}"{comment or ""}\n'
    if pending:
        raise KeyError(f"Keys not found under schedule: {', '.join(pending)}")

    new_text = "".join(lines)
    cfg = yaml.safe_load(new_text)
    validate(cfg)
    path.write_text(new_text, encoding="utf-8")
    return cfg


def parse_time(value: str) -> tuple[int, int]:
    m = _TIME_RE.match(str(value).strip())
    if not m:
        raise ValueError(f"Invalid time {value!r}, expected HH:MM (24h)")
    return int(m.group(1)), int(m.group(2))


_DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def normalize_days(value: str) -> str:
    """Expand wrap-around ranges like "sun-thu", which APScheduler rejects."""
    value = str(value or "*").strip().lower()
    if value == "*":
        return value
    out = []
    for part in value.split(","):
        part = part.strip()
        if "-" in part:
            first, last = (p.strip() for p in part.split("-", 1))
            if first not in _DAYS or last not in _DAYS:
                raise ValueError(f"Invalid day range {part!r}")
            i, j = _DAYS.index(first), _DAYS.index(last)
            span = _DAYS[i:j + 1] if i <= j else _DAYS[i:] + _DAYS[:j + 1]
            out.extend(span)
        elif part in _DAYS:
            out.append(part)
        else:
            raise ValueError(f"Invalid day {part!r}, use mon..sun")
    return ",".join(dict.fromkeys(out))


def validate(cfg: dict) -> None:
    sched = cfg.get("schedule") or {}
    parse_time(sched.get("time", ""))
    ZoneInfo(sched.get("timezone", "UTC"))
    normalize_days(sched.get("days", "*"))
    if "report" not in cfg:
        raise ValueError("Missing 'report' section in config")


@dataclass(frozen=True)
class DayWindow:
    """A calendar day in the report timezone, as aware datetimes [start, end)."""

    day: date
    start: datetime
    end: datetime

    @classmethod
    def for_day(cls, day: date, tz_name: str) -> "DayWindow":
        tz = ZoneInfo(tz_name)
        start = datetime.combine(day, time.min, tzinfo=tz)
        return cls(day=day, start=start, end=start + timedelta(days=1))

    @classmethod
    def today(cls, tz_name: str) -> "DayWindow":
        return cls.for_day(datetime.now(ZoneInfo(tz_name)).date(), tz_name)
