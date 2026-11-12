import logging
import re
import time
from collections import Counter
from datetime import timedelta, timezone

import requests

from ..models import CodeSource
from ..window import DayWindow
from . import author_match, in_window, parse_ts
from .diffutil import FileDiff, combine

log = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"
_NEXT = re.compile(r'<([^>]+)>;\s*rel="next"')
MAX_BRANCHES = 30


class GitHubClient:
    def __init__(self, token: str, api: str = GITHUB_API, timeout: int = 30):
        self.api = api.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "RabShoot",
        })
        self.timeout = timeout

    def _request(self, url: str, params: dict | None = None) -> requests.Response:
        for _ in range(3):
            resp = self.session.get(url, params=params, timeout=self.timeout)
            if resp.status_code in (403, 429) and resp.headers.get("X-RateLimit-Remaining") == "0":
                reset = int(resp.headers.get("X-RateLimit-Reset", "0")) - int(time.time())
                if 0 < reset <= 60:
                    time.sleep(reset + 1)
                    continue
            resp.raise_for_status()
            return resp
        resp.raise_for_status()
        return resp

    def _get(self, path: str, params: dict | None = None):
        return self._request(f"{self.api}{path}", params).json()

    def _get_all(self, path: str, params: dict | None = None, max_pages: int = 20,
                 stop=None) -> list[dict]:
        items, url, query = [], f"{self.api}{path}", {**(params or {}), "per_page": 100}
        while url and max_pages:
            resp = self._request(url, query)
            page = resp.json()
            items.extend(page)
            if stop and page and stop(page[-1]):
                break
            match = _NEXT.search(resp.headers.get("Link", ""))
            url, query = (match.group(1), None) if match else (None, None)
            max_pages -= 1
        return items

    def user(self) -> dict:
        return self._get("/user")

    def repos(self, max_pages: int = 10) -> list[dict]:
        return self._get_all("/user/repos", {
            "affiliation": "owner,collaborator,organization_member",
            "sort": "pushed", "direction": "desc",
        }, max_pages=max_pages)

    def repo(self, full_name: str) -> dict:
        return self._get(f"/repos/{full_name}")

    def branches(self, full_name: str) -> list[dict]:
        return self._get_all(f"/repos/{full_name}/branches", max_pages=3)

    def commits(self, full_name: str, since, until, sha: str | None = None) -> list[dict]:
        params = {"since": _iso(since), "until": _iso(until)}
        if sha:
            params["sha"] = sha
        return self._get_all(f"/repos/{full_name}/commits", params, max_pages=5)

    def commit(self, full_name: str, sha: str) -> dict:
        return self._get(f"/repos/{full_name}/commits/{sha}")

    def pulls(self, full_name: str, since) -> list[dict]:
        pulls = self._get_all(
            f"/repos/{full_name}/pulls",
            {"state": "all", "sort": "updated", "direction": "desc"},
            max_pages=5,
            stop=lambda last: parse_ts(last.get("updated_at")) < since,
        )
        return [p for p in pulls if parse_ts(p.get("updated_at")) >= since]

    def issues(self, full_name: str, since) -> list[dict]:
        items = self._get_all(f"/repos/{full_name}/issues",
                              {"state": "all", "since": _iso(since)}, max_pages=5)
        return [i for i in items if "pull_request" not in i]


def _iso(dt) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def repo_summary(r: dict) -> dict:
    return {"id": r["full_name"], "name": r["full_name"], "url": r["html_url"],
            "last_activity_at": r.get("pushed_at"), "private": r.get("private", False)}


def _file_diffs(files: list[dict]) -> list[FileDiff]:
    status_map = {"added": "added", "removed": "deleted", "renamed": "renamed"}
    return [FileDiff(path=f.get("filename", "?"),
                     status=status_map.get(f.get("status"), "modified"),
                     diff=f.get("patch") or "") for f in files]


def _day_commits(client: GitHubClient, full_name: str, window: DayWindow) -> list[dict]:
    """Commits on every branch (capped), de-duplicated by SHA."""
    seen: dict[str, dict] = {}
    try:
        branches = [b["name"] for b in client.branches(full_name)][:MAX_BRANCHES]
    except requests.RequestException:
        branches = []
    for branch in branches or [None]:
        try:
            for c in client.commits(full_name, window.start, window.end, sha=branch):
                seen.setdefault(c["sha"], c)
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 409:
                return []  # empty repository
            raise
    return sorted(seen.values(), key=lambda c: c["commit"]["committer"]["date"], reverse=True)


