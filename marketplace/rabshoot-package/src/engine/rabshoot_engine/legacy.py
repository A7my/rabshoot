"""Import the old daily_report setup (config.yaml + .env) as RabShoot connections + a profile."""

from pathlib import Path

import yaml

from . import storage
from .ai import DEFAULT_FALLBACKS, GEMINI_BASE_URL
from .mail.providers import guess_provider
from .models import (CodeSource, Connection, ConversationRef, Delivery, Profile, ReportOptions,
                     Schedule, SlackSelection, ThreadRef)
from .sources.slack import SlackClient


def _dotenv(path: Path) -> dict:
    env = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def _list(value) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        value = value.split(",")
    return [v.strip() for v in value if v and str(v).strip()]


def import_legacy(folder: Path) -> Profile:
    cfg = yaml.safe_load((folder / "config.yaml").read_text(encoding="utf-8")) or {}
    env = _dotenv(folder / ".env")
    delivery_cfg = (cfg.get("delivery") or {}).get("email") or {}
    profile = Profile(name=(cfg.get("report") or {}).get("title", "Daily Report"))

    sender = env.get("SMTP_USER") or delivery_cfg.get("sender")
    if sender and env.get("SMTP_PASSWORD"):
        conn = Connection(type="email", label=sender, meta={
            "address": sender, "provider": guess_provider(sender),
            "smtp_host": delivery_cfg.get("smtp_host", ""),
            "smtp_port": int(delivery_cfg.get("smtp_port", 587)),
            "imap_host": delivery_cfg.get("imap_host", ""),
            "display_name": delivery_cfg.get("sender_name", ""),
        })
        storage.save_connection(conn, {"password": env["SMTP_PASSWORD"]})
        profile.sender_connection_id = conn.id

    thread = delivery_cfg.get("thread") or {}
    profile.delivery = Delivery(
        mode="thread" if thread.get("enabled") else "recipients",
        to=_list(delivery_cfg.get("to")), cc=_list(delivery_cfg.get("cc")),
        bcc=_list(delivery_cfg.get("bcc")),
        thread=ThreadRef(subject=thread.get("subject", ""),
                         message_id=thread.get("message_id", "")) if thread.get("enabled") else None,
        reply_all=thread.get("reply_all", True),
        sender_name=delivery_cfg.get("sender_name", ""),
    )

    gl = cfg.get("gitlab") or {}
    if env.get("GITLAB_TOKEN") and gl.get("enabled", True):
        conn = Connection(type="gitlab", meta={"url": gl.get("url", "https://gitlab.com"),
                                               "auth": "pat"})
        conn.label = f"GitLab · {conn.meta['url'].replace('https://', '')}"
        storage.save_connection(conn, {"token": env["GITLAB_TOKEN"]})
        projects = gl.get("projects", "all")
        profile.code_sources.append(CodeSource(
            connection_id=conn.id,
            projects="all" if projects == "all" else [str(p) for p in projects],
            exclude=[str(p) for p in gl.get("exclude_projects") or []],
            authors=gl.get("authors") or [],
        ))

    sl = cfg.get("slack") or {}
    token = env.get("SLACK_USER_TOKEN") or env.get("SLACK_BOT_TOKEN")
    if token and sl.get("enabled", True):
        client = SlackClient(token)
        info = client.auth_test()
        conn = Connection(type="slack", label=info.get("team", "Slack"),
                          meta={"team": info.get("team"), "team_id": info.get("team_id"),
                                "user": info.get("user")})
        storage.save_connection(conn, {"token": token})
        refs = [*(sl.get("channels") or []), *(sl.get("direct_messages") or []),
                *(sl.get("conversations") or [])]
        convs = []
        for ref in refs:
            ref = str(ref).strip()
            if ref.startswith("#"):
                match = next((c for c in client.conversations()
                              if c.get("name", "").lower() == ref[1:].lower()), None)
                if match:
                    convs.append(ConversationRef(id=match["id"], name=ref))
            elif ref.startswith("@"):
                handle = ref[1:].lower()
                user = next((u for u in client.users().values()
                             if handle in {u.get("name", "").lower(),
                                           u.get("profile", {}).get("display_name", "").lower()}),
                            None)
                im = next((c for c in client.conversations()
                           if user and c.get("is_im") and c.get("user") == user["id"]), None)
                if im:
                    convs.append(ConversationRef(id=im["id"], name=f"DM with {ref[1:]}"))
            elif ref:
                convs.append(ConversationRef(id=ref, name=ref))
        sel = SlackSelection(connection_id=conn.id, conversations=convs)
        if sl.get("ignore_messages"):
            sel.ignore_messages = list(sl["ignore_messages"])
        sel.ignore_leftover_words = int(sl.get("ignore_leftover_words", 2))
        sel.thread_lookback_days = int(sl.get("thread_lookback_days", 7))
        profile.slack = sel

    ai = cfg.get("ai") or {}
    if env.get("AI_API_KEY"):
        conn = Connection(type="ai", label="Google Gemini", meta={
            "provider": "gemini", "base_url": ai.get("base_url", GEMINI_BASE_URL),
            "model": ai.get("model", "gemini-3.5-flash"),
            "fallback_models": ai.get("fallback_models", DEFAULT_FALLBACKS)})
        storage.save_connection(conn, {"key": env["AI_API_KEY"]})
        profile.ai_connection_id = conn.id

    sched = cfg.get("schedule") or {}
    profile.schedule = Schedule(time=str(sched.get("time", "18:00")),
                                days=str(sched.get("days", "sun-thu")),
                                timezone=sched.get("timezone", "UTC"))
    report = cfg.get("report") or {}
    profile.report = ReportOptions(
        title=report.get("title", "Daily Report"), language=ai.get("language", "English"),
        extra_instructions=ai.get("extra_instructions", "") or "",
        max_points=int(ai.get("max_points", 6)),
        max_diff_chars_per_project=int(ai.get("max_diff_chars_per_project", 20000)))
    return storage.save_profile(profile)
