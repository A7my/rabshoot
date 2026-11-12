import email
import imaplib
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from email import policy
from email.utils import getaddresses, parsedate_to_datetime

from ..models import ThreadRef
from .providers import with_defaults

_THRID = re.compile(rb"X-GM-THRID (\d+)")
_UID = re.compile(rb"UID (\d+)")
_LIST = re.compile(rb'^\((?P<flags>[^)]*)\) (?P<delim>"[^"]*"|NIL) (?P<name>.+)$')
_REPLY_PREFIX = re.compile(r"^\s*((re|fw|fwd|aw|sv|رد)\s*:\s*)+", re.IGNORECASE)
_HEADERS = "(SUBJECT FROM TO CC DATE MESSAGE-ID REPLY-TO REFERENCES)"


@dataclass
class ThreadParent:
    message_id: str
    references: str
    subject: str
    reply_to: list[str]
    to: list[str]
    cc: list[str]
    participants: list[str] = field(default_factory=list)  # everyone in the whole thread


def addresses(values) -> list[str]:
    return [addr for _, addr in getaddresses([str(v) for v in values or []]) if addr]


def reply_subject(subject: str) -> str:
    return "Re: " + _REPLY_PREFIX.sub("", subject).strip()


def base_subject(subject: str) -> str:
    return " ".join(_REPLY_PREFIX.sub("", subject or "").split())


def reply_all_recipients(parent: ThreadParent, me: str) -> tuple[list[str], list[str]]:
    """Everyone on the newest message except me; if that was only me, everyone in the thread."""
    me = me.lower()
    seen, to, cc = {me}, [], []
    buckets = [(to, parent.reply_to + parent.to), (cc, parent.cc), (to, parent.participants)]
    for i, (bucket, addrs) in enumerate(buckets):
        if i == 2 and (to or cc):
            break
        for addr in addrs:
            if addr.lower() not in seen:
                seen.add(addr.lower())
                bucket.append(addr)
    if not to and cc:
        to, cc = cc[:1], cc[1:]
    return to, cc


class Mailbox:
    def __init__(self, meta: dict, password: str):
        self.meta = with_defaults(meta)
        host = self.meta.get("imap_host")
        if not host:
            raise ValueError("IMAP server is not set")
        self.gmail = host == "imap.gmail.com"
        self.imap = imaplib.IMAP4_SSL(host, int(self.meta.get("imap_port") or 993), timeout=30)
        self.imap.login(self.meta["username"], password)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        try:
            self.imap.logout()
        except Exception:
            pass

    def special_folder(self, flag: str) -> str | None:
        typ, data = self.imap.list()
        if typ != "OK":
            return None
        for line in data or []:
            if not isinstance(line, bytes):
                continue
            m = _LIST.match(line)
            if m and flag.encode().lower() in m.group("flags").lower():
                return m.group("name").decode("utf-8", "replace")
        return None

    def select_all(self) -> None:
        """Gmail 'All Mail' (so sent + received are searched), otherwise INBOX."""
        folder = self.special_folder("\\All") if self.gmail else None
        if not folder or self.imap.select(folder, readonly=True)[0] != "OK":
            self.imap.select("INBOX", readonly=True)

    def select_sent(self) -> bool:
        folder = self.special_folder("\\Sent")
        return bool(folder) and self.imap.select(folder, readonly=True)[0] == "OK"

    def search_raw(self, query: str) -> list[bytes]:
        self.imap.literal = query.encode("utf-8")
        typ, data = self.imap.uid("SEARCH", "CHARSET", "UTF-8", "X-GM-RAW")
        return data[0].split() if typ == "OK" and data and data[0] else []

    def search(self, *criteria: str) -> list[bytes]:
        typ, data = self.imap.uid("SEARCH", None, *criteria)
        return data[0].split() if typ == "OK" and data and data[0] else []

    def fetch_headers(self, uids: list[bytes]) -> list[dict]:
        if not uids:
            return []
        items = []
        parts = "(UID X-GM-THRID BODY.PEEK[HEADER.FIELDS " if self.gmail else "(UID BODY.PEEK[HEADER.FIELDS "
        typ, data = self.imap.uid("FETCH", b",".join(uids), parts + _HEADERS + "])")
        if typ != "OK":
            return []
        for part in data:
            if not isinstance(part, tuple):
                continue
            meta, raw = part
            msg = email.message_from_bytes(raw, policy=policy.default)
            thrid = _THRID.search(meta)
            uid = _UID.search(meta)
            try:
                date = parsedate_to_datetime(str(msg.get("Date"))) if msg.get("Date") else None
            except (TypeError, ValueError):
                date = None
            items.append({
                "uid": uid.group(1).decode() if uid else "",
                "thrid": thrid.group(1).decode() if thrid else "",
                "subject": str(msg.get("Subject", "") or ""),
                "from": addresses(msg.get_all("From")),
                "reply_to": addresses(msg.get_all("Reply-To")),
                "to": addresses(msg.get_all("To")),
                "cc": addresses(msg.get_all("Cc")),
                "message_id": str(msg.get("Message-ID", "") or "").strip(),
                "references": " ".join(str(msg.get("References", "") or "").split()),
                "date": date,
            })
        return items


