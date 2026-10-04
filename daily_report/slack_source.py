import logging
import os
import re
import time
from datetime import datetime, timedelta

import requests

from .config import DayWindow

log = logging.getLogger(__name__)

SLACK_API = "https://slack.com/api"

_SKIP_SUBTYPES = {"channel_join", "channel_leave", "channel_topic", "channel_purpose",
                  "channel_name", "group_join", "group_leave"}
_USER_MENTION = re.compile(r"<@([UW][A-Z0-9]+)(?:\|[^>]*)?>")
_CHANNEL_MENTION = re.compile(r"<#[A-Z0-9]+\|([^>]*)>")
_LINK = re.compile(r"<(https?://[^|>]+)(?:\|([^>]*))?>")
_SPECIAL = re.compile(r"<!(here|channel|everyone)[^>]*>")


class SlackClient:
    def __init__(self, token: str, timeout: int = 30):
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"Bearer {token}"
        self.timeout = timeout
        self._users: dict[str, dict] | None = None
        self._conversations: list[dict] | None = None

    def call(self, method: str, http: str = "GET", **params) -> dict:
        while True:
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
                raise RuntimeError(f"Slack {method} failed: {data.get('error')}")
            return data

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

    # --- lookups -----------------------------------------------------------

    def users(self) -> dict[str, dict]:
        if self._users is None:
            self._users = {u["id"]: u for u in self._paginate("users.list", "members",
                                                                limit=200)}
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

    def resolve(self, ref: str) -> tuple[str, str]:
        """Turn '#name', '@user' or a raw ID into (conversation_id, display_name)."""
        ref = ref.strip()
        if ref.startswith("#"):
            name = ref[1:].lower()
            for c in self.conversations():
                if (c.get("name") or "").lower() == name:
                    return c["id"], f"#{c['name']}"
            raise LookupError(f"Channel {ref} not found (are you a member?)")
        if ref.startswith("@"):
            handle = ref[1:].lower()
            user = next(
                (u for u in self.users().values()
                 if handle in {u.get("name", "").lower(),
                               u.get("profile", {}).get("display_name", "").lower(),
                               u.get("real_name", "").lower()}),
                None,
            )
            if not user:
                raise LookupError(f"User {ref} not found")
            for c in self.conversations():
                if c.get("is_im") and c.get("user") == user["id"]:
                    return c["id"], f"DM with {self.user_name(user['id'])}"
            raise LookupError(f"No direct message conversation with {ref}")
        for c in self.conversations():
            if c["id"] == ref:
                return ref, self._display(c)
        return ref, ref

    def _display(self, c: dict) -> str:
        if c.get("is_im"):
            return f"DM with {self.user_name(c.get('user'))}"
        if c.get("is_mpim"):
            return "Group chat: " + (c.get("purpose", {}).get("value") or c.get("name", ""))
        return f"#{c.get('name', c['id'])}"

    # --- messages ----------------------------------------------------------

    def history(self, channel: str, oldest: float, latest: float) -> list[dict]:
        return self._paginate("conversations.history", "messages", channel=channel,
                              oldest=oldest, latest=latest, inclusive="true", limit=200)

    def replies(self, channel: str, ts: str, oldest: float, latest: float) -> list[dict]:
        msgs = self._paginate("conversations.replies", "messages", channel=channel, ts=ts,
                              oldest=oldest, latest=latest, inclusive="true", limit=200)
        return [m for m in msgs if m.get("ts") != ts]

    def post_message(self, channel: str, text: str) -> None:
        self.call("chat.postMessage", http="POST", channel=channel, text=text,
                  mrkdwn=True, unfurl_links=False)

    def format_text(self, text: str) -> str:
        text = _USER_MENTION.sub(lambda m: "@" + self.user_name(m.group(1)), text)
        text = _CHANNEL_MENTION.sub(lambda m: "#" + m.group(1), text)
        text = _LINK.sub(lambda m: m.group(2) or m.group(1), text)
        text = _SPECIAL.sub(lambda m: "@" + m.group(1), text)
        return text.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")


_ARABIC_MARKS = re.compile(r"[\u064B-\u0652\u0640]")
_NON_WORD = re.compile(r"[^\w\s]|_")
_EMOJI_CODE = re.compile(r":[a-z0-9_+\-]+:")


