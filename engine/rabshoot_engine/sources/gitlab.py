import logging
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from urllib.parse import quote

import requests

from ..models import CodeSource
from ..window import DayWindow
from . import author_match, in_window
from .diffutil import FileDiff, combine

log = logging.getLogger(__name__)

GITLAB_COM = "https://gitlab.com"
MAX_IDENTITY_LOOKUPS = 20


class GitLabClient:
    def __init__(self, base_url: str, token: str, oauth: bool = False, timeout: int = 30):
        self.base_url = (base_url or GITLAB_COM).rstrip("/")
        self.api = self.base_url + "/api/v4"
        self.session = requests.Session()
        if oauth:
            self.session.headers["Authorization"] = f"Bearer {token}"
        else:
            self.session.headers["PRIVATE-TOKEN"] = token
        self.timeout = timeout

    def _get(self, path: str, params: dict | None = None):
        resp = self.session.get(f"{self.api}{path}", params=params, timeout=self.timeout)
        resp.raise_for_status()
        return resp

    def _get_all(self, path: str, params: dict, max_pages: int = 50) -> list[dict]:
        items, page = [], "1"
        while page and max_pages:
            resp = self._get(path, {**params, "per_page": 100, "page": page})
            items.extend(resp.json())
            page = resp.headers.get("X-Next-Page", "")
            max_pages -= 1
        return items

    def user(self) -> dict:
        return self._get("/user").json()

    def user_by_username(self, username: str) -> dict | None:
        found = self._get("/users", {"username": username}).json()
        return found[0] if found else None

    def push_events(self, user_id, after: date, before: date) -> list[dict]:
        """Pushes by a user; `after`/`before` are exclusive dates."""
        return self._get_all(f"/users/{user_id}/events",
                             {"action": "pushed", "after": after.isoformat(),
                              "before": before.isoformat()}, max_pages=5)

    def commit(self, project_id, sha: str) -> dict:
        return self._get(f"/projects/{_pid(project_id)}/repository/commits/{sha}").json()

    def projects(self, since: datetime | None = None, max_pages: int = 50) -> list[dict]:
        params = {"membership": "true", "archived": "false", "simple": "true",
                  "order_by": "last_activity_at", "sort": "desc"}
        if since:
            params["last_activity_after"] = _iso(since)
        return self._get_all("/projects", params, max_pages=max_pages)

    def project(self, project_id) -> dict:
        return self._get(f"/projects/{_pid(project_id)}").json()

    def commits(self, project_id, since: datetime, until: datetime) -> list[dict]:
        return self._get_all(f"/projects/{_pid(project_id)}/repository/commits",
                             {"since": _iso(since), "until": _iso(until), "all": "true"})

    def commit_diff(self, project_id, sha: str) -> list[dict]:
        return self._get_all(f"/projects/{_pid(project_id)}/repository/commits/{sha}/diff", {})

    def merge_requests(self, project_id, since: datetime, until: datetime) -> list[dict]:
        return self._get_all(f"/projects/{_pid(project_id)}/merge_requests",
                             {"updated_after": _iso(since), "updated_before": _iso(until),
                              "scope": "all"})

    def issues(self, project_id, since: datetime, until: datetime) -> list[dict]:
        return self._get_all(f"/projects/{_pid(project_id)}/issues",
                             {"updated_after": _iso(since), "updated_before": _iso(until),
                              "scope": "all"})


def _pid(project_id) -> str:
    return quote(str(project_id), safe="")


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def project_summary(p: dict) -> dict:
    return {"id": str(p["id"]), "name": p["path_with_namespace"],
            "url": p["web_url"], "last_activity_at": p.get("last_activity_at")}


def _file_diffs(raw: list[dict]) -> list[FileDiff]:
    out = []
    for d in raw:
        status = ("added" if d.get("new_file") else "deleted" if d.get("deleted_file")
                  else "renamed" if d.get("renamed_file") else "modified")
        out.append(FileDiff(path=d.get("new_path") or d.get("old_path") or "?",
                            status=status, diff=d.get("diff") or ""))
    return out


def _looks_like_username(value: str) -> bool:
    return "@" not in value and " " not in value.strip()


def _identities(user: dict) -> set[str]:
    return {str(v).strip().lower() for v in (user.get("username"), user.get("name"), user.get("email"),
                                             user.get("public_email"), user.get("commit_email")) if v}