def list_threads(meta: dict, password: str, query: str = "", days: int = 60,
                 limit: int = 40) -> list[dict]:
    """Recent conversations in the mailbox, newest first."""
    with Mailbox(meta, password) as box:
        box.select_all()
        since = (datetime.now() - timedelta(days=days)).strftime("%d-%b-%Y")
        if box.gmail:
            raw = f"newer_than:{days}d" + (f" {query}" if query else "")
            uids = box.search_raw(raw)
        elif query:
            box.imap.literal = query.encode("utf-8")
            typ, data = box.imap.uid("SEARCH", "CHARSET", "UTF-8", "SINCE", since, "SUBJECT")
            uids = data[0].split() if typ == "OK" and data and data[0] else []
        else:
            uids = box.search("SINCE", since)
        headers = box.fetch_headers(uids[-300:])

    me = box.meta["address"].lower()
    groups: dict[str, list[dict]] = {}
    for h in headers:
        key = h["thrid"] or base_subject(h["subject"]).lower()
        groups.setdefault(key, []).append(h)

    threads = []
    for key, msgs in groups.items():
        msgs.sort(key=lambda m: m["date"].timestamp() if m["date"] else 0)
        latest = msgs[-1]
        people = []
        for m in msgs:
            for a in m["from"] + m["to"] + m["cc"]:
                if a.lower() != me and a.lower() not in {p.lower() for p in people}:
                    people.append(a)
        threads.append({
            "key": key,
            "subject": base_subject(msgs[0]["subject"]) or "(no subject)",
            "message_id": latest["message_id"],
            "gm_thrid": latest["thrid"],
            "count": len(msgs),
            "last_date": latest["date"].isoformat() if latest["date"] else None,
            "participants": people[:12],
            "last_from": (latest["from"] or [""])[0],
        })
    threads.sort(key=lambda t: t["last_date"] or "", reverse=True)
    return threads[:limit]


def contacts(meta: dict, password: str, query: str = "", limit: int = 20) -> list[dict]:
    """People the user recently emailed, most frequent first (for autocomplete)."""
    with Mailbox(meta, password) as box:
        if box.gmail:
            box.select_all()
            uids = box.search_raw("from:me newer_than:180d")
        elif box.select_sent():
            uids = box.search("SINCE", (datetime.now() - timedelta(days=180)).strftime("%d-%b-%Y"))
        else:
            return []
        headers = box.fetch_headers(uids[-400:])
    me = box.meta["address"].lower()
    counts: Counter[str] = Counter()
    names: dict[str, str] = {}
    for h in headers:
        for addr in h["to"] + h["cc"]:
            low = addr.lower()
            if low != me:
                counts[low] += 1
                names.setdefault(low, addr)
    q = query.lower().strip()
    return [{"email": names[a], "count": n} for a, n in counts.most_common()
            if not q or q in a][:limit]


def find_parent(meta: dict, password: str, ref: ThreadRef) -> ThreadParent:
    """Newest message of the chosen thread, to reply to."""
    with Mailbox(meta, password) as box:
        box.select_all()
        uids: list[bytes] = []
        if box.gmail and ref.gm_thrid:
            uids = box.search("X-GM-THRID", ref.gm_thrid)
        if not uids and ref.message_id:
            mid = ref.message_id if ref.message_id.startswith("<") else f"<{ref.message_id}>"
            uids = box.search("HEADER", "Message-ID", f'"{mid}"')
            if uids and box.gmail:
                info = box.fetch_headers(uids[-1:])
                if info and info[0]["thrid"]:
                    uids = box.search("X-GM-THRID", info[0]["thrid"]) or uids
        if not uids and ref.subject:
            if box.gmail:
                uids = box.search_raw(f'subject:"{base_subject(ref.subject)}"')
            else:
                box.imap.literal = base_subject(ref.subject).encode("utf-8")
                typ, data = box.imap.uid("SEARCH", "CHARSET", "UTF-8", "SUBJECT")
                uids = data[0].split() if typ == "OK" and data and data[0] else []
        if not uids:
            raise LookupError("The selected email thread was not found in the sender's mailbox")
        headers = box.fetch_headers(uids[-20:])

    headers.sort(key=lambda m: m["date"].timestamp() if m["date"] else 0)
    latest = headers[-1]
    everyone: list[str] = []
    for m in reversed(headers):
        for addr in m["reply_to"] + m["from"] + m["to"] + m["cc"]:
            if addr.lower() not in {e.lower() for e in everyone}:
                everyone.append(addr)
    return ThreadParent(
        message_id=latest["message_id"],
        references=latest["references"],
        subject=latest["subject"] or ref.subject,
        reply_to=latest["reply_to"] or latest["from"],
        to=latest["to"],
        cc=latest["cc"],
        participants=everyone,
    )


def test_login(meta: dict, password: str) -> None:
    with Mailbox(meta, password) as box:
        box.select_all()