def _normalize(text: str) -> str:
    """Lowercase, drop emoji codes, punctuation and Arabic diacritics, unify alef/yaa/taa."""
    text = _EMOJI_CODE.sub(" ", str(text).lower())
    text = _ARABIC_MARKS.sub("", text)
    text = text.translate(str.maketrans("أإآىة", "ااايه"))
    return " ".join(_NON_WORD.sub(" ", text).split())


def configured_conversations(sl_cfg: dict) -> list[str]:
    refs = [*(sl_cfg.get("channels") or []), *(sl_cfg.get("direct_messages") or []),
            *(sl_cfg.get("conversations") or [])]
    return [str(r).strip() for r in dict.fromkeys(refs) if r and str(r).strip()]


def reader_client() -> SlackClient:
    token = os.environ.get("SLACK_USER_TOKEN") or os.environ.get("SLACK_BOT_TOKEN")
    if not token:
        raise RuntimeError("Set SLACK_USER_TOKEN (or SLACK_BOT_TOKEN) in .env")
    return SlackClient(token)


def collect(cfg: dict, window: DayWindow) -> dict:
    sl_cfg = cfg.get("slack") or {}
    if not sl_cfg.get("enabled") or not configured_conversations(sl_cfg):
        return {"conversations": []}

    client = reader_client()
    users = set(sl_cfg.get("users") or [])
    keywords = [k.lower() for k in sl_cfg.get("keywords") or []]
    include_bots = sl_cfg.get("include_bots", False)
    phrases = sorted({_normalize(p) for p in sl_cfg.get("ignore_messages") or []} - {""},
                     key=len, reverse=True)
    ignore = [re.compile(rf"(?:^|\s){re.escape(p)}(?=\s|$)") for p in phrases]
    leftover = int(sl_cfg.get("ignore_leftover_words", 2))
    lookback = timedelta(days=int(sl_cfg.get("thread_lookback_days", 7)))
    day_start, day_end = window.start.timestamp(), window.end.timestamp()

    def in_day(msg: dict) -> bool:
        return day_start <= float(msg["ts"]) < day_end

    def keep(msg: dict) -> bool:
        if msg.get("subtype") in _SKIP_SUBTYPES:
            return False
        if not include_bots and (msg.get("bot_id") or msg.get("subtype") == "bot_message"):
            return False
        if users and msg.get("user") not in users:
            return False
        text = (msg.get("text") or "").lower()
        if ignore:
            rest, matched = _normalize(text), False
            for pattern in ignore:
                rest, n = pattern.subn(" ", rest)
                matched = matched or n > 0
            if not rest.split() or (matched and len(rest.split()) <= leftover):
                return False
        return not keywords or any(k in text for k in keywords)

    def fmt(msg: dict) -> dict:
        return {
            "user": client.user_name(msg.get("user")) if msg.get("user")
            else msg.get("username", "bot"),
            "text": client.format_text(msg.get("text", "")),
            "time": datetime.fromtimestamp(float(msg["ts"]), window.start.tzinfo)
            .strftime("%H:%M"),
            "date": datetime.fromtimestamp(float(msg["ts"]), window.start.tzinfo)
            .strftime("%Y-%m-%d"),
            "ts": msg["ts"],
        }

    results = []
    for ref in configured_conversations(sl_cfg):
        try:
            conv_id, name = client.resolve(ref)
            history = client.history(conv_id, (window.start - lookback).timestamp(), day_end)
            threads = []
            for msg in history:
                # Broadcast replies also appear in history; they are picked up via replies.
                if msg.get("thread_ts") not in (None, msg["ts"]):
                    continue
                parent_today = in_day(msg) and keep(msg)
                replies = []
                if msg.get("reply_count") and float(msg.get("latest_reply", 0)) >= day_start:
                    replies = [fmt(r) for r in
                               client.replies(conv_id, msg["ts"], day_start, day_end)
                               if in_day(r) and keep(r)]
                if parent_today or replies:
                    threads.append({
                        **fmt(msg),
                        "from_earlier": not in_day(msg),
                        "replies": sorted(replies, key=lambda r: float(r["ts"])),
                    })
            threads.sort(key=lambda t: float(t["ts"]))
            results.append({
                "id": conv_id,
                "name": name,
                "threads": threads,
                "message_count": sum((not t["from_earlier"]) + len(t["replies"])
                                     for t in threads),
            })
        except Exception as exc:
            log.error("Slack conversation %s failed: %s", ref, exc)
            results.append({"id": ref, "name": ref, "error": str(exc),
                            "threads": [], "message_count": 0})

    return {"conversations": results}
