from datetime import datetime

from ..window import DayWindow


def parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def in_window(value: str | None, window: DayWindow) -> bool:
    dt = parse_ts(value)
    return dt is not None and window.start <= dt < window.end


def author_match(authors: set[str], *candidates: str | None) -> bool:
    return not authors or any(c and c.lower() in authors for c in candidates)
