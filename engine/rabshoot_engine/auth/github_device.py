"""GitHub OAuth Device Flow: show a code, the user approves on github.com, we poll."""

import threading
import time
import uuid

import requests

from . import GITHUB_CLIENT_ID

DEVICE_URL = "https://github.com/login/device/code"
TOKEN_URL = "https://github.com/login/oauth/access_token"
GRANT = "urn:ietf:params:oauth:grant-type:device_code"
# PAT fallback: pre-filled classic token page (read-only scopes).
TOKEN_PAGE = "https://github.com/settings/tokens/new?description=RabShoot&scopes=repo,read:org"

_flows: dict[str, dict] = {}
_lock = threading.Lock()


def start() -> dict:
    if not GITHUB_CLIENT_ID:
        raise RuntimeError("GitHub sign-in is not configured in this build; use a token instead")
    resp = requests.post(DEVICE_URL, data={"client_id": GITHUB_CLIENT_ID, "scope": "repo read:org"},
                         headers={"Accept": "application/json"}, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if "device_code" not in data:
        raise RuntimeError(data.get("error_description") or data.get("error") or "Device flow failed")
    flow_id = uuid.uuid4().hex
    with _lock:
        _flows[flow_id] = {
            "device_code": data["device_code"],
            "interval": int(data.get("interval", 5)),
            "expires_at": time.time() + int(data.get("expires_in", 900)),
            "next_poll": 0.0,
        }
    return {"flow_id": flow_id, "user_code": data["user_code"],
            "verification_uri": data.get("verification_uri", "https://github.com/login/device"),
            "expires_in": int(data.get("expires_in", 900)), "interval": int(data.get("interval", 5))}


def poll(flow_id: str) -> dict:
    """{'status': pending|done|expired|denied|error, 'token'?: {...}}"""
    with _lock:
        flow = _flows.get(flow_id)
    if not flow:
        return {"status": "error", "message": "Unknown sign-in session"}
    if time.time() > flow["expires_at"]:
        _flows.pop(flow_id, None)
        return {"status": "expired"}
    if time.time() < flow["next_poll"]:
        return {"status": "pending"}
    resp = requests.post(TOKEN_URL, data={"client_id": GITHUB_CLIENT_ID,
                                          "device_code": flow["device_code"], "grant_type": GRANT},
                         headers={"Accept": "application/json"}, timeout=30)
    data = resp.json() if resp.ok else {"error": f"http_{resp.status_code}"}
    error = data.get("error")
    if error == "authorization_pending":
        flow["next_poll"] = time.time() + flow["interval"]
        return {"status": "pending"}
    if error == "slow_down":
        flow["interval"] = int(data.get("interval", flow["interval"] + 5))
        flow["next_poll"] = time.time() + flow["interval"]
        return {"status": "pending"}
    _flows.pop(flow_id, None)
    if error == "expired_token":
        return {"status": "expired"}
    if error == "access_denied":
        return {"status": "denied"}
    if error:
        return {"status": "error", "message": data.get("error_description") or error}
    token = {"token": data["access_token"]}
    if data.get("refresh_token"):
        token["refresh_token"] = data["refresh_token"]
        token["expires_at"] = time.time() + int(data.get("expires_in", 28800))
    return {"status": "done", "token": token}
