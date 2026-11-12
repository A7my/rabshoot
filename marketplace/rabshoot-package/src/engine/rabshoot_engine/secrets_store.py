"""Secrets live in the OS keychain; a private file is used only when no keychain exists."""

import json
import logging
import os
import threading
from pathlib import Path

from . import paths

log = logging.getLogger(__name__)

SERVICE = "RabShoot"
_lock = threading.Lock()


class SecretStore:
    def __init__(self, force_file: bool = False):
        self._keyring = None if force_file else _usable_keyring()
        self._file = paths.config_dir() / "secrets.json"

    @property
    def backend(self) -> str:
        return "keychain" if self._keyring else "file"

    @property
    def secure(self) -> bool:
        return self._keyring is not None

    def get(self, key: str) -> dict:
        if self._keyring:
            raw = self._keyring.get_password(SERVICE, key)
            return json.loads(raw) if raw else {}
        return self._read_file().get(key, {})

    def set(self, key: str, value: dict) -> None:
        if self._keyring:
            self._keyring.set_password(SERVICE, key, json.dumps(value))
            return
        with _lock:
            data = self._read_file()
            data[key] = value
            self._write_file(data)

    def delete(self, key: str) -> None:
        if self._keyring:
            try:
                self._keyring.delete_password(SERVICE, key)
            except Exception:
                pass
            return
        with _lock:
            data = self._read_file()
            if data.pop(key, None) is not None:
                self._write_file(data)

    def _read_file(self) -> dict:
        if not self._file.exists():
            return {}
        return json.loads(self._file.read_text(encoding="utf-8") or "{}")

    def _write_file(self, data: dict) -> None:
        tmp = self._file.with_suffix(".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.replace(tmp, self._file)
        try:
            os.chmod(self._file, 0o600)
        except OSError:
            pass


def _usable_keyring():
    if os.environ.get("RABSHOOT_SECRETS") == "file":
        return None
    try:
        import keyring
        from keyring.backends import fail, null

        backend = keyring.get_keyring()
        if isinstance(backend, (fail.Keyring, null.Keyring)):
            raise RuntimeError(type(backend).__name__)
        probe = "__rabshoot_probe__"
        backend.set_password(SERVICE, probe, "1")
        ok = backend.get_password(SERVICE, probe) == "1"
        backend.delete_password(SERVICE, probe)
        if not ok:
            raise RuntimeError("probe mismatch")
        return backend
    except Exception as exc:
        log.warning("OS keychain unavailable (%s); storing secrets in a private file", exc)
        return None


_store: SecretStore | None = None


def store() -> SecretStore:
    global _store
    if _store is None:
        _store = SecretStore()
    return _store


def reset(force_file: bool = False) -> SecretStore:
    global _store
    _store = SecretStore(force_file=force_file)
    return _store


def secrets_file() -> Path:
    return paths.config_dir() / "secrets.json"
