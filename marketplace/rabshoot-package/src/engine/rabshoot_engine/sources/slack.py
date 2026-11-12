import json
import logging
import re
import time
from datetime import datetime, timedelta
from urllib.parse import quote

import requests

from ..models import SlackSelection
from ..window import DayWindow

log = logging.getLogger(__name__)

SLACK_API = "https://slack.com/api"

USER_SCOPES = ["channels:history", "groups:history", "im:history", "mpim:history",
               "channels:read", "groups:read", "im:read", "mpim:read", "users:read"]

_SKIP_SUBTYPES = {"channel_join", "channel_leave", "channel_topic", "channel_purpose",
                  "channel_name", "group_join", "group_leave"}
_USER_MENTION = re.compile(r"<@([UW][A-Z0-9]+)(?:\|[^>]*)?>")
_CHANNEL_MENTION = re.compile(r"<#[A-Z0-9]+\|([^>]*)>")
_LINK = re.compile(r"<(https?://[^|>]+)(?:\|([^>]*))?>")
_SPECIAL = re.compile(r"<!(here|channel|everyone)[^>]*>")


SLACK_REDIRECT_URL = "http://127.0.0.1:47114/slack/callback"
PROJECT_URL = "https://github.com/A7my/rabshoot"

# Slack requires 175-4000 characters and shows it as plain text.
LONG_DESCRIPTION = (
    "RabShoot is a free desktop app for Windows and Linux that writes your daily work report. "
    "It collects the day's commits, merge requests and issues from GitLab and GitHub and the "
    "Slack conversations you choose, summarizes them with AI, and emails the report from your "
    "own mailbox on your schedule.\n\n"
    "This Slack app is read-only: it lets each teammate sign in with their own account so "
    "RabShoot can read the channels and chats they pick. It never posts messages, and "
    "everything runs on the member's own computer. One app per workspace is enough; share its "
    "Client ID as the team code.\n\n"
    f"Download, source code and documentation: {PROJECT_URL}"
)


def manifest(app_name: str = "RabShoot") -> dict:
    """Read-only app created once per workspace; every member signs in to it with PKCE."""
    return {
        "display_information": {
            "name": app_name,
            "description": "Collects your work updates for the RabShoot daily report.",
            "long_description": LONG_DESCRIPTION,
            "background_color": "#0a0b10",
        },
        "oauth_config": {"redirect_urls": [SLACK_REDIRECT_URL], "pkce_enabled": True,
                         "scopes": {"user": USER_SCOPES}},
        "settings": {"org_deploy_enabled": False, "socket_mode_enabled": False,
                     "token_rotation_enabled": False},
    }


def manifest_url(app_name: str = "RabShoot") -> str:
    body = json.dumps(manifest(app_name), separators=(",", ":"))
    return f"https://api.slack.com/apps?new_app=1&manifest_json={quote(body)}"


class SlackError(RuntimeError):
    def __init__(self, method: str, code: str):
        super().__init__(f"Slack {method} failed: {code}")
        self.code = code


class SlackClient:
    def __init__(self, token: str, timeout: int = 30):
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"Bearer {token}"
        self.timeout = timeout
        self._users: dict[str, dict] | None = None
        self._conversations: list[dict] | None = None

    def call(self, method: str, http: str = "GET", **params) -> dict:
        for _ in range(5):
            if http == "GET":
                resp = self.session.get(f"{SLACK_API}/{method}", params=params,
                                        timeout=self.timeout)
            else:
                resp = self.session.post(f"{SLACK_API}/{method}", json=params,
                                         timeout=self.timeout)
            if resp.status_code == 429:
                time.sleep(int(resp.headers.get("Retry-After", "5")))
                continue
            resp.raise_for_status()
            data = resp.json()
            if not data.get("ok"):
                raise SlackError(method, data.get("error", "unknown_error"))
            return data
        raise SlackError(method, "rate_limited")

    def _paginate(self, method: str, key: str, **params) -> list[dict]:
        items, cursor = [], None
        while True:
            if cursor:
                params["cursor"] = cursor
            data = self.call(method, **params)
            items.extend(data.get(key, []))
            cursor = (data.get("response_metadata") or {}).get("next_cursor")
            if not cursor:
                return items

    def auth_test(self) -> dict:
        return self.call("auth.test")

    def users(self) -> dict[str, dict]:
        if self._users is None:
            self._users = {u["id"]: u for u in self._paginate("users.list", "members", limit=200)}
        return self._users

    def user_name(self, user_id: str | None) -> str:
        if not user_id:
            return "unknown"
        u = self.users().get(user_id)
        if not u:
            return user_id
        return u.get("profile", {}).get("display_name") or u.get("real_name") or u["name"]

    def conversations(self) -> list[dict]:
        if self._conversations is None:
            self._conversations = self._paginate(
                "conversations.list", "channels",
                types="public_channel,private_channel,mpim,im",
                exclude_archived="true", limit=200,
            )
        return self._conversations

    def display(self, c: dict) -> str:
        if c.get("is_im"):
            return f"DM with {self.user_name(c.get('user'))}"
        if c.get("is_mpim"):
            return "Group chat: " + (c.get("purpose", {}).get("value") or c.get("name", ""))
        return f"#{c.get('name', c['id'])}"

    def conversation_list(self) -> list[dict]:
        """Picker entries: channels the user is a member of, DMs and group chats."""
        out = []
        for c in self.conversations():
            if c.get("is_im"):
                user = self.users().get(c.get("user") or "", {})
                if user.get("deleted") or c.get("user") == "USLACKBOT":
                    continue
                kind = "dm"
            elif c.get("is_mpim"):
                kind = "group"
            else:
                if not c.get("is_member"):
                    continue
                kind = "private" if c.get("is_private") else "channel"
            out.append({"id": c["id"], "name": self.display(c), "kind": kind,
                        "members": c.get("num_members")})
        order = {"channel": 0, "private": 1, "group": 2, "dm": 3}
        return sorted(out, key=lambda x: (order[x["kind"]], x["name"].lower()))

    def history(self, channel: str, oldest: float, latest: float) -> list[dict]:
        return self._paginate("conversations.history", "messages", channel=channel,
                              oldest=oldest, latest=latest, inclusive="true", limit=200)

    def replies(self, channel: str, ts: str, oldest: float, latest: float) -> list[dict]:
        msgs = self._paginate("conversations.replies", "messages", channel=channel, ts=ts,
                              oldest=oldest, latest=latest, inclusive="true", limit=200)
        return [m for m in msgs if m.get("ts") != ts]

    def format_text(self, text: str) -> str:
        text = _USER_MENTION.sub(lambda m: "@" + self.user_name(m.group(1)), text)
        text = _CHANNEL_MENTION.sub(lambda m: "#" + m.group(1), text)
        text = _LINK.sub(lambda m: m.group(2) or m.group(1), text)
        text = _SPECIAL.sub(lambda m: "@" + m.group(1), text)
        return text.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")


