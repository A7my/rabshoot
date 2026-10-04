from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from .config import DayWindow

DEFAULT_TEXT_TEMPLATE = "templates/daily_report.md.j2"
DEFAULT_EMAIL_TEMPLATE = "templates/daily_report_email.html.j2"


@dataclass
class Report:
    title: str
    subject: str
    text: str
    html: str


def _oneline(text: str, limit: int = 300) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _render(template: str, context: dict, html: bool) -> str:
    path = Path(template)
    env = Environment(
        loader=FileSystemLoader(str(path.parent)),
        autoescape=html,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )
    env.filters["oneline"] = _oneline
    return env.get_template(path.name).render(**context).strip() + "\n"


def build_context(cfg: dict, window: DayWindow, gitlab: dict, slack: dict) -> dict:
    report_cfg = cfg["report"]
    projects = gitlab.get("projects", [])
    conversations = slack.get("conversations", [])
    stats = {
        "commits": sum(len(p["commits"]) for p in projects),
        "merge_requests": sum(len(p["merge_requests"]) for p in projects),
        "merged": sum(1 for p in projects for mr in p["merge_requests"]
                      if mr["action"] == "merged"),
        "issues_closed": sum(1 for p in projects for i in p["issues"]
                             if i["action"] == "closed"),
        "slack_messages": sum(c["message_count"] for c in conversations),
        "projects": sum(1 for p in projects if not p.get("error")),
        "changes": sum(len(p.get("changes") or []) for p in projects),
        "highlights": sum(len(c.get("points") or []) for c in conversations),
    }
    sections = {
        "gitlab_changes": True,
        "gitlab_commits": False,
        "gitlab_merge_requests": True,
        "gitlab_issues": True,
        "slack_messages": True,
        **(report_cfg.get("sections") or {}),
    }
    # Per item: AI output when it succeeded, raw data otherwise.
    ai_on = any("changes" in p for p in projects) or any("points" in c for c in conversations)
    active = [c for c in conversations
              if not c.get("error") and (c["points"] if "points" in c else c["threads"])]
    return {
        "title": report_cfg.get("title", "Daily Report"),
        "date": window.day.strftime("%A %d %B %Y"),
        "date_iso": window.day.isoformat(),
        "generated_at": datetime.now(window.start.tzinfo).strftime("%Y-%m-%d %H:%M"),
        "sections": sections,
        "max_items": int(report_cfg.get("max_items_per_section", 50)),
        "gitlab": {"projects": projects},
        "slack": {"conversations": conversations, "active": active},
        "stats": stats,
        "ai": ai_on,
    }


def render(cfg: dict, window: DayWindow, gitlab: dict, slack: dict) -> Report:
    report_cfg = cfg["report"]
    context = build_context(cfg, window, gitlab, slack)
    email_cfg = (cfg.get("delivery") or {}).get("email") or {}
    subject = str(email_cfg.get("subject") or "{title} — {date}").format(
        title=context["title"], date=context["date_iso"]
    )
    return Report(
        title=context["title"],
        subject=subject,
        text=_render(report_cfg.get("template", DEFAULT_TEXT_TEMPLATE), context, html=False),
        html=_render(report_cfg.get("email_template", DEFAULT_EMAIL_TEMPLATE), context,
                     html=True),
    )
