from fastapi.testclient import TestClient

from rabshoot_engine import connectors
from rabshoot_engine.api import create_app

TOKEN = "t0ken"


def client():
    return TestClient(create_app(TOKEN), headers={"Authorization": f"Bearer {TOKEN}"})


def test_requires_token():
    anon = TestClient(create_app(TOKEN))
    assert anon.get("/health").status_code == 401
    health = client().get("/health").json()
    assert health["ok"] is True
    assert set(health["paths"]) == {"config", "data", "logs"}


def test_connection_is_tested_before_saving(monkeypatch):
    c = client()
    monkeypatch.setattr(connectors, "test", lambda conn: {"ok": False, "message": "bad key",
                                                          "meta": {}})
    r = c.post("/connections", json={"type": "ai", "meta": {}, "secret": {"key": "x"}})
    assert r.status_code == 400 and r.json()["detail"] == "bad key"
    assert c.get("/connections").json() == []

    monkeypatch.setattr(connectors, "test", lambda conn: {"ok": True, "message": "ok",
                                                          "meta": {}})
    r = c.post("/connections", json={"type": "ai", "meta": {}, "secret": {"key": "x"}})
    assert r.status_code == 200
    body = r.json()
    assert body["label"] == "Google Gemini" and "secret" not in body
    assert len(c.get("/connections").json()) == 1


def test_profile_crud_and_problems(monkeypatch):
    c = client()
    monkeypatch.setattr(connectors, "test", lambda conn: {"ok": True, "message": "ok",
                                                          "meta": {}})
    ai = c.post("/connections", json={"type": "ai", "secret": {"key": "x"}}).json()
    r = c.post("/profiles", json={"name": "Team", "ai_connection_id": ai["id"],
                                  "schedule": {"time": "17:30", "days": "sun-thu",
                                               "timezone": "Africa/Cairo"}})
    assert r.status_code == 200
    pid = r.json()["id"]
    listed = c.get("/profiles").json()
    assert listed[0]["problems"] == ["sender", "recipients", "code_source"]
    assert c.post(f"/profiles/{pid}/send").status_code == 400
    future = c.post(f"/profiles/{pid}/send", json={"day": "2999-01-01"})
    assert future.status_code == 400 and "earlier day" in future.json()["detail"]
    assert c.post(f"/profiles/{pid}/preview", json={"day": "2999-01-01"}).status_code == 400

    bad = c.put(f"/profiles/{pid}", json={"name": "x", "schedule": {"time": "99:00"}})
    assert bad.status_code == 422
    assert c.delete(f"/connections/{ai['id']}").status_code == 409
    assert c.delete(f"/profiles/{pid}").json() == {"ok": True}


def test_manifest_and_links():
    links = client().get("/auth/links").json()
    assert links["slack_manifest_url"].startswith("https://api.slack.com/apps?new_app=1")
    assert "personal_access_tokens" in links["gitlab_token_page"]