_ARABIC_MARKS = re.compile(r"[\u064B-\u0652\u0640]")
_NON_WORD = re.compile(r"[^\w\s]|_")
_EMOJI_CODE = re.compile(r":[a-z0-9_+\-]+:")


def normalize(text: str) -> str:
    """Lowercase, drop emoji codes, punctuation and Arabic diacritics, unify alef/yaa/taa."""
    text = _EMOJI_CODE.sub(" ", str(text).lower())
    text = _ARABIC_MARKS.sub("", text)
    text = text.translate(str.maketrans("أإآىة", "ااايه"))
    return " ".join(_NON_WORD.sub(" ", text).split())


class SmallTalkFilter:
    """Drops messages that are only greetings/thanks, keeps ones with real content."""

    def __init__(self, phrases: list[str], leftover_words: int = 2):
        ordered = sorted({normalize(p) for p in phrases} - {""}, key=len, reverse=True)
        self.patterns = [re.compile(rf"(?:^|\s){re.escape(p)}(?=\s|$)") for p in ordered]
        self.leftover = leftover_words

    def is_small_talk(self, text: str) -> bool:
        rest, matched = normalize(text), False
        for pattern in self.patterns:
            rest, n = pattern.subn(" ", rest)
            matched = matched or n > 0
        words = rest.split()
        return not words or (matched and len(words) <= self.leftover)


def collect(client: SlackClient, sel: SlackSelection, window: DayWindow) -> list[dict]:
    if not sel.conversations:
        return []
    small_talk = SmallTalkFilter(sel.ignore_messages, sel.ignore_leftover_words)
    lookback = timedelta(days=sel.thread_lookback_days)
    day_start, day_end = window.start.timestamp(), window.end.timestamp()
    tz = window.start.tzinfo

    def in_day(msg: dict) -> bool:
        return day_start <= float(msg["ts"]) < day_end

    def keep(msg: dict) -> bool:
        if msg.get("subtype") in _SKIP_SUBTYPES:
            return False
        if not sel.include_bots and (msg.get("bot_id") or msg.get("subtype") == "bot_message"):
            return False
        return not small_talk.is_small_talk(msg.get("text") or "")

    def fmt(msg: dict) -> dict:
        when = datetime.fromtimestamp(float(msg["ts"]), tz)
        return {"user": client.user_name(msg.get("user")) if msg.get("user")
                else msg.get("username", "bot"),
                "text": client.format_text(msg.get("text", "")),
                "time": when.strftime("%H:%M"), "date": when.strftime("%Y-%m-%d"),
                "ts": msg["ts"]}

    results = []
    for ref in sel.conversations:
        name = ref.name or ref.id
        try:
            conv = next((c for c in client.conversations() if c["id"] == ref.id), None)
            if conv:
                name = client.display(conv)
            history = client.history(ref.id, (window.start - lookback).timestamp(), day_end)
            threads = []
            for msg in history:
                # Broadcast replies also appear in history; they are picked up via replies.
                if msg.get("thread_ts") not in (None, msg["ts"]):
                    continue
                parent_today = in_day(msg) and keep(msg)
                replies = []
                if msg.get("reply_count") and float(msg.get("latest_reply", 0)) >= day_start:
                    replies = [fmt(r) for r in client.replies(ref.id, msg["ts"], day_start, day_end)
                               if in_day(r) and keep(r)]
                if parent_today or replies:
                    threads.append({**fmt(msg), "from_earlier": not in_day(msg),
                                    "replies": sorted(replies, key=lambda r: float(r["ts"]))})
            threads.sort(key=lambda t: float(t["ts"]))
            results.append({"id": ref.id, "name": name, "threads": threads,
                            "message_count": sum((not t["from_earlier"]) + len(t["replies"])
                                                 for t in threads)})
        except Exception as exc:
            log.error("Slack conversation %s failed: %s", name, exc)
            results.append({"id": ref.id, "name": name, "error": str(exc),
                            "threads": [], "message_count": 0})
    return results
