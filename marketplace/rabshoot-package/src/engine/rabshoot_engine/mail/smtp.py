import smtplib
import ssl
from email.message import EmailMessage

from .providers import with_defaults


def connect(meta: dict, password: str) -> smtplib.SMTP:
    meta = with_defaults(meta)
    host, port = meta["smtp_host"], int(meta["smtp_port"])
    if not host:
        raise ValueError("SMTP server is not set")
    context = ssl.create_default_context()
    if port == 465 or meta.get("smtp_security") == "ssl":
        smtp = smtplib.SMTP_SSL(host, port, timeout=30, context=context)
    else:
        smtp = smtplib.SMTP(host, port, timeout=30)
        if meta.get("smtp_security") != "none":
            smtp.starttls(context=context)
    smtp.login(meta["username"], password)
    return smtp


def test_login(meta: dict, password: str) -> None:
    with connect(meta, password):
        pass


def send(meta: dict, password: str, msg: EmailMessage, recipients: list[str]) -> None:
    meta = with_defaults(meta)
    with connect(meta, password) as smtp:
        smtp.send_message(msg, from_addr=meta["address"], to_addrs=recipients)
