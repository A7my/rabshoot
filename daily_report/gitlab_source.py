import logging
import os
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import requests

from .config import DayWindow

log = logging.getLogger(__name__)


class GitLabClient:
    def __init__(self, base_url: str, token: str, timeout: int = 30):
        self.api = base_url.rstrip("/") + "/api/v4"
        self.session = requests.Session()
        self.session.headers["PRIVATE-TOKEN"] = token
        self.timeout = timeout

    def _get_all(self, path: str, params: dict) -> list[dict]:
        items, page = [], "1"
        while page:
            resp = self.session.get(
                f"{self.api}{path}",
                params={**params, "per_page": 100, "page": page},
                timeout=self.timeout,
            )
            resp.raise_for_status()
            items.extend(resp.json())
            page = resp.headers.get("X-Next-Page", "")
        return items

    def active_projects(self, since: datetime) -> list[dict]:
        return self._get_all(
            "/projects",
            {
                "membership": "true",
                "archived": "false",
                "simple": "true",
                "last_activity_after": _iso(since),
                "order_by": "last_activity_at",
            },
        )

    def project(self, project_id) -> dict:
        resp = self.session.get(
            f"{self.api}/projects/{_pid(project_id)}", timeout=self.timeout
        )
        resp.raise_for_status()
        return resp.json()

    def commits(self, project_id, since: datetime, until: datetime) -> list[dict]:
        return self._get_all(
            f"/projects/{_pid(project_id)}/repository/commits",
            {"since": _iso(since), "until": _iso(until), "all": "true"},
        )

    def commit_diff(self, project_id, sha: str) -> list[dict]:
        return self._get_all(f"/projects/{_pid(project_id)}/repository/commits/{sha}/diff", {})

    def merge_requests(self, project_id, since: datetime, until: datetime) -> list[dict]:
        return self._get_all(
            f"/projects/{_pid(project_id)}/merge_requests",
            {"updated_after": _iso(since), "updated_before": _iso(until), "scope": "all"},
        )

    def issues(self, project_id, since: datetime, until: datetime) -> list[dict]:
        return self._get_all(
            f"/projects/{_pid(project_id)}/issues",
            {"updated_after": _iso(since), "updated_before": _iso(until), "scope": "all"},
        )


def _pid(project_id) -> str:
    return quote(str(project_id), safe="")


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _in_window(value: str | None, window: DayWindow) -> bool:
    if not value:
        return False
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return window.start <= dt < window.end


def _author_match(authors: set[str], *candidates: str | None) -> bool:
    return not authors or any(c and c.lower() in authors for c in candidates)


# Never sent to the AI: secrets, lockfiles, generated/binary assets.
_SKIP_FILE = re.compile(
    r"(^|/)(\.env(\..*)?|.*\.(pem|key|p12|pfx|jks|keystore|crt|lock|min\.js|min\.css|map|svg|png"
    r"|jpe?g|gif|webp|ico|pdf|zip|gz|woff2?|ttf|otf|mp4|mp3)|package-lock\.json|yarn\.lock"
    r"|pnpm-lock\.yaml|composer\.lock|pubspec\.lock|Podfile\.lock|google-services\.json"
    r"|GoogleService-Info\.plist|credentials\.json|service-account.*\.json)$",
    re.IGNORECASE,
)
_SKIP_DIR = re.compile(r"(^|/)(vendor|node_modules|dist|build|\.dart_tool|Pods|storage"
                       r"|public/build|\.idea|\.vscode)/")
_SECRET = re.compile(
    r"(?i)((?:api[_-]?key|secret|token|password|passwd|pwd|private[_-]?key|access[_-]?key"
    r"|client[_-]?secret|auth)[\"']?\s*[:=]>?\s*)([\"']?)[^\s\"',;]+"
)
_MAX_FILE_CHARS = 4000


def build_diff(client: GitLabClient, pid, commits: list[dict],
               max_chars: int) -> tuple[str, list[dict]]:
    """Combine the day's commit diffs into one redacted, size-limited text."""
    parts, files, used = [], {}, 0
    for commit in reversed(commits):
        try:
            diffs = client.commit_diff(pid, commit["id"])
        except requests.RequestException as exc:
            log.warning("Diff for %s failed: %s", commit["short_id"], exc)
            continue
        for d in diffs:
            path = d.get("new_path") or d.get("old_path") or "?"
            body = d.get("diff") or ""
            added = sum(1 for ln in body.splitlines() if ln.startswith("+"))
            removed = sum(1 for ln in body.splitlines() if ln.startswith("-"))
            status = ("added" if d.get("new_file") else "deleted" if d.get("deleted_file")
                      else "renamed" if d.get("renamed_file") else "modified")
            entry = files.setdefault(path, {"path": path, "status": status,
                                            "added": 0, "removed": 0})
            entry["added"] += added
            entry["removed"] += removed

            if _SKIP_FILE.search(path) or _SKIP_DIR.search(path):
                continue
            header = f"--- {path} ({status}, +{added} -{removed}) in {commit['short_id']}"
            if not body:
                body = "(diff too large, omitted)"
            body = _SECRET.sub(r"\1\2***", body)
            if len(body) > _MAX_FILE_CHARS:
                body = body[:_MAX_FILE_CHARS] + "\n... (truncated)"
            if used + len(body) > max_chars:
                parts.append(f"{header}\n(omitted: size limit reached)")
                continue
            parts.append(f"{header}\n{body}")
            used += len(body)
    return "\n\n".join(parts), list(files.values())


