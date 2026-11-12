import time
from urllib.parse import parse_qs, urlparse

import pytest
import requests
from fastapi.testclient import TestClient

from rabshoot_engine import connectors, storage
from rabshoot_engine.api import create_app
from rabshoot_engine.auth import slack_oauth
from rabshoot_engine.sources.slack import SLACK_REDIRECT_URL, manifest


def _browser_returns(authorize_url: str, **params) -> str:
    query = parse_qs(urlparse(authorize_url).query)
    params.setdefault("state", query["state"][0])
    return requests.get(query["redirect_uri"][0], params=params, timeout=5).text


def _wait(flow_id: str, client: TestClient | None = None) -> dict:
    for _ in range(50):
        result = (client.get("/auth/slack/oauth/status", params={"flow_id": flow_id}).json()
                  if client else slack_oauth.status(flow_id))
        if result["status"] != "pending":
            return result
        time.sleep(0.1)
    raise AssertionError("sign-in never finished")


def test_manifest_enables_pkce_with_our_redirect():
    oauth = manifest()["oauth_config"]
    assert oauth["pkce_enabled"] is True
    assert oauth["redirect_urls"] == [SLACK_REDIRECT_URL] == [slack_oauth.redirect_uri()]
    assert "bot" not in oauth["scopes"]  # desktop PKCE redirects may only request user scopes


def test_rejects_malformed_team_code():
    with pytest.raises(ValueError):
        slack_oauth.start("not-a-client-id")


def test_sign_in_creates_connection_without_client_secret(isolated_home, monkeypatch):
    sent = {}

    def fake_call(payload):
        sent.update(payload)
        return {"ok": True, "authed_user": {"id": "U1", "access_token": "xoxp-new"},
                "team": {"id": "T1", "name": "Acme"}}

    monkeypatch.setattr(slack_oauth, "_call", fake_call)
    monkeypatch.setattr(connectors, "test", lambda conn: {"ok": True, "message": "ok", "meta": {}})
    client = TestClient(create_app("t"), headers={"Authorization": "Bearer t"})

    started = client.post("/auth/slack/oauth/start", json={"client_id": "1234567.7654321"}).json()
    query = parse_qs(urlparse(started["authorize_url"]).query)
    assert query["client_id"] == ["1234567.7654321"]
    assert query["code_challenge_method"] == ["S256"] and "user_scope" in query

    assert "connected to Slack" in _browser_returns(started["authorize_url"], code="abc")
    result = _wait(started["flow_id"], client)
    assert result["status"] == "done"
    conn = result["connection"]
    assert conn["type"] == "slack" and conn["meta"]["client_id"] == "1234567.7654321"
    assert storage.get_secret(conn["id"])["token"] == "xoxp-new"
    assert sent["code"] == "abc" and sent["code_verifier"] and "client_secret" not in sent


def test_wrong_workspace_is_explained(monkeypatch):
    def fake_call(payload):
        raise RuntimeError(slack_oauth._ERRORS["invalid_team_for_non_distributed_app"])

    monkeypatch.setattr(slack_oauth, "_call", fake_call)
    started = slack_oauth.start("1234567.7654321")
    page = _browser_returns(started["authorize_url"], code="abc")
    assert "sign-in failed" in page
    result = _wait(started["flow_id"])
    assert result["status"] == "error" and "different Slack workspace" in result["message"]


def test_cancelled_in_browser(monkeypatch):
    started = slack_oauth.start("1234567.7654321")
    _browser_returns(started["authorize_url"], error="access_denied")
    assert _wait(started["flow_id"]) == {"status": "denied", "message": "Sign-in was cancelled"}
