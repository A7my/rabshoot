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


def editable_text(profile: Profile, window: DayWindow, projects: list[dict],
                  conversations: list[dict]) -> str:
    """The report body as plain text the author can edit (format: see parse_blocks)."""
    context = build_context(profile, window, projects, conversations)
    text = _env(False).get_template("report.edit.j2").render(**context)
    return re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"


_HEADING_COLORS = ("#2F7BFF", "#7C3AED", "#10B981", "#F59E0B")
_BULLET = re.compile(r"^\s*[•\-*]\s+")


def parse_blocks(body: str) -> list[dict]:
    """'## ' section heading, '### ' project or chat name, '• '/'- ' bullet, anything else a paragraph."""
    blocks: list[dict] = []
    sections = 0
    for raw in body.splitlines():
        line = raw.strip()
        last = blocks[-1] if blocks else None
        if not line:
            if last and last["type"] == "p":
                last["closed"] = True
            continue
        if line.startswith("### "):
            blocks.append({"type": "h3", "text": line[4:].strip()})
        elif line.startswith("## ") or line.startswith("# "):
            blocks.append({"type": "h2", "text": line.lstrip("#").strip(),
                           "color": _HEADING_COLORS[sections % len(_HEADING_COLORS)]})
            sections += 1
        elif _BULLET.match(line):
            item = _BULLET.sub("", line)
            if last and last["type"] == "list":
                last["items"].append(item)
            else:
                blocks.append({"type": "list", "items": [item]})
        elif last and last["type"] == "p" and not last.get("closed"):
            last["lines"].append(line)
        else:
            blocks.append({"type": "p", "lines": [line]})
    return blocks


def _plain(body: str) -> str:
    lines = []
    for raw in body.strip().splitlines():
        line = raw.strip()
        if line.startswith("### "):
            line = line[4:].strip()
        elif line.startswith("#"):
            line = line.lstrip("#").strip().upper()
        lines.append(line)
    return "\n".join(lines)


def render(profile: Profile, window: DayWindow, projects: list[dict],
           conversations: list[dict], subject: str = "", body: str | None = None) -> Report:
    """subject: an edited subject instead of the template; body: edited text shown instead of the
    generated sections (header, numbers and footer stay)."""
    context = build_context(profile, window, projects, conversations)
    subject = subject.strip() or (profile.delivery.subject or "{title} — {date}").replace(
        "{title}", context["title"]).replace("{date}", context["date_iso"])
    if body is not None:
        context.update(blocks=parse_blocks(body), ai=False,
                       show_stats=any(context["stats"][k] for k in
                                      ("projects", "commits", "merged", "slack_messages")))
        footer = "\n\n— Sent with RabShoot\n" if context["branding"] else "\n"
        text = f"{context['title']} — {context['date']}\n\n{_plain(body)}{footer}"
    else:
        text = _env(False).get_template("report.md.j2").render(**context).strip() + "\n"
    return Report(
        title=context["title"],
        subject=subject,
        text=text,
        html=_env(True).get_template("report.html.j2").render(**context).strip() + "\n",
        branding=profile.report.branding,
        stats=context["stats"],
    )
