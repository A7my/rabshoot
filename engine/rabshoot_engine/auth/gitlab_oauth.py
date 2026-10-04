"""GitLab OAuth (authorization code + PKCE) with a one-shot loopback listener."""

import time
from urllib.parse import urlencode

import requests

from . import GITLAB_CLIENT_ID, GITLAB_REDIRECT_PORT
from .loopback import LoopbackFlows, pkce_pair

SCOPES = "read_api read_user"
_flows = LoopbackFlows("GitLab")


def token_page(base_url: str) -> str:
    """Pre-filled personal access token page (self-hosted or no OAuth app)."""
    return (f"{base_url.rstrip('/')}/-/user_settings/personal_access_tokens"
            f"?name=RabShoot&scopes=read_api,read_user")


def redirect_uri() -> str:
    return f"http://127.0.0.1:{GITLAB_REDIRECT_PORT}/callback"


def start(base_url: str = "https://gitlab.com") -> dict:
    if not GITLAB_CLIENT_ID:
        raise RuntimeError("GitLab sign-in is not configured in this build; use a token instead")
    verifier, challenge = pkce_pair()
    base_url = base_url.rstrip("/")
    flow_id, flow = _flows.start(GITLAB_REDIRECT_PORT, "/callback", _exchange,
                                 base_url=base_url, verifier=verifier)
    url = f"{base_url}/oauth/authorize?" + urlencode({
        "client_id": GITLAB_CLIENT_ID, "redirect_uri": redirect_uri(), "response_type": "code",
        "state": flow["state"], "scope": SCOPES, "code_challenge": challenge,
        "code_challenge_method": "S256",
    })
    return {"flow_id": flow_id, "authorize_url": url}


def _exchange(flow: dict, code: str) -> dict:
    resp = requests.post(f"{flow['base_url']}/oauth/token", data={
        "client_id": GITLAB_CLIENT_ID, "code": code, "grant_type": "authorization_code",
        "redirect_uri": redirect_uri(), "code_verifier": flow["verifier"],
    }, timeout=30)
    resp.raise_for_status()
    return {"token": _token(resp.json()), "base_url": flow["base_url"]}


def _token(data: dict) -> dict:
    return {"token": data["access_token"], "refresh_token": data.get("refresh_token", ""),
            "expires_at": time.time() + int(data.get("expires_in", 7200)), "oauth": True}


def status(flow_id: str) -> dict:
    return _flows.status(flow_id)


def refresh(base_url: str, secret: dict) -> dict:
    resp = requests.post(f"{base_url.rstrip('/')}/oauth/token", data={
        "client_id": GITLAB_CLIENT_ID, "refresh_token": secret["refresh_token"],
        "grant_type": "refresh_token", "redirect_uri": redirect_uri(),
    }, timeout=30)
    resp.raise_for_status()
    return _token(resp.json())
