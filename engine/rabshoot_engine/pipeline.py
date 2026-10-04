"""Build and send one profile's report, recording each step for the UI."""

import logging
import threading
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from email.message import EmailMessage
from email.utils import formataddr, make_msgid

from . import connectors, drafts, history, storage
from .ai import enrich
from .mail import imap, smtp
from .models import CODE_TYPES, Profile, now_iso, profile_problems
from .render import LOGO_CID, Report, editable_text, logo_bytes, render
from .sources import github as github_source
from .sources import gitlab as gitlab_source
from .sources import slack as slack_source
from .window import DayWindow

log = logging.getLogger(__name__)

_running: set[str] = set()
_running_lock = threading.Lock()
_progress: dict[str, "Progress"] = {}

# (stage, start %, end %) — rough share of a typical run's time.
_STAGES = {"prepare": (0, 5), "code": (5, 45), "slack": (45, 58), "ai": (58, 88),
           "render": (88, 92), "email": (92, 100)}
FINISHED_VISIBLE_SECONDS = 20


class ProfileBusy(RuntimeError):
    pass


class Progress:
    """Live state of one run, polled by the UI while the run is in flight."""

    def __init__(self, profile_id: str, trigger: str, sending: bool):
        self.profile_id = profile_id
        self.state = {"run_id": "", "trigger": trigger, "sending": sending, "stage": "prepare",
                      "percent": 0, "current": 0, "total": 0, "item": "", "status": "running",
                      "error": "", "started_at": now_iso(), "finished_at": None, "steps": []}
        self._finished = 0.0
        _progress[profile_id] = self

    def update(self, stage: str, done: int = 0, total: int = 0, item: str = "",
               share: tuple[int, int] = (0, 1)) -> None:
        """share = (index, count) when a stage is split across several sources."""
        low, high = _STAGES[stage]
        index, count = share
        fraction = (index + (done / total if total else 0)) / max(count, 1)
        percent = round(low + (high - low) * min(max(fraction, 0.0), 1.0))
        self.state.update(stage=stage, percent=max(self.state["percent"], percent),
                          current=min(done + 1, total) if total else 0, total=total, item=item)

    def finish(self, status: str, error: str = "") -> None:
        self.state.update(status=status, error=error, finished_at=now_iso(), item="",
                          percent=100 if status in ("sent", "previewed", "skipped") else self.state["percent"])
        self._finished = time.monotonic()

    def visible(self) -> bool:
        return not self._finished or time.monotonic() - self._finished < FINISHED_VISIBLE_SECONDS

    def snapshot(self) -> dict:
        return {**self.state, "steps": list(self.state["steps"])}


def progress(profile_id: str) -> dict | None:
    tracker = _progress.get(profile_id)
    return tracker.snapshot() if tracker and tracker.visible() else None


@dataclass
class RunResult:
    status: str = "running"  # sent | previewed | skipped | failed
    steps: list[dict] = field(default_factory=list)
    has_activity: bool = True
    report: Report | None = None
    subject: str = ""
    recipients: list[str] = field(default_factory=list)
    error: str = ""
    run_id: str = ""
    projects: list[dict] = field(default_factory=list, repr=False)
    conversations: list[dict] = field(default_factory=list, repr=False)
    draft: dict | None = None  # {"id", "content"} for previews and tests, so they can be edited

    def step(self, key: str, status: str, message: str, **extra) -> None:
        self.steps.append({"key": key, "status": status, "message": message, **extra})

    def as_dict(self, include_html: bool = False) -> dict:
        out = {"status": self.status, "steps": self.steps, "subject": self.subject,
               "recipients": self.recipients, "error": self.error, "run_id": self.run_id}
        if include_html and self.report:
            out["html"] = self.report.html_for_display()
            out["text"] = self.report.text
            out["stats"] = self.report.stats
        if include_html and self.draft:
            out["draft"] = self.draft
        return out


@dataclass
class EmailPlan:
    sender: str
    subject: str
    to: list[str]
    cc: list[str]
    bcc: list[str]
    parent: imap.ThreadParent | None = None
    only_me: bool = False  # a thread nobody else is in: the reply goes back to the sender


def _merge(*lists: list[str]) -> list[str]:
    return list({a.lower(): a for lst in lists for a in lst}.values())


