import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

_TIME_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")
DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def parse_time(value: str) -> tuple[int, int]:
    m = _TIME_RE.match(str(value).strip())
    if not m:
        raise ValueError(f"Invalid time {value!r}, expected HH:MM (24h)")
    return int(m.group(1)), int(m.group(2))


def normalize_days(value: str) -> str:
    """Expand wrap-around ranges like "sun-thu", which APScheduler rejects."""
    value = str(value or "*").strip().lower()
    if value in ("*", ""):
        return "*"
    out = []
    for part in value.split(","):
        part = part.strip()
        if "-" in part:
            first, last = (p.strip() for p in part.split("-", 1))
            if first not in DAYS or last not in DAYS:
                raise ValueError(f"Invalid day range {part!r}")
            i, j = DAYS.index(first), DAYS.index(last)
            out.extend(DAYS[i:j + 1] if i <= j else DAYS[i:] + DAYS[:j + 1])
        elif part in DAYS:
            out.append(part)
        else:
            raise ValueError(f"Invalid day {part!r}, use mon..sun")
    return ",".join(dict.fromkeys(out))


@dataclass(frozen=True)
class DayWindow:
    """A calendar day in the report timezone, as aware datetimes [start, end)."""

    day: date
    start: datetime
    end: datetime

    @classmethod
    def for_day(cls, day: date, tz_name: str) -> "DayWindow":
        start = datetime.combine(day, time.min, tzinfo=ZoneInfo(tz_name))
        return cls(day=day, start=start, end=start + timedelta(days=1))

    @classmethod
    def today(cls, tz_name: str) -> "DayWindow":
        return cls.for_day(datetime.now(ZoneInfo(tz_name)).date(), tz_name)
