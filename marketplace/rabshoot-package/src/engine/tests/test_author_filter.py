from collections import Counter
from datetime import date

from rabshoot_engine import connectors, pipeline, storage
from rabshoot_engine.models import CodeSource, Connection, Profile
from rabshoot_engine.sources import gitlab
from rabshoot_engine.window import DayWindow

WINDOW = DayWindow.for_day(date(2026, 9, 29), "Africa/Cairo")
COMMITS = [
    {"id": "1", "short_id": "1", "title": "net worth", "author_name": "Dev",
     "author_email": "laptop@example.com", "created_at": "2026-09-29T10:00:00Z", "parent_ids": ["0"]},
    {"id": "2", "short_id": "2", "title": "ui", "author_name": "Saber",
     "author_email": "saber@example.com", "created_at": "2026-09-29T11:00:00Z", "parent_ids": ["0"]},
]


class FakeGitLab:
    """Account 'devuser' whose local git config signs commits as Dev <laptop@example.com>."""

    base_url = "https://gitlab.com"

    def user(self):
        return {"id": 7, "username": "devuser", "name": "dev user",
                "email": "dev@example.com"}

    def user_by_username(self, username):
        return {"id": 9, "username": username, "name": "Saber"} if username == "saber" else None

    def push_events(self, user_id, after, before):
        assert after < date(2026, 9, 29) < before
        return [{"project_id": 1, "push_data": {"commit_to": "1"}}] if user_id == 7 else []

    def commit(self, project_id, sha):
        return next(c for c in COMMITS if c["id"] == sha)

    def projects(self, since):
        return [{"id": 1, "path_with_namespace": "team/asol-sync", "web_url": "u"}]

    def commits(self, pid, since, until):
        return COMMITS

    def merge_requests(self, *a):
        return []

    def issues(self, *a):
        return []


def test_username_matches_commits_signed_with_another_git_identity():
    authors = gitlab.resolve_authors(FakeGitLab(), {"devuser"}, WINDOW)
    assert {"dev", "laptop@example.com", "dev@example.com"} <= authors

    skipped = Counter()
    found = gitlab.collect(FakeGitLab(), CodeSource(connection_id="c", authors=["DEVUSER "]),
                           WINDOW, want_diffs=False, max_diff_chars=0, skipped=skipped)
    assert [c["title"] for c in found[0]["commits"]] == ["net worth"]
    assert skipped == Counter({"Saber <saber@example.com>": 1})


def test_other_emails_and_names_are_used_as_is():
    assert gitlab.resolve_authors(FakeGitLab(), {"a@b.com", "someone else"}, WINDOW) == \
        {"a@b.com", "someone else"}


def test_own_account_email_or_name_matches_commits_signed_differently():
    for entry in ("dev@example.com", "dev user"):
        assert "laptop@example.com" in gitlab.resolve_authors(FakeGitLab(), {entry}, WINDOW)


def test_re_adding_an_account_refreshes_the_saved_one():
    meta = {"url": "https://gitlab.com/", "username": "devuser"}
    first = storage.save_connection(Connection(type="gitlab", meta=meta), secret={"token": "old"})
    again = storage.save_connection(Connection(type="gitlab", meta={**meta, "url": "https://gitlab.com"}),
                                    secret={"token": "new"})
    merged = storage.merge_duplicate(again)
    assert merged.id == first.id
    assert [c.id for c in storage.list_connections()] == [first.id]
    assert storage.get_secret(first.id) == {"token": "new"}
    other = storage.save_connection(Connection(type="gitlab", meta={**meta, "username": "saber"}))
    assert storage.merge_duplicate(other).id == other.id


def test_filter_that_matches_nothing_explains_who_was_skipped(monkeypatch):
    conn = storage.save_connection(Connection(type="gitlab", label="GitLab"), secret={"token": "x"})
    profile = Profile(code_sources=[CodeSource(connection_id=conn.id, authors=["nobody@x.com"])])
    monkeypatch.setattr(connectors, "code_client", lambda c: FakeGitLab())
    result = pipeline.RunResult()
    assert pipeline.collect_code(profile, WINDOW, result) == []
    step = result.steps[0]
    assert step["status"] == "warn"
    assert "Dev <laptop@example.com> (1)" in step["message"]