def plan_email(profile: Profile, meta: dict, password: str, subject: str) -> EmailPlan:
    d = profile.delivery
    to, cc, bcc = list(d.to), list(d.cc), list(d.bcc)
    sender = meta["address"]
    parent = None
    only_me = False
    if d.mode == "thread" and d.thread:
        parent = imap.find_parent(meta, password, d.thread)
        subject = imap.reply_subject(parent.subject)
        if d.reply_all:
            thread_to, thread_cc = imap.reply_all_recipients(parent, sender)
            to = _merge(thread_to, to)
            cc = [a for a in _merge(thread_cc, cc) if a.lower() not in {t.lower() for t in to}]
        if not to and not cc:
            if not d.reply_all:
                raise ValueError("No recipients: 'Reply to everyone in the thread' is off and no "
                                 "extra recipients were added")
            to, only_me = [sender], True
    if not to:
        raise ValueError("No recipients: add at least one 'To' address or pick a thread")
    return EmailPlan(sender=sender, subject=subject, to=to, cc=cc, bcc=bcc, parent=parent,
                     only_me=only_me)


def _sent_message(plan: EmailPlan) -> str:
    where = ""
    if plan.parent:
        where = (" (reply in the thread; nobody else is in it, so only you got it)"
                 if plan.only_me else " (reply-all in thread)")
    return f"Sent to {', '.join(plan.to + plan.cc)}{where}"


def build_message(plan: EmailPlan, report: Report, sender_name: str) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = plan.subject
    msg["From"] = formataddr((sender_name, plan.sender)) if sender_name else plan.sender
    msg["To"] = ", ".join(plan.to)
    if plan.cc:
        msg["Cc"] = ", ".join(plan.cc)
    msg["Message-ID"] = make_msgid(domain=plan.sender.split("@")[-1])
    msg["X-Mailer"] = "RabShoot"
    if plan.parent and plan.parent.message_id:
        msg["In-Reply-To"] = plan.parent.message_id
        msg["References"] = f"{plan.parent.references} {plan.parent.message_id}".strip()
    msg.set_content(report.text)
    msg.add_alternative(report.html, subtype="html")
    if report.branding and logo_bytes() and f"cid:{LOGO_CID}" in report.html:
        msg.get_payload()[1].add_related(logo_bytes(), "image", "png", cid=f"<{LOGO_CID}>",
                                         filename="rabshoot.png")
    return msg


def _deliver(profile: Profile, result: RunResult, test_to: str | None = None,
             plan: EmailPlan | None = None, suffix: str = "") -> None:
    """Email result.report to the report's recipients (or only to test_to) and record the step."""
    try:
        conn = storage.get_connection(profile.sender_connection_id or "")
        meta, password = connectors.email_credentials(conn)
        if test_to:
            plan = EmailPlan(sender=meta["address"], subject="[Test] " + result.subject,
                             to=[test_to], cc=[], bcc=[])
        else:
            plan = plan or plan_email(profile, meta, password, result.subject)
            if not plan.parent:
                plan.subject = result.subject
        msg = build_message(plan, result.report, profile.delivery.sender_name
                            or meta.get("display_name", ""))
        smtp.send(meta, password, msg, plan.to + plan.cc + plan.bcc)
        result.subject, result.recipients = plan.subject, plan.to + plan.cc
        result.step("email", "ok", _sent_message(plan) + suffix)
        result.status = "sent"
    except Exception as exc:
        log.exception("Sending failed")
        result.step("email", "error", connectors._friendly(exc))
        result.status = "failed"
        result.error = connectors._friendly(exc)


def _updater(tracker: Progress | None):
    return tracker.update if tracker else (lambda *args, **kwargs: None)


def collect_code(profile: Profile, window: DayWindow, result: RunResult,
                 tracker: Progress | None = None) -> list[dict]:
    update = _updater(tracker)
    connections = storage.connections_by_id()
    projects: list[dict] = []
    count = len(profile.code_sources)
    update("code", share=(0, count))
    for index, source in enumerate(profile.code_sources):
        conn = connections.get(source.connection_id)
        if not conn or conn.type not in CODE_TYPES:
            result.step("code", "error", "A code source points to a removed account")
            continue
        label = conn.label or conn.type
        try:
            client = connectors.code_client(conn)
            module = gitlab_source if conn.type == "gitlab" else github_source
            skipped: Counter = Counter()
            found = module.collect(
                client, source, window, want_diffs=True,
                max_diff_chars=profile.report.max_diff_chars_per_project,
                progress=lambda done, total, name, i=index: update(
                    "code", done, total, name, share=(i, count)),
                skipped=skipped)
            projects.extend(found)
            commits = sum(len(p["commits"]) for p in found)
            failed = [p["name"] for p in found if p.get("error")]
            status = "warn" if failed else "ok"
            msg = f"{label}: {len(found)} project(s) with activity, {commits} commit(s)"
            if failed:
                msg += f"; failed: {', '.join(failed[:3])}"
            if not commits and skipped:
                status = "warn"
                seen = ", ".join(f"{who} ({n})" for who, n in skipped.most_common(5))
                msg += (f". The author filter skipped {sum(skipped.values())} commit(s) by: "
                        f"{seen}. If one of these is you, add that name or email to "
                        "'Only these authors'.")
            result.step("code", status, msg, source=conn.type)
        except Exception as exc:
            log.exception("Code source %s failed", label)
            connectors.mark_failed(conn, exc)
            result.step("code", "error", f"{label}: {connectors._friendly(exc)}", source=conn.type)
    return projects


