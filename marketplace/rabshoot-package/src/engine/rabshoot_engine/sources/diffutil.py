"""Turn per-commit file diffs into one redacted, size-limited text for the AI."""

import re
from dataclasses import dataclass

# Never sent to the AI: secrets, lockfiles, generated/binary assets.
SKIP_FILE = re.compile(
    r"(^|/)(\.env(\..*)?|.*\.(pem|key|p12|pfx|jks|keystore|crt|lock|min\.js|min\.css|map|svg|png"
    r"|jpe?g|gif|webp|ico|pdf|zip|gz|woff2?|ttf|otf|mp4|mp3)|package-lock\.json|yarn\.lock"
    r"|pnpm-lock\.yaml|composer\.lock|pubspec\.lock|Podfile\.lock|google-services\.json"
    r"|GoogleService-Info\.plist|credentials\.json|service-account.*\.json)$",
    re.IGNORECASE,
)
SKIP_DIR = re.compile(r"(^|/)(vendor|node_modules|dist|build|\.dart_tool|Pods|storage"
                      r"|public/build|\.idea|\.vscode)/")
SECRET = re.compile(
    r"(?i)((?:api[_-]?key|secret|token|password|passwd|pwd|private[_-]?key|access[_-]?key"
    r"|client[_-]?secret|auth)[\"']?\s*[:=]>?\s*)([\"']?)[^\s\"',;]+"
)
MAX_FILE_CHARS = 4000


@dataclass
class FileDiff:
    path: str
    status: str  # added | deleted | renamed | modified
    diff: str


def mask_secrets(text: str) -> str:
    return SECRET.sub(r"\1\2***", text)


def combine(commits: list[tuple[str, list[FileDiff]]], max_chars: int) -> tuple[str, list[dict]]:
    """commits: [(short_sha, [FileDiff…])] oldest first → (diff_text, file stats)."""
    parts, files, used = [], {}, 0
    for short_id, diffs in commits:
        for d in diffs:
            body = d.diff or ""
            lines = body.splitlines()
            added = sum(1 for ln in lines if ln.startswith("+") and not ln.startswith("+++"))
            removed = sum(1 for ln in lines if ln.startswith("-") and not ln.startswith("---"))
            entry = files.setdefault(d.path, {"path": d.path, "status": d.status,
                                              "added": 0, "removed": 0})
            entry["added"] += added
            entry["removed"] += removed

            if SKIP_FILE.search(d.path) or SKIP_DIR.search(d.path):
                continue
            header = f"--- {d.path} ({d.status}, +{added} -{removed}) in {short_id}"
            body = mask_secrets(body) if body else "(diff too large, omitted)"
            if len(body) > MAX_FILE_CHARS:
                body = body[:MAX_FILE_CHARS] + "\n... (truncated)"
            if used + len(body) > max_chars:
                parts.append(f"{header}\n(omitted: size limit reached)")
                continue
            parts.append(f"{header}\n{body}")
            used += len(body)
    return "\n\n".join(parts), list(files.values())
