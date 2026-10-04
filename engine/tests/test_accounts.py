import requests

from rabshoot_engine import connectors, storage
from rabshoot_engine.models import CodeSource, Connection, Profile, SlackSelection

ME = {"url": "https://gitlab.com", "username": "devuser"}


def _gitlab(created_at: str, token: str) -> Connection:
    return storage.save_connection(Connection(type="gitlab", meta=dict(ME), created_at=created_at),
                                   secret={"token": token})


def test_saved_copies_merge_into_the_oldest_with_the_newest_token():
    old = _gitlab("2026-09-29T12:00:00+00:00", "revoked")
    mid = _gitlab("2026-10-01T12:28:00+00:00", "older")
    new = _gitlab("2026-10-01T12:48:00+00:00", "works")
    slack = storage.save_connection(Connection(type="slack", meta={"team_id": "T", "user_id": "U"}))
    profile = storage.save_profile(Profile(name="Daily", slack=SlackSelection(connection_id=slack.id),
                                           code_sources=[CodeSource(connection_id=old.id),
                                                         CodeSource(connection_id=new.id)]))

    assert storage.merge_saved_duplicates() == 2
    assert sorted(c.id for c in storage.list_connections()) == sorted([old.id, slack.id])
    assert storage.get_secret(old.id) == {"token": "works"}
    saved = storage.get_profile(profile.id)
    assert [s.connection_id for s in saved.code_sources] == [old.id]
    assert saved.slack.connection_id == slack.id
    assert storage.get_secret(mid.id) == {} and storage.merge_saved_duplicates() == 0


def test_rejected_token_marks_the_account_red():
    conn = _gitlab("2026-10-01T12:00:00+00:00", "x")
    response = requests.Response()
    response.status_code = 401
    connectors.mark_failed(conn, requests.HTTPError(response=response))
    saved = storage.get_connection(conn.id)
    assert saved.status == "error" and "rejected" in saved.status_message

    connectors.mark_failed(saved, requests.ConnectionError("offline"))
    assert storage.get_connection(conn.id).status == "error"