def collect_slack(profile: Profile, window: DayWindow, result: RunResult,
                  tracker: Progress | None = None) -> list[dict]:
    _updater(tracker)("slack")
    sel = profile.slack
    if not sel.connection_id:
        if any(c.type == "slack" for c in storage.list_connections()):
            result.step("slack", "warn", "Slack isn't added to this report. Open the report's "
                        "Slack tab and pick the conversations to include.")
        else:
            result.step("slack", "skipped", "Slack not used in this report")
        return []
    if not sel.conversations:
        result.step("slack", "skipped", "No Slack conversations selected")
        return []
    conn = None
    try:
        conn = storage.get_connection(sel.connection_id)
        convs = slack_source.collect(connectors.slack_client(conn), sel, window)
        failed = [c["name"] for c in convs if c.get("error")]
        msgs = sum(c["message_count"] for c in convs)
        result.step("slack", "warn" if failed else "ok",
                    f"{conn.label or 'Slack'}: {msgs} message(s) in {len(convs)} conversation(s)"
                    + (f"; failed: {', '.join(failed[:3])}" if failed else ""))
        return convs
    except Exception as exc:
        log.exception("Slack failed")
        if conn:
            connectors.mark_failed(conn, exc)
        result.step("slack", "error", connectors._friendly(exc))
        return []


def summarize(profile: Profile, projects: list[dict], convs: list[dict],
              result: RunResult, tracker: Progress | None = None) -> None:
    update = _updater(tracker)
    update("ai")
    if not any(p["commits"] or p["merge_requests"] for p in projects) and \
            not any(c["threads"] for c in convs):
        result.step("ai", "skipped", "Nothing to summarize")
        return
    try:
        conn = storage.get_connection(profile.ai_connection_id or "")
        client = connectors.ai_client(conn, profile.report.language,
                                      profile.report.extra_instructions, profile.report.max_points)
        stats = enrich(client, projects, convs,
                       progress=lambda done, total, name: update("ai", done, total, name))
        if stats["failed"]:
            result.step("ai", "warn", f"{stats['ok']} summarized, {stats['failed']} failed "
                        f"(raw data used instead): {stats['errors'][0]}", model=client.model)
        else:
            result.step("ai", "ok", f"{stats['ok']} item(s) summarized with {client.model}",
                        model=client.model)
    except Exception as exc:
        log.exception("AI failed")
        result.step("ai", "error", f"{connectors._friendly(exc)} — raw data used instead")


def build(profile: Profile, day: date | None = None,
          tracker: Progress | None = None) -> tuple[RunResult, DayWindow]:
    tz = profile.schedule.timezone
    window = DayWindow.for_day(day, tz) if day else DayWindow.today(tz)
    result = RunResult()
    if tracker:
        tracker.state["steps"] = result.steps
    projects = collect_code(profile, window, result, tracker)
    convs = collect_slack(profile, window, result, tracker)
    result.has_activity = any(p.get("commits") or p.get("merge_requests") or p.get("issues")
                              for p in projects) \
        or any(c.get("message_count") for c in convs)
    summarize(profile, projects, convs, result, tracker)
    _updater(tracker)("render")
    result.report = render(profile, window, projects, convs)
    result.subject = result.report.subject
    result.projects, result.conversations = projects, convs
    return result, window


SCHEDULED_TRIGGERS = ("schedule", "catch_up")


