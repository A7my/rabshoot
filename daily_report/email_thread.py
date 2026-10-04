import email
import imaplib
import os
import re
from dataclasses import dataclass
from email import policy
from email.utils import getaddresses

_IMAP_FOR_SMTP = {
    "smtp.gmail.com": "imap.gmail.com",
    "smtp.office365.com": "outlook.office365.com",
    "smtp-mail.outlook.com": "outlook.office365.com",
}
_THRID = re.compile(rb"X-GM-THRID (\d+)")
_REPLY_PREFIX = re.compile(r"^\s*((re|fw|fwd|رد)\s*:\s*)+", re.IGNORECASE)


@dataclass
class ThreadParent:
    message_id: str
    references: str
    subject: str
    reply_to: list[str]
    to: list[str]
    cc: list[str]


def imap_host(email_cfg: dict) -> str:
    host = email_cfg.get("imap_host") or _IMAP_FOR_SMTP.get(email_cfg.get("smtp_host", ""))
    if not host:
        raise ValueError("Set delivery.email.imap_host to reply inside a thread")
    return host


def _addresses(values) -> list[str]:
    return [addr for _, addr in getaddresses([str(v) for v in values or []]) if addr]


def _search(imap: imaplib.IMAP4_SSL, gmail: bool, thread_cfg: dict) -> list[bytes]:
    message_id = (thread_cfg.get("message_id") or "").strip()
    subject = (thread_cfg.get("subject") or "").strip()
    if message_id:
        if not message_id.startswith("<"):
            message_id = f"<{message_id}>"
        typ, data = imap.uid("SEARCH", None, "HEADER", "Message-ID", f'"{message_id}"')
    elif subject:
        imap.literal = (f'subject:"{subject}"' if gmail else subject).encode("utf-8")
        typ, data = imap.uid("SEARCH", "CHARSET", "UTF-8",
                             "X-GM-RAW" if gmail else "SUBJECT")
    else:
        raise ValueError("Set delivery.email.thread.subject or thread.message_id")
    if typ != "OK":
        raise RuntimeError(f"IMAP search failed: {data}")
    return data[0].split() if data and data[0] else []


def find_parent(email_cfg: dict) -> ThreadParent:
    """Locate the newest message of the configured thread in the sender's mailbox."""
    thread_cfg = email_cfg.get("thread") or {}
    host = imap_host(email_cfg)
    gmail = host == "imap.gmail.com"

    imap = imaplib.IMAP4_SSL(host, 993)
    try:
        imap.login(os.environ["SMTP_USER"], os.environ.get("SMTP_PASSWORD", ""))
        folder = '"[Gmail]/All Mail"' if gmail else "INBOX"
        if imap.select(folder, readonly=True)[0] != "OK":
            imap.select("INBOX", readonly=True)

        uids = _search(imap, gmail, thread_cfg)
        if not uids:
            raise LookupError("No email found for the configured thread "
                              "(is it in the sender's mailbox?)")

        latest = uids[-1]
        if gmail:
            _, meta = imap.uid("FETCH", latest, "(X-GM-THRID)")
            match = _THRID.search(meta[0] if isinstance(meta[0], bytes) else meta[0][0])
            if match:
                _, data = imap.uid("SEARCH", None, "X-GM-THRID", match.group(1).decode())
                if data and data[0]:
                    latest = data[0].split()[-1]

        _, data = imap.uid("FETCH", latest, "(BODY.PEEK[HEADER])")
        raw = next(part[1] for part in data if isinstance(part, tuple))
        msg = email.message_from_bytes(raw, policy=policy.default)
    finally:
        try:
            imap.logout()
        except Exception:
            pass

    return ThreadParent(
        message_id=str(msg.get("Message-ID", "")).strip(),
        references=" ".join(str(msg.get("References", "")).split()),
        subject=str(msg.get("Subject", "")),
        reply_to=_addresses(msg.get_all("Reply-To") or msg.get_all("From")),
        to=_addresses(msg.get_all("To")),
        cc=_addresses(msg.get_all("Cc")),
    )


def reply_subject(subject: str) -> str:
    return "Re: " + _REPLY_PREFIX.sub("", subject).strip()


def reply_all_recipients(parent: ThreadParent, me: str) -> tuple[list[str], list[str]]:
    me = me.lower()
    seen, to, cc = {me}, [], []
    for bucket, addrs in ((to, parent.reply_to + parent.to), (cc, parent.cc)):
        for addr in addrs:
            if addr.lower() not in seen:
                seen.add(addr.lower())
                bucket.append(addr)
    if not to and cc:
        to, cc = cc[:1], cc[1:]
    return to, cc
