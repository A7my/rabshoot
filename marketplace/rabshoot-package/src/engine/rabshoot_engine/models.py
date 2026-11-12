import re
import uuid
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from .window import normalize_days, parse_time

ConnectionType = Literal["email", "gitlab", "github", "slack", "ai"]
CODE_TYPES = ("gitlab", "github")

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

DEFAULT_IGNORE_MESSAGES = [
    "صباح الخير", "صباح النور", "مساء الخير", "مساء النور", "السلام عليكم", "وعليكم السلام",
    "ازيك", "عامل ايه", "اخبارك", "الحمد لله", "شكرا", "متشكر", "تسلم", "تمام", "ماشي",
    "اوكي", "حاضر", "good morning", "good evening", "hello", "hi", "hey", "thanks",
    "thank you", "ok", "okay", "great", "welcome",
]


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Connection(BaseModel):
    id: str = Field(default_factory=lambda: new_id("conn"))
    type: ConnectionType
    label: str = ""
    meta: dict = Field(default_factory=dict)
    created_at: str = Field(default_factory=now_iso)
    status: Literal["ok", "error", "unknown"] = "unknown"
    status_message: str = ""


class ThreadRef(BaseModel):
    subject: str = ""
    message_id: str = ""
    gm_thrid: str = ""
    participants: list[str] = Field(default_factory=list)


class Delivery(BaseModel):
    mode: Literal["recipients", "thread"] = "recipients"
    to: list[str] = Field(default_factory=list)
    cc: list[str] = Field(default_factory=list)
    bcc: list[str] = Field(default_factory=list)
    thread: ThreadRef | None = None
    reply_all: bool = True
    subject: str = "{title} — {date}"
    sender_name: str = ""

    @field_validator("to", "cc", "bcc")
    @classmethod
    def _emails(cls, value: list[str]) -> list[str]:
        cleaned = [v.strip() for v in value if v and v.strip()]
        bad = [v for v in cleaned if not _EMAIL.match(v)]
        if bad:
            raise ValueError(f"Invalid email address: {', '.join(bad)}")
        return list(dict.fromkeys(cleaned))


class CodeSource(BaseModel):
    connection_id: str
    projects: Literal["all"] | list[str] = "all"
    exclude: list[str] = Field(default_factory=list)
    authors: list[str] = Field(default_factory=list)
    include_merge_commits: bool = False


class ConversationRef(BaseModel):
    id: str
    name: str = ""


class SlackSelection(BaseModel):
    connection_id: str | None = None
    conversations: list[ConversationRef] = Field(default_factory=list)
    ignore_messages: list[str] = Field(default_factory=lambda: list(DEFAULT_IGNORE_MESSAGES))
    ignore_leftover_words: int = 2
    thread_lookback_days: int = 7
    include_bots: bool = False


class Schedule(BaseModel):
    # recurring: `time` on `days`; once: `time` on `once_date`; now: no schedule, sent by hand.
    mode: Literal["recurring", "once", "now"] = "recurring"
    time: str = "18:00"
    days: str = "sun-thu"
    once_date: str | None = None
    timezone: str = "UTC"
    catch_up: bool = True
    # Scheduled sends only: no GitLab/GitHub or Slack activity that day means no email.
    skip_empty: bool = True

    @field_validator("once_date")
    @classmethod
    def _once_date(cls, value: str | None) -> str | None:
        if not value:
            return None
        from datetime import date

        try:
            return date.fromisoformat(value.strip()).isoformat()
        except ValueError:
            raise ValueError(f"Invalid date {value!r}, expected YYYY-MM-DD")

    @model_validator(mode="after")
    def _once_needs_date(self) -> "Schedule":
        if self.mode == "once" and not self.once_date:
            raise ValueError("Pick the date for the one-time send")
        return self

    @field_validator("time")
    @classmethod
    def _time(cls, value: str) -> str:
        h, m = parse_time(value)
        return f"{h:02d}:{m:02d}"

    @field_validator("days")
    @classmethod
    def _days(cls, value: str) -> str:
        normalize_days(value)
        return value.strip().lower() or "*"

    @field_validator("timezone")
    @classmethod
    def _tz(cls, value: str) -> str:
        from zoneinfo import ZoneInfo

        try:
            ZoneInfo(value)
        except Exception:
            raise ValueError(f"Unknown timezone {value!r}")
        return value


class Sections(BaseModel):
    code_changes: bool = True
    commits: bool = False
    merge_requests: bool = True
    issues: bool = True
    slack: bool = True


class ReportOptions(BaseModel):
    title: str = "Daily Report"
    language: str = "English"
    extra_instructions: str = ""
    max_points: int = 6
    max_diff_chars_per_project: int = 20000
    max_items_per_section: int = 50
    sections: Sections = Field(default_factory=Sections)
    branding: bool = True


class Profile(BaseModel):
    id: str = Field(default_factory=lambda: new_id("prof"))
    name: str = "Daily report"
    enabled: bool = True
    sender_connection_id: str | None = None
    delivery: Delivery = Field(default_factory=Delivery)
    code_sources: list[CodeSource] = Field(default_factory=list)
    slack: SlackSelection = Field(default_factory=SlackSelection)
    ai_connection_id: str | None = None
    schedule: Schedule = Field(default_factory=Schedule)
    report: ReportOptions = Field(default_factory=ReportOptions)
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)

    @model_validator(mode="after")
    def _thread_needs_ref(self):
        if self.delivery.mode == "thread" and self.delivery.thread is None:
            self.delivery.thread = ThreadRef()
        return self


def profile_problems(profile: Profile, connections: dict[str, Connection]) -> list[str]:
    """Reasons a profile cannot run yet (the wizard's required steps)."""
    problems = []

    def conn(cid: str | None, *types: str) -> Connection | None:
        c = connections.get(cid or "")
        return c if c and c.type in types else None

    if not conn(profile.sender_connection_id, "email"):
        problems.append("sender")
    d = profile.delivery
    if d.mode == "recipients" and not d.to:
        problems.append("recipients")
    if d.mode == "thread" and not (d.thread and (d.thread.message_id or d.thread.subject
                                                 or d.thread.gm_thrid)):
        problems.append("thread")
    if not any(conn(s.connection_id, *CODE_TYPES) for s in profile.code_sources):
        problems.append("code_source")
    if profile.slack.connection_id and not conn(profile.slack.connection_id, "slack"):
        problems.append("slack")
    if not conn(profile.ai_connection_id, "ai"):
        problems.append("ai")
    return problems


class Settings(BaseModel):
    language: Literal["en", "ar"] = "en"
    autostart: bool = True
    catch_up_default: bool = True
    onboarding_done: bool = False
    paused: bool = False
    notifications: bool = True
