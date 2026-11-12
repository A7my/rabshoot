"""SMTP/IMAP presets plus the pages users need to create an app password."""

PROVIDERS: dict[str, dict] = {
    "gmail": {
        "label": "Gmail / Google Workspace",
        "smtp_host": "smtp.gmail.com", "smtp_port": 587,
        "imap_host": "imap.gmail.com", "imap_port": 993,
        "app_password_url": "https://myaccount.google.com/apppasswords",
        "two_factor_url": "https://myaccount.google.com/signinoptions/twosv",
        "domains": ["gmail.com", "googlemail.com"],
    },
    "outlook": {
        "label": "Outlook / Microsoft 365",
        "smtp_host": "smtp.office365.com", "smtp_port": 587,
        "imap_host": "outlook.office365.com", "imap_port": 993,
        "app_password_url": "https://account.live.com/proofs/AppPassword",
        "two_factor_url": "https://account.microsoft.com/security",
        "domains": ["outlook.com", "hotmail.com", "live.com", "msn.com"],
        "note": "Microsoft is retiring password sign-in for SMTP/IMAP. Microsoft 365 admins "
                "must allow 'Authenticated SMTP' for your mailbox.",
    },
    "yahoo": {
        "label": "Yahoo Mail",
        "smtp_host": "smtp.mail.yahoo.com", "smtp_port": 465,
        "imap_host": "imap.mail.yahoo.com", "imap_port": 993,
        "app_password_url": "https://login.yahoo.com/account/security/app-passwords",
        "two_factor_url": "https://login.yahoo.com/account/security",
        "domains": ["yahoo.com", "ymail.com"],
    },
    "zoho": {
        "label": "Zoho Mail",
        "smtp_host": "smtp.zoho.com", "smtp_port": 465,
        "imap_host": "imap.zoho.com", "imap_port": 993,
        "app_password_url": "https://accounts.zoho.com/home#security/app_password",
        "two_factor_url": "https://accounts.zoho.com/home#security/multifactor",
        "domains": ["zoho.com", "zohomail.com"],
    },
    "icloud": {
        "label": "iCloud Mail",
        "smtp_host": "smtp.mail.me.com", "smtp_port": 587,
        "imap_host": "imap.mail.me.com", "imap_port": 993,
        "app_password_url": "https://account.apple.com/account/manage",
        "two_factor_url": "https://account.apple.com/account/manage",
        "domains": ["icloud.com", "me.com", "mac.com"],
    },
    "custom": {
        "label": "Other (custom SMTP)",
        "smtp_host": "", "smtp_port": 587, "imap_host": "", "imap_port": 993,
        "domains": [],
    },
}


def guess_provider(address: str) -> str:
    domain = address.rsplit("@", 1)[-1].lower()
    for key, preset in PROVIDERS.items():
        if domain in preset["domains"]:
            return key
    return "custom"


def with_defaults(meta: dict) -> dict:
    """Fill host/port from the provider preset when the user left them empty."""
    preset = PROVIDERS.get(meta.get("provider") or "custom", PROVIDERS["custom"])
    out = dict(meta)
    for key in ("smtp_host", "smtp_port", "imap_host", "imap_port"):
        if not out.get(key):
            out[key] = preset[key]
    if not out.get("username"):
        out["username"] = out.get("address", "")
    return out