def run(profile: Profile, trigger: str = "manual", day: date | None = None,
        send: bool = True, test_to: str | None = None) -> RunResult:
    """trigger: schedule | catch_up | manual | test | preview."""
    with _running_lock:
        if profile.id in _running:
            raise ProfileBusy(f"'{profile.name}' is already running")
        _running.add(profile.id)
    run_id = ""
    tracker = Progress(profile.id, trigger, sending=send)
    try:
        problems = profile_problems(profile, storage.connections_by_id())
        if problems:
            result = RunResult(status="failed", error="Setup incomplete: " + ", ".join(problems))
            tracker.finish("failed", result.error)
            return result
        tz_day = day or DayWindow.today(profile.schedule.timezone).day
        run_id = history.start_run(profile.id, profile.name, trigger, tz_day.isoformat())
        tracker.state["run_id"] = run_id

        early_plan = None
        if send and not test_to:
            # Resolve recipients first so a delivery problem fails in seconds, not after the AI.
            try:
                meta, password = connectors.email_credentials(
                    storage.get_connection(profile.sender_connection_id or ""))
                early_plan = plan_email(profile, meta, password, subject="")
            except Exception as exc:
                message = connectors._friendly(exc)
                result = RunResult(status="failed", error=message, run_id=run_id)
                result.step("email", "error", message)
                history.finish_run(run_id, "failed", error=message, steps=result.steps)
                tracker.state["steps"] = result.steps
                tracker.finish("failed", message)
                return result

        result, window = build(profile, tz_day, tracker)
        result.run_id = run_id
        tracker.update("email")
        quiet_day = profile.schedule.skip_empty and not result.has_activity

        if quiet_day and send and not test_to and trigger in SCHEDULED_TRIGGERS:
            errors = [s["message"] for s in result.steps if s["status"] == "error"]
            if errors:
                result.status, result.error = "failed", f"Nothing was sent: {errors[0]}"
                result.step("email", "error", result.error)
            else:
                result.status = "skipped"
                result.step("email", "skipped", "No code or Slack activity on this day, "
                            "so nothing was sent")
        elif not send:
            result.status = "previewed"
            if quiet_day and trigger == "preview" and profile.schedule.mode != "now":
                result.step("email", "warn", "No code or Slack activity on this day: a scheduled "
                            "send would be skipped. Send now still sends it.")
            try:
                meta, password = connectors.email_credentials(
                    storage.get_connection(profile.sender_connection_id or ""))
                if test_to:
                    result.recipients = [test_to]
                else:
                    plan = plan_email(profile, meta, password, result.subject)
                    result.subject, result.recipients = plan.subject, plan.to + plan.cc
                    if plan.only_me:
                        result.step("email", "warn", "Nobody else is in the chosen thread, so the "
                                    "report would go only to you. Add recipients or pick "
                                    "another thread.")
                result.step("email", "skipped", "Preview only, nothing was sent")
            except Exception as exc:
                result.step("email", "warn", f"Recipients could not be resolved: "
                            f"{connectors._friendly(exc)}")
        else:
            _deliver(profile, result, test_to, plan=early_plan)

        if trigger in ("preview", "test"):
            body = editable_text(profile, window, result.projects, result.conversations)
            draft = drafts.save(profile.id, tz_day, result.report.subject, body, result.projects,
                                result.conversations, result.steps)
            result.draft = {"id": draft.id, "content": draft.content.model_dump()}

        errors = [s for s in result.steps if s["status"] == "error"]
        if result.status != "failed" and errors and not result.report.stats["projects"] \
                and not result.report.stats["slack_messages"]:
            result.error = errors[0]["message"]
        history.finish_run(run_id, result.status, error=result.error, subject=result.subject,
                           recipients=result.recipients, steps=result.steps,
                           html=result.report.html_for_display(), text=result.report.text)
        tracker.finish(result.status, result.error)
        return result
    except Exception as exc:
        log.exception("Run failed")
        if run_id:
            history.finish_run(run_id, "failed", error=str(exc))
        tracker.finish("failed", str(exc))
        return RunResult(status="failed", error=str(exc), run_id=run_id)
    finally:
        with _running_lock:
            _running.discard(profile.id)


def send_draft(profile: Profile, draft: drafts.Draft, content: drafts.DraftContent,
               test_to: str | None = None) -> RunResult:
    """Send a previewed report as edited, without collecting or summarizing again."""
    with _running_lock:
        if profile.id in _running:
            raise ProfileBusy(f"'{profile.name}' is already running")
        _running.add(profile.id)
    run_id = ""
    try:
        problems = profile_problems(profile, storage.connections_by_id())
        if problems:
            return RunResult(status="failed", error="Setup incomplete: " + ", ".join(problems))
        run_id = history.start_run(profile.id, profile.name, "test" if test_to else "manual",
                                   draft.day.isoformat())
        window = DayWindow.for_day(draft.day, profile.schedule.timezone)
        report = render(profile, window, draft.projects, draft.conversations,
                        subject=content.subject, body=draft.edited_body(content))
        result = RunResult(steps=[dict(s) for s in draft.steps], report=report,
                           subject=report.subject, run_id=run_id)
        _deliver(profile, result, test_to, suffix=" — edited before sending")
        history.finish_run(run_id, result.status, error=result.error, subject=result.subject,
                           recipients=result.recipients, steps=result.steps,
                           html=report.html_for_display(), text=report.text)
        return result
    except Exception as exc:
        log.exception("Sending the edited report failed")
        if run_id:
            history.finish_run(run_id, "failed", error=str(exc))
        return RunResult(status="failed", error=str(exc), run_id=run_id)
    finally:
        with _running_lock:
            _running.discard(profile.id)


def is_running(profile_id: str) -> bool:
    return profile_id in _running
