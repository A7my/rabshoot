import logging
import os
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import make_msgid
from pathlib import Path

from .config import DayWindow
from .email_thread import ThreadParent, find_parent, reply_all_recipients, reply_subject
from .render import Report
from .slack_source import SlackClient, reader_client

log = logging.getLogger(__name__)

# Slack rejects messages above ~40k chars; stay well under and split on lines.
_SLACK_CHUNK = 3500


def _chunks(text: str, size: int) -> list[str]:
    parts, current = [], ""
    for line in text.splitlines(keepends=True):
        if len(current) + len(line) > size and current:
            parts.append(current)
            current = ""
        current += line
    if current:
        parts.append(current)
    return parts


def parse_addresses(value) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        value = value.split(",")
    return [a.strip() for a in value if a and a.strip()]


def to_slack(cfg: dict, report: Report) -> None:
    reader = reader_client()
    channel, _ = reader.resolve(cfg["channel"])
    bot_token = os.environ.get("SLACK_BOT_TOKEN")
    poster = SlackClient(bot_token) if bot_token else reader
    for part in _chunks(report.text, _SLACK_CHUNK):
        poster.post_message(channel, part)


def smtp_connection(cfg: dict) -> smtplib.SMTP:
    host, port = cfg["smtp_host"], int(cfg.get("smtp_port", 587))
    if port == 465:
        smtp = smtplib.SMTP_SSL(host, port, timeout=30)
    else:
        smtp = smtplib.SMTP(host, port, timeout=30)
        smtp.starttls()
    if os.environ.get("SMTP_USER"):
        smtp.login(os.environ["SMTP_USER"], os.environ.get("SMTP_PASSWORD", ""))
    return smtp


@dataclass
class EmailPlan:
    sender: str
    subject: str
    to: list[str]
    cc: list[str]
    bcc: list[str]
    parent: ThreadParent | None = None


def _merge(*lists: list[str]) -> list[str]:
    return list({a.lower(): a for lst in lists for a in lst}.values())


def plan_email(cfg: dict, subject: str) -> EmailPlan:
    """Work out subject and recipients, replying inside a thread when configured."""
    to, cc, bcc = (parse_addresses(cfg.get(k)) for k in ("to", "cc", "bcc"))
    sender = cfg.get("sender") or os.environ.get("SMTP_USER")
    if not sender:
        raise ValueError("Set delivery.email.sender or SMTP_USER")

    thread_cfg = cfg.get("thread") or {}
    parent = None
    if thread_cfg.get("enabled"):
        parent = find_parent(cfg)
        subject = reply_subject(parent.subject)
        if thread_cfg.get("reply_all", True):
            thread_to, thread_cc = reply_all_recipients(parent, sender)
            to = _merge(thread_to, to)
            cc = [a for a in _merge(thread_cc, cc) if a.lower() not in {t.lower() for t in to}]

    if not to:
        raise ValueError("No recipients: delivery.email.to is empty")
    return EmailPlan(sender=sender, subject=subject, to=to, cc=cc, bcc=bcc, parent=parent)


def to_email(cfg: dict, report: Report) -> None:
    plan = plan_email(cfg, report.subject)

    msg = EmailMessage()
    msg["Subject"] = plan.subject
    msg["From"] = (f"{cfg['sender_name']} <{plan.sender}>" if cfg.get("sender_name")
                   else plan.sender)
    msg["To"] = ", ".join(plan.to)
    if plan.cc:
        msg["Cc"] = ", ".join(plan.cc)
    msg["Message-ID"] = make_msgid(domain=plan.sender.split("@")[-1])
    if plan.parent and plan.parent.message_id:
        msg["In-Reply-To"] = plan.parent.message_id
        msg["References"] = f"{plan.parent.references} {plan.parent.message_id}".strip()
    msg.set_content(report.text)
    msg.add_alternative(report.html, subtype="html")

    with smtp_connection(cfg) as smtp:
        smtp.send_message(msg, from_addr=plan.sender, to_addrs=plan.to + plan.cc + plan.bcc)


def to_file(cfg: dict, window: DayWindow, report: Report) -> Path:
    directory = Path(cfg.get("directory", "reports"))
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"report-{window.day.isoformat()}.md"
    path.write_text(report.text, encoding="utf-8")
    (directory / f"report-{window.day.isoformat()}.html").write_text(report.html,
                                                                      encoding="utf-8")
    return path


def deliver(cfg: dict, window: DayWindow, report: Report) -> list[str]:
    """Send to every enabled target; returns the list of failures."""
    delivery = cfg.get("delivery") or {}
    failures = []

    targets = [
        ("file", lambda c: log.info("Saved %s", to_file(c, window, report))),
        ("email", lambda c: to_email(c, report)),
        ("slack", lambda c: to_slack(c, report)),
    ]
    for name, send in targets:
        target_cfg = delivery.get(name) or {}
        if not target_cfg.get("enabled"):
            continue
        try:
            send(target_cfg)
            log.info("Delivered via %s", name)
        except Exception as exc:
            log.exception("Delivery via %s failed", name)
            failures.append(f"{name}: {exc}")
    return failures
