import base64
import re
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache

from jinja2 import Environment, FileSystemLoader
from markupsafe import Markup, escape

from .models import Profile
from .paths import resource_path
from .window import DayWindow

LOGO_CID = "rabshoot-mark"


@dataclass
class Report:
    title: str
    subject: str
    text: str
    html: str  # uses cid:rabshoot-mark for the logo when branding is on
    branding: bool
    stats: dict

    def html_for_display(self) -> str:
        """HTML with the logo inlined, for previews and history."""
        if not self.branding or not logo_bytes():
            return self.html
        uri = "data:image/png;base64," + base64.b64encode(logo_bytes()).decode()
        return self.html.replace(f"cid:{LOGO_CID}", uri)


@lru_cache
def logo_bytes() -> bytes:
    path = resource_path("assets", "mark.png")
    return path.read_bytes() if path.exists() else b""


def _oneline(text: str, limit: int = 300) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


_CODE = re.compile(r"`([^`\n]+)`")


def _codify(text: str) -> Markup:
    """Escape, then show `inline code` from AI bullets as code."""
    return Markup(_CODE.sub(
        r'<code style="background:#F0F2F7;border-radius:4px;padding:0 4px;'
        r'font-family:Consolas,monospace;font-size:12px;">\1</code>', str(escape(text))))


@lru_cache
def _env(html: bool) -> Environment:
    env = Environment(loader=FileSystemLoader(str(resource_path("templates"))), autoescape=html,
                      trim_blocks=True, lstrip_blocks=True, keep_trailing_newline=True)
    env.filters["oneline"] = _oneline
    env.filters["codify"] = _codify
    env.filters["nl2br"] = lambda text: Markup(str(escape(text)).replace("\n", "<br>"))
    return env


def build_context(profile: Profile, window: DayWindow, projects: list[dict],
                  conversations: list[dict]) -> dict:
    opts = profile.report
    stats = {
        "commits": sum(len(p["commits"]) for p in projects),
        "merge_requests": sum(len(p["merge_requests"]) for p in projects),
        "merged": sum(1 for p in projects for mr in p["merge_requests"] if mr["action"] == "merged"),
        "issues_closed": sum(1 for p in projects for i in p["issues"] if i["action"] == "closed"),
        "slack_messages": sum(c["message_count"] for c in conversations),
        "projects": sum(1 for p in projects if not p.get("error")),
        "changes": sum(len(p.get("changes") or []) for p in projects),
        "highlights": sum(len(c.get("points") or []) for c in conversations),
    }
    # Per item: AI output when it succeeded, raw data otherwise.
    ai_on = any("changes" in p for p in projects) or any("points" in c for c in conversations)
    active = [c for c in conversations
              if not c.get("error") and (c["points"] if "points" in c else c["threads"])]
    return {
        "title": opts.title,
        "date": window.day.strftime("%A %d %B %Y"),
        "date_iso": window.day.isoformat(),
        "generated_at": datetime.now(window.start.tzinfo).strftime("%Y-%m-%d %H:%M"),
        "sections": opts.sections.model_dump(),
        "max_items": opts.max_items_per_section,
        "projects": projects,
        "slack_enabled": bool(profile.slack.connection_id and profile.slack.conversations),
        "conversations": conversations,
        "active_conversations": active,
        "failed_conversations": [c for c in conversations if c.get("error")],
        "stats": stats,
        "ai": ai_on,
        "branding": opts.branding,
        "logo_src": f"cid:{LOGO_CID}" if opts.branding and logo_bytes() else "",
    }


def render(profile: Profile, window: DayWindow, projects: list[dict],
           conversations: list[dict], note: str = "", subject: str = "") -> Report:
    """note: the author's own text at the top; subject: an edited subject instead of the template."""
    context = build_context(profile, window, projects, conversations)
    context["note"] = note.strip()
    subject = subject.strip() or (profile.delivery.subject or "{title} — {date}").replace(
        "{title}", context["title"]).replace("{date}", context["date_iso"])
    return Report(
        title=context["title"],
        subject=subject,
        text=_env(False).get_template("report.md.j2").render(**context).strip() + "\n",
        html=_env(True).get_template("report.html.j2").render(**context).strip() + "\n",
        branding=profile.report.branding,
        stats=context["stats"],
    )