def resolve_authors(client: GitLabClient, authors: set[str], window: DayWindow) -> set[str]:
    """Add the commit identities (git name/email) behind each GitLab account in the filter.

    An entry names an account when it is a username, or the email/name of the connected
    account itself. Commits only carry the name/email from the author's local git config,
    which often differs from the account, so the user's pushes around the day reveal them.
    """
    out = set(authors)
    try:
        me = client.user()
    except requests.RequestException:
        me = {}
    mine = _identities(me)
    users: dict[int, dict] = {}
    for entry in authors:
        try:
            if entry in mine:
                user = me
            elif _looks_like_username(entry):
                user = client.user_by_username(entry)
            else:
                continue
        except requests.RequestException as exc:
            log.warning("Could not look up GitLab user %s: %s", entry, exc)
            continue
        if user and user.get("id") is not None:
            users[user["id"]] = user
    # A few days around the report day: enough to learn the identities, cheap to scan.
    after = window.start.date() - timedelta(days=3)
    before = window.end.date() + timedelta(days=1)
    for user in users.values():
        out |= _identities(user)
        try:
            seen: set[str] = set()
            for event in client.push_events(user["id"], after, before):
                sha = (event.get("push_data") or {}).get("commit_to")
                if not sha or sha in seen or not event.get("project_id"):
                    continue
                if len(seen) >= MAX_IDENTITY_LOOKUPS:
                    break
                seen.add(sha)
                commit = client.commit(event["project_id"], sha)
                out |= {str(v).strip().lower() for v in (commit.get("author_name"),
                                                         commit.get("author_email")) if v}
        except requests.RequestException as exc:
            log.warning("Could not resolve GitLab user %s: %s", user.get("username"), exc)
    log.info("GitLab author filter %s matches %s", sorted(authors), sorted(out))
    return out


def collect(client: GitLabClient, source: CodeSource, window: DayWindow,
            want_diffs: bool, max_diff_chars: int, progress=None,
            skipped: Counter | None = None) -> list[dict]:
    """GitLab activity inside the window, one dict per project that had any.

    progress(done, total, name) is called before each project is scanned.
    skipped, when given, counts commits dropped by the author filter per "Name <email>".
    """
    authors = resolve_authors(client, {a.strip().lower() for a in source.authors if a.strip()},
                              window)
    excluded = {str(p).lower() for p in source.exclude}

    if source.projects == "all":
        # last_activity_at is only refreshed about once an hour, hence the margin.
        targets = client.projects(since=window.start - timedelta(hours=1))
    else:
        targets = []
        for pid in source.projects:
            try:
                targets.append(client.project(pid))
            except requests.RequestException as exc:
                log.error("GitLab project %s not reachable: %s", pid, exc)
    targets = [p for p in targets if str(p["id"]) not in excluded
               and p["path_with_namespace"].lower() not in excluded]
    log.info("GitLab %s: scanning %d project(s)", client.base_url, len(targets))

    projects = []
    for index, proj in enumerate(targets):
        pid = proj["id"]
        name = proj.get("name_with_namespace") or proj["path_with_namespace"]
        if progress:
            progress(index, len(targets), name)
        try:
            commits = []
            for c in client.commits(pid, window.start, window.end):
                if not source.include_merge_commits and len(c.get("parent_ids") or []) > 1:
                    continue
                if not author_match(authors, c.get("author_name"), c.get("author_email")):
                    if skipped is not None:
                        skipped[f"{c.get('author_name')} <{c.get('author_email')}>"] += 1
                    continue
                commits.append({"id": c["id"], "short_id": c["short_id"], "title": c["title"],
                                "author": c["author_name"], "url": c.get("web_url"),
                                "created_at": c["created_at"]})

            mrs = []
            for mr in client.merge_requests(pid, window.start, window.end):
                author = mr["author"]["username"]
                if not author_match(authors, author, mr["author"].get("name")):
                    continue
                if in_window(mr.get("merged_at"), window):
                    action = "merged"
                elif in_window(mr.get("created_at"), window):
                    action = "opened"
                elif in_window(mr.get("closed_at"), window):
                    action = "closed"
                else:
                    action = "updated"
                mrs.append({"iid": mr["iid"], "ref": f"!{mr['iid']}", "title": mr["title"],
                            "author": author, "action": action, "state": mr["state"],
                            "url": mr["web_url"], "target_branch": mr["target_branch"]})

            issues = []
            for issue in client.issues(pid, window.start, window.end):
                author = issue["author"]["username"]
                assignees = [a["username"] for a in issue.get("assignees") or []]
                if not author_match(authors, author, *assignees):
                    continue
                if in_window(issue.get("closed_at"), window):
                    action = "closed"
                elif in_window(issue.get("created_at"), window):
                    action = "opened"
                else:
                    action = "updated"
                issues.append({"iid": issue["iid"], "ref": f"#{issue['iid']}",
                               "title": issue["title"], "author": author,
                               "assignees": assignees, "action": action,
                               "labels": issue.get("labels") or [], "url": issue["web_url"]})

            if not (commits or mrs or issues):
                continue
            project = {"source": "gitlab", "name": name, "url": proj["web_url"],
                       "commits": commits, "merge_requests": mrs, "issues": issues}
            if want_diffs and commits:
                per_commit = []
                for c in reversed(commits):
                    try:
                        per_commit.append((c["short_id"],
                                           _file_diffs(client.commit_diff(pid, c["id"]))))
                    except requests.RequestException as exc:
                        log.warning("Diff for %s failed: %s", c["short_id"], exc)
                project["diff_text"], project["files"] = combine(per_commit, max_diff_chars)
            projects.append(project)
        except requests.RequestException as exc:
            log.error("GitLab project %s failed: %s", pid, exc)
            projects.append({"source": "gitlab", "name": name, "url": proj["web_url"],
                             "error": str(exc), "commits": [], "merge_requests": [],
                             "issues": []})
    return projects
