"""JSON config files: connections.json, profiles/<id>.json, settings.json."""

import json
import os
import threading
from pathlib import Path
from typing import Callable

from . import paths
from .models import Connection, Profile, Settings, now_iso
from .secrets_store import store as secret_store

_lock = threading.RLock()
_listeners: list[Callable[[], None]] = []


def on_change(callback: Callable[[], None]) -> None:
    _listeners.append(callback)


def _notify() -> None:
    for cb in list(_listeners):
        cb()


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def _read_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8") or "null") or default


# --- settings ----------------------------------------------------------------

def _settings_path() -> Path:
    return paths.config_dir() / "settings.json"


def get_settings() -> Settings:
    return Settings(**_read_json(_settings_path(), {}))


def save_settings(settings: Settings) -> Settings:
    with _lock:
        _write_json(_settings_path(), settings.model_dump())
    return settings


# --- connections -------------------------------------------------------------

def _connections_path() -> Path:
    return paths.config_dir() / "connections.json"


def list_connections() -> list[Connection]:
    return [Connection(**c) for c in _read_json(_connections_path(), [])]


def connections_by_id() -> dict[str, Connection]:
    return {c.id: c for c in list_connections()}


def get_connection(conn_id: str) -> Connection:
    conn = connections_by_id().get(conn_id)
    if not conn:
        raise KeyError(f"Connection {conn_id} not found")
    return conn


def save_connection(conn: Connection, secret: dict | None = None) -> Connection:
    with _lock:
        items = [c for c in list_connections() if c.id != conn.id]
        items.append(conn)
        _write_json(_connections_path(), [c.model_dump() for c in items])
        if secret is not None:
            secret_store().set(conn.id, secret)
    _notify()
    return conn


def _identity(conn: Connection) -> tuple | None:
    """Who a tested account belongs to; AI keys have none, several keys can be on purpose."""
    m = conn.meta
    if conn.type in ("gitlab", "github") and m.get("username"):
        return conn.type, (m.get("url") or "").rstrip("/").lower(), m["username"].lower()
    if conn.type == "slack" and m.get("user_id"):
        return conn.type, m.get("team_id"), m["user_id"]
    if conn.type == "email" and m.get("address"):
        return conn.type, m["address"].lower()
    return None


def merge_duplicate(conn: Connection) -> Connection:
    """Adding an account that is already saved refreshes the saved one instead of copying it.

    Reports keep pointing at the saved id, so a re-added account fixes them too.
    """
    key = _identity(conn)
    existing = next((c for c in list_connections()
                     if c.id != conn.id and key and _identity(c) == key), None)
    if not existing:
        return conn
    existing.meta.update(conn.meta)
    existing.status, existing.status_message = conn.status, conn.status_message
    save_connection(existing, secret=get_secret(conn.id))
    delete_connection(conn.id)
    return existing


def _repoint(profile: Profile, gone: set[str], keep: str) -> bool:
    before = profile.model_dump()
    for field_name in ("sender_connection_id", "ai_connection_id"):
        if getattr(profile, field_name) in gone:
            setattr(profile, field_name, keep)
    if profile.slack.connection_id in gone:
        profile.slack.connection_id = keep
    sources, seen = [], set()
    for source in profile.code_sources:
        if source.connection_id in gone:
            source.connection_id = keep
        if source.connection_id not in seen:
            seen.add(source.connection_id)
            sources.append(source)
    profile.code_sources = sources
    return profile.model_dump() != before


def uses(profile: Profile, conn_id: str) -> bool:
    return conn_id in {profile.sender_connection_id, profile.ai_connection_id,
                       profile.slack.connection_id, *(s.connection_id for s in profile.code_sources)}


def detach_connection(conn_id: str) -> list[str]:
    """Take an account out of every report that uses it; returns those reports' names."""
    names = []
    for profile in list_profiles():
        if not uses(profile, conn_id):
            continue
        if profile.sender_connection_id == conn_id:
            profile.sender_connection_id = None
        if profile.ai_connection_id == conn_id:
            profile.ai_connection_id = None
        if profile.slack.connection_id == conn_id:
            profile.slack.connection_id, profile.slack.conversations = None, []
        profile.code_sources = [s for s in profile.code_sources if s.connection_id != conn_id]
        save_profile(profile)
        names.append(profile.name)
    return names


def merge_saved_duplicates() -> int:
    """Fold copies of one account into the oldest copy, keeping the newest sign-in.

    Every copy passed its test when it was added, so the newest one holds the token
    most likely to still work. Reports are repointed; returns how many copies were removed.
    """
    groups: dict[tuple, list[Connection]] = {}
    for conn in list_connections():
        key = _identity(conn)
        if key:
            groups.setdefault(key, []).append(conn)
    removed = 0
    for copies in groups.values():
        if len(copies) < 2:
            continue
        copies.sort(key=lambda c: c.created_at)
        keep, newest = copies[0], copies[-1]
        secret = get_secret(newest.id)
        if not secret:
            continue
        keep.meta.update(newest.meta)
        keep.status, keep.status_message = newest.status, newest.status_message
        save_connection(keep, secret=secret)
        gone = {c.id for c in copies[1:]}
        for profile in list_profiles():
            if _repoint(profile, gone, keep.id):
                save_profile(profile)
        for conn_id in gone:
            delete_connection(conn_id)
        removed += len(gone)
    return removed


def delete_connection(conn_id: str) -> None:
    with _lock:
        items = [c for c in list_connections() if c.id != conn_id]
        _write_json(_connections_path(), [c.model_dump() for c in items])
        secret_store().delete(conn_id)
    _notify()


def get_secret(conn_id: str) -> dict:
    return secret_store().get(conn_id)


def set_secret(conn_id: str, secret: dict) -> None:
    secret_store().set(conn_id, secret)


# --- profiles ----------------------------------------------------------------

def _profiles_dir() -> Path:
    path = paths.config_dir() / "profiles"
    path.mkdir(parents=True, exist_ok=True)
    return path


def list_profiles() -> list[Profile]:
    profiles = [Profile(**_read_json(p, {})) for p in sorted(_profiles_dir().glob("*.json"))]
    return sorted(profiles, key=lambda p: p.created_at)


def get_profile(profile_id: str) -> Profile:
    path = _profiles_dir() / f"{profile_id}.json"
    if not path.exists():
        raise KeyError(f"Profile {profile_id} not found")
    return Profile(**_read_json(path, {}))


def save_profile(profile: Profile) -> Profile:
    profile.updated_at = now_iso()
    with _lock:
        _write_json(_profiles_dir() / f"{profile.id}.json", profile.model_dump())
    _notify()
    return profile


def delete_profile(profile_id: str) -> None:
    with _lock:
        (_profiles_dir() / f"{profile_id}.json").unlink(missing_ok=True)
    _notify()
