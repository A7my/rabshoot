"""Slack sign-in to a workspace's shared RabShoot app (OAuth v2 + PKCE, user scopes only).

One person creates the app once per workspace (manifest has PKCE on and our loopback redirect);
everyone else signs in with its Client ID, so no extra app slot is used and no secret is shared.
"""

import re
import time
from urllib.parse import urlencode, urlparse

import requests

from ..sources.slack import SLACK_REDIRECT_URL, USER_SCOPES
from .loopback import LoopbackFlows, pkce_pair

REDIRECT_PORT = urlparse(SLACK_REDIRECT_URL).port
REDIRECT_PATH = urlparse(SLACK_REDIRECT_URL).path
AUTHORIZE_URL = "https://slack.com/oauth/v2/authorize"
ACCESS_URL = "https://slack.com/api/oauth.v2.access"
CLIENT_ID_RE = re.compile(r"^\d{5,}\.\d{5,}$")

_flows = LoopbackFlows("Slack")

_ERRORS = {
    "invalid_team_for_non_distributed_app":
        "This team code belongs to a different Slack workspace. Use the code of your own "
        "workspace's RabShoot app.",
    "bad_client_secret":
        "Slack refused the sign-in because PKCE is off for this app. The app's owner should turn "
        "on PKCE under OAuth & Permissions.",
    "invalid_client_id": "Slack doesn't know this team code. Check it and try again.",
    "bad_redirect_uri":
        f"The app is missing the redirect URL {SLACK_REDIRECT_URL} "
        "(OAuth & Permissions → Redirect URLs).",
    "invalid_code": "The sign-in expired. Try again.",
    "code_already_used": "The sign-in expired. Try again.",
    "invalid_refresh_token": "Your Slack sign-in expired. Sign in again.",
}


def redirect_uri() -> str:
    return SLACK_REDIRECT_URL


def clean_client_id(client_id: str) -> str:
    client_id = (client_id or "").strip()
    if not CLIENT_ID_RE.match(client_id):
        raise ValueError("That doesn't look like a team code. It is the app's Client ID: numbers "
                         "with a dot, like 1234567890.1234567890123")
    return client_id


def start(client_id: str) -> dict:
    client_id = clean_client_id(client_id)
    verifier, challenge = pkce_pair()
    flow_id, flow = _flows.start(REDIRECT_PORT, REDIRECT_PATH, _exchange,
                                 client_id=client_id, verifier=verifier)
    url = f"{AUTHORIZE_URL}?" + urlencode({
        "client_id": client_id, "scope": "", "user_scope": ",".join(USER_SCOPES),
        "redirect_uri": redirect_uri(), "state": flow["state"],
        "code_challenge": challenge, "code_challenge_method": "S256",
    })
    return {"flow_id": flow_id, "authorize_url": url}


def status(flow_id: str) -> dict:
    return _flows.status(flow_id)


def _call(payload: dict) -> dict:
    resp = requests.post(ACCESS_URL, data=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if not data.get("ok"):
        code = data.get("error", "unknown_error")
        raise RuntimeError(_ERRORS.get(code, f"Slack sign-in failed ({code})"))
    return data


def _exchange(flow: dict, code: str) -> dict:
    data = _call({"client_id": flow["client_id"], "code": code, "redirect_uri": redirect_uri(),
                  "code_verifier": flow["verifier"]})
    return {"token": _secret(data.get("authed_user") or {}, flow["client_id"]),
            "client_id": flow["client_id"]}


def _secret(user: dict, client_id: str) -> dict:
    token = user.get("access_token")
    if not token:
        raise RuntimeError("Slack did not return a user token. Make sure the app asks for user "
                           "scopes (create it from RabShoot's manifest).")
    secret = {"token": token, "oauth": True, "client_id": client_id}
    if user.get("refresh_token"):
        secret["refresh_token"] = user["refresh_token"]
        secret["expires_at"] = time.time() + int(user.get("expires_in", 43200))
    return secret


def refresh(secret: dict) -> dict:
    """Only for apps with token rotation on; PKCE refreshes need no client secret."""
    data = _call({"client_id": secret["client_id"], "grant_type": "refresh_token",
                  "refresh_token": secret["refresh_token"]})
    return _secret(data.get("authed_user") or data, secret["client_id"])