def collect(cfg: dict, window: DayWindow) -> dict:
    """Return GitLab activity for the window, grouped by project."""
    gl_cfg = cfg.get("gitlab") or {}
    if not gl_cfg.get("enabled"):
        return {"projects": []}

    client = GitLabClient(gl_cfg["url"], os.environ["GITLAB_TOKEN"])
    authors = {a.lower() for a in gl_cfg.get("authors") or []}
    include_merges = gl_cfg.get("include_merge_commits", False)
    excluded = {str(p).lower() for p in gl_cfg.get("exclude_projects") or []}
    ai_cfg = cfg.get("ai") or {}
    want_diffs = bool(ai_cfg.get("enabled"))
    max_diff_chars = int(ai_cfg.get("max_diff_chars_per_project", 20000))
    projects = []

    selection = gl_cfg.get("projects", "all")
    if selection == "all":
        # last_activity_at is only refreshed about once an hour, hence the margin.
        targets = client.active_projects(window.start - timedelta(hours=1))
    else:
        targets = [client.project(pid) for pid in selection]
    targets = [
        p for p in targets
        if str(p["id"]) not in excluded and p["path_with_namespace"].lower() not in excluded
    ]
    log.info("GitLab: scanning %d project(s)", len(targets))

    for proj in targets:
        pid = proj["id"]
        try:
            commits = [
                {
                    "id": c["id"],
                    "short_id": c["short_id"],
                    "title": c["title"],
                    "author": c["author_name"],
                    "url": c.get("web_url"),
                    "created_at": c["created_at"],
                }
                for c in client.commits(pid, window.start, window.end)
                if (include_merges or len(c.get("parent_ids") or []) <= 1)
                and _author_match(authors, c.get("author_name"), c.get("author_email"))
            ]

            mrs = []
            for mr in client.merge_requests(pid, window.start, window.end):
                author = mr["author"]["username"]
                if not _author_match(authors, author, mr["author"].get("name")):
                    continue
                if _in_window(mr.get("merged_at"), window):
                    action = "merged"
                elif _in_window(mr.get("created_at"), window):
                    action = "opened"
                elif _in_window(mr.get("closed_at"), window):
                    action = "closed"
                else:
                    action = "updated"
                mrs.append(
                    {
                        "iid": mr["iid"],
                        "title": mr["title"],
                        "author": author,
                        "action": action,
                        "state": mr["state"],
                        "url": mr["web_url"],
                        "target_branch": mr["target_branch"],
                    }
                )

            issues = []
            for issue in client.issues(pid, window.start, window.end):
                author = issue["author"]["username"]
                assignees = [a["username"] for a in issue.get("assignees") or []]
                if not _author_match(authors, author, *assignees):
                    continue
                if _in_window(issue.get("closed_at"), window):
                    action = "closed"
                elif _in_window(issue.get("created_at"), window):
                    action = "opened"
                else:
                    action = "updated"
                issues.append(
                    {
                        "iid": issue["iid"],
                        "title": issue["title"],
                        "author": author,
                        "assignees": assignees,
                        "action": action,
                        "labels": issue.get("labels") or [],
                        "url": issue["web_url"],
                    }
                )

            if commits or mrs or issues:
                project = {
                    "name": proj["name_with_namespace"],
                    "url": proj["web_url"],
                    "commits": commits,
                    "merge_requests": mrs,
                    "issues": issues,
                }
                if want_diffs and commits:
                    project["diff_text"], project["files"] = build_diff(
                        client, pid, commits, max_diff_chars
                    )
                projects.append(project)
        except requests.RequestException as exc:
            log.error("GitLab project %s failed: %s", pid, exc)
            projects.append({"name": proj["name_with_namespace"], "url": proj["web_url"],
                             "error": str(exc),
                             "commits": [], "merge_requests": [], "issues": []})

    return {"projects": projects}