def collect(client: GitHubClient, source: CodeSource, window: DayWindow,
            want_diffs: bool, max_diff_chars: int, progress=None,
            skipped: Counter | None = None) -> list[dict]:
    """progress(done, total, name) is called before each repo is scanned.

    skipped, when given, counts commits dropped by the author filter per "Name <email>".
    """
    authors = {a.lower() for a in source.authors}
    excluded = {str(p).lower() for p in source.exclude}

    if source.projects == "all":
        since = window.start - timedelta(hours=1)
        targets = [r for r in client.repos()
                   if (parse_ts(r.get("pushed_at")) or since) >= since
                   or (parse_ts(r.get("updated_at")) or since) >= since]
    else:
        targets = []
        for name in source.projects:
            try:
                targets.append(client.repo(name))
            except requests.RequestException as exc:
                log.error("GitHub repo %s not reachable: %s", name, exc)
    targets = [r for r in targets if r["full_name"].lower() not in excluded]
    log.info("GitHub: scanning %d repo(s)", len(targets))

    projects = []
    for index, repo in enumerate(targets):
        full = repo["full_name"]
        if progress:
            progress(index, len(targets), full)
        try:
            commits = []
            for c in _day_commits(client, full, window):
                if len(c.get("parents") or []) > 1 and not source.include_merge_commits:
                    continue
                info = c["commit"]
                login = (c.get("author") or {}).get("login")
                if not author_match(authors, login, info["author"].get("name"),
                                    info["author"].get("email")):
                    if skipped is not None:
                        skipped[f"{info['author'].get('name') or login} "
                                f"<{info['author'].get('email')}>"] += 1
                    continue
                commits.append({"id": c["sha"], "short_id": c["sha"][:8],
                                "title": info["message"].splitlines()[0] if info["message"] else "",
                                "author": info["author"].get("name") or login or "unknown",
                                "url": c.get("html_url"), "created_at": info["author"].get("date")})

            mrs = []
            for pr in client.pulls(full, window.start):
                if parse_ts(pr["updated_at"]) >= window.end:
                    if not (in_window(pr.get("merged_at"), window)
                            or in_window(pr.get("created_at"), window)):
                        continue
                author = (pr.get("user") or {}).get("login", "")
                if not author_match(authors, author):
                    continue
                if in_window(pr.get("merged_at"), window):
                    action = "merged"
                elif in_window(pr.get("created_at"), window):
                    action = "opened"
                elif in_window(pr.get("closed_at"), window):
                    action = "closed"
                else:
                    action = "updated"
                mrs.append({"iid": pr["number"], "ref": f"#{pr['number']}", "title": pr["title"],
                            "author": author, "action": action,
                            "state": "merged" if pr.get("merged_at") else pr["state"],
                            "url": pr["html_url"], "target_branch": pr["base"]["ref"]})

            issues = []
            for issue in client.issues(full, window.start):
                if parse_ts(issue["updated_at"]) >= window.end:
                    continue
                author = (issue.get("user") or {}).get("login", "")
                assignees = [a["login"] for a in issue.get("assignees") or []]
                if not author_match(authors, author, *assignees):
                    continue
                if in_window(issue.get("closed_at"), window):
                    action = "closed"
                elif in_window(issue.get("created_at"), window):
                    action = "opened"
                else:
                    action = "updated"
                issues.append({"iid": issue["number"], "ref": f"#{issue['number']}",
                               "title": issue["title"], "author": author,
                               "assignees": assignees, "action": action,
                               "labels": [lb["name"] for lb in issue.get("labels") or []],
                               "url": issue["html_url"]})

            if not (commits or mrs or issues):
                continue
            project = {"source": "github", "name": full, "url": repo["html_url"],
                       "commits": commits, "merge_requests": mrs, "issues": issues}
            if want_diffs and commits:
                per_commit = []
                for c in reversed(commits[:40]):
                    try:
                        detail = client.commit(full, c["id"])
                        per_commit.append((c["short_id"], _file_diffs(detail.get("files") or [])))
                    except requests.RequestException as exc:
                        log.warning("Diff for %s failed: %s", c["short_id"], exc)
                project["diff_text"], project["files"] = combine(per_commit, max_diff_chars)
            projects.append(project)
        except requests.RequestException as exc:
            log.error("GitHub repo %s failed: %s", full, exc)
            projects.append({"source": "github", "name": full, "url": repo["html_url"],
                             "error": str(exc), "commits": [], "merge_requests": [],
                             "issues": []})
    return projects
