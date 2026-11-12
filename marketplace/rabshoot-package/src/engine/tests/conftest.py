import pytest

from rabshoot_engine import secrets_store


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("RABSHOOT_HOME", str(tmp_path))
    monkeypatch.setenv("RABSHOOT_SECRETS", "file")
    secrets_store.reset(force_file=True)
    yield tmp_path
