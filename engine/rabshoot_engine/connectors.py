"""Build API clients from stored connections, test them and list pickable items."""

import logging
import socket
import time

import requests

from . import storage
from .ai import AIClient, DEFAULT_FALLBACKS, DEFAULT_MODEL, GEMINI_BASE_URL
from .auth import gitlab_oauth, slack_oauth
from .mail import imap, smtp
from .mail.providers import with_defaults
from .models import Connection
from .sources.github import GitHubClient, repo_summary
from .sources.gitlab import GITLAB_COM, GitLabClient, project_summary
from .sources.slack import SlackClient

log = logging.getLogger(__name__)


class ConnectionError_(RuntimeError):
    """A connection that needs the user's attention (bad password, revoked token…)."""


def _secret(conn: Connection) -> dict:
    secret = storage.get_secret(conn.id)
    if not secret:
        raise ConnectionError_(f"No credentials saved for '{conn.label or conn.type}'")
    return secret


def email_credentials(conn: Connection) -> tuple[dict, str]:
    meta = with_defaults(conn.meta)
    return meta, _secret(conn).get("password", "")


def gitlab_client(conn: Connection) -> GitLabClient:
    secret = _secret(conn)
    base_url = conn.meta.get("url") or GITLAB_COM
    if secret.get("oauth") and secret.get("refresh_token") and \
            secret.get("expires_at", 0) < time.time() + 120:
        secret = gitlab_oauth.refresh(base_url, secret)
        storage.set_secret(conn.id, secret)
    return GitLabClient(base_url, secret["token"], oauth=bool(secret.get("oauth")))


def github_client(conn: Connection) -> GitHubClient:
    secret = _secret(conn)
    if secret.get("expires_at") and secret["expires_at"] < time.time():
        raise ConnectionError_("GitHub sign-in expired; reconnect the account")
    return GitHubClient(secret["token"])


def slack_client(conn: Connection) -> SlackClient:
    secret = _secret(conn)
    if secret.get("oauth") and secret.get("refresh_token") and \
            secret.get("expires_at", 0) < time.time() + 120:
        secret = slack_oauth.refresh(secret)
        storage.set_secret(conn.id, secret)
    return SlackClient(secret["token"])


def ai_client(conn: Connection, language: str = "English", extra: str = "",
              max_points: int = 6) -> AIClient:
    meta = conn.meta
    return AIClient(
        api_key=_secret(conn)["key"],
        base_url=meta.get("base_url") or GEMINI_BASE_URL,
        model=meta.get("model") or DEFAULT_MODEL,
        fallback_models=meta.get("fallback_models", DEFAULT_FALLBACKS),
        language=language, extra_instructions=extra, max_points=max_points,
    )


def code_client(conn: Connection):
    return gitlab_client(conn) if conn.type == "gitlab" else github_client(conn)


def _friendly(exc: Exception) -> str:
    if isinstance(exc, requests.HTTPError) and exc.response is not None:
        code = exc.response.status_code
        if code == 401:
            return "The token was rejected (invalid, expired or revoked)"
        if code == 403:
            return "Access denied: the token is missing permissions"
        if code == 404:
            return "Not found: check the server URL"
        return f"HTTP {code}: {exc.response.text[:200]}"
    if isinstance(exc, requests.ConnectionError):
        return "Cannot reach the server (check the URL and your internet connection)"
    if isinstance(exc, (socket.gaierror, TimeoutError, ConnectionRefusedError)) or \
            "name resolution" in str(exc) or "Name or service not known" in str(exc):
        return "Cannot reach the server (check your internet connection and the server address)"
    text = str(exc)
    if "AUTHENTICATIONFAILED" in text or "Username and Password not accepted" in text \
            or "535" in text:
        return "Email sign-in failed: check the address and the app password"
    if "invalid_auth" in text or "not_authed" in text or "token_revoked" in text:
        return "Slack rejected the token (invalid or revoked)"
    return text or exc.__class__.__name__


def is_auth_error(exc: Exception) -> bool:
    if isinstance(exc, requests.HTTPError) and exc.response is not None:
        return exc.response.status_code in (401, 403)
    text = str(exc)
    return any(k in text for k in ("invalid_auth", "not_authed", "token_revoked", "token_expired"))


def mark_failed(conn: Connection, exc: Exception) -> None:
    """A rejected token shows up on the account (red) instead of only inside one run."""
    if is_auth_error(exc):
        conn.status, conn.status_message = "error", _friendly(exc)
        storage.save_connection(conn)


def test(conn: Connection) -> dict:
    """Validate credentials; returns {ok, message, meta} and stores the status."""
    meta_updates: dict = {}
    try:
        if conn.type == "email":
            meta, password = email_credentials(conn)
            smtp.test_login(meta, password)
            try:
                imap.test_login(meta, password)
                meta_updates["imap_ok"] = True
                message = "Sending and mailbox access work"
            except Exception as exc:
                meta_updates["imap_ok"] = False
                message = f"Sending works, but mailbox access failed ({_friendly(exc)}). " \
                          "Thread replies and suggestions will not be available."
        elif conn.type == "gitlab":
            user = gitlab_client(conn).user()
            meta_updates = {"username": user.get("username"), "name": user.get("name"),
                            "avatar": user.get("avatar_url")}
            message = f"Connected as @{user.get('username')}"
        elif conn.type == "github":
            user = github_client(conn).user()
            meta_updates = {"username": user.get("login"), "name": user.get("name"),
                            "avatar": user.get("avatar_url")}
            message = f"Connected as @{user.get('login')}"
        elif conn.type == "slack":
            info = slack_client(conn).auth_test()
            meta_updates = {"team": info.get("team"), "team_id": info.get("team_id"),
                            "user": info.get("user"), "user_id": info.get("user_id"),
                            "url": info.get("url")}
            message = f"Connected to {info.get('team')} as {info.get('user')}"
        elif conn.type == "ai":
            model = ai_client(conn).ping()
            meta_updates = {"working_model": model}
            message = f"AI key works (model {model})"
        else:
            raise ValueError(f"Unknown connection type {conn.type}")
        ok = True
    except Exception as exc:
        log.warning("Test of %s failed: %s", conn.id, exc)
        ok, message = False, _friendly(exc)

    conn.meta.update({k: v for k, v in meta_updates.items() if v is not None})
    conn.status = "ok" if ok else "error"
    conn.status_message = message
    if any(c.id == conn.id for c in storage.list_connections()):
        storage.save_connection(conn)
    return {"ok": ok, "message": message, "meta": conn.meta}


def default_label(conn: Connection) -> str:
    m = conn.meta
    if conn.type == "email":
        return m.get("address", "Email")
    if conn.type in ("gitlab", "github"):
        host = (m.get("url") or "").replace("https://", "") if conn.type == "gitlab" else "GitHub"
        return f"{m.get('username') or ''} · {host or 'gitlab.com'}".strip(" ·")
    if conn.type == "slack":
        return m.get("team") or "Slack"
    return "Google Gemini"


def list_projects(conn: Connection) -> list[dict]:
    if conn.type == "gitlab":
        return [project_summary(p) for p in gitlab_client(conn).projects(max_pages=5)]
    if conn.type == "github":
        return [repo_summary(r) for r in github_client(conn).repos(max_pages=5)]
    raise ValueError("Not a code connection")
