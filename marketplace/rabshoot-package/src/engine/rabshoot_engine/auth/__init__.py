import json
import os

from ..paths import resource_path

# Public OAuth client IDs of the RabShoot GitHub App and GitLab application. They are not
# secrets (desktop apps cannot keep secrets); baked in at build time (assets/oauth.json,
# written by scripts/build_engine.py) and overridable via environment.


def _baked() -> dict:
    path = resource_path("assets", "oauth.json")
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except (OSError, ValueError):
        return {}


_BAKED = _baked()


def _setting(name: str, default: str = "") -> str:
    return os.environ.get(name) or _BAKED.get(name) or default


GITHUB_CLIENT_ID = _setting("RABSHOOT_GITHUB_CLIENT_ID")
GITHUB_APP_SLUG = _setting("RABSHOOT_GITHUB_APP_SLUG")
GITLAB_CLIENT_ID = _setting("RABSHOOT_GITLAB_CLIENT_ID")
GITLAB_REDIRECT_PORT = int(_setting("RABSHOOT_GITLAB_REDIRECT_PORT", "47113"))


def oauth_status() -> dict:
    return {
        "github_device": bool(GITHUB_CLIENT_ID),
        "github_app_install_url": (f"https://github.com/apps/{GITHUB_APP_SLUG}/installations/new"
                                   if GITHUB_APP_SLUG else ""),
        "gitlab_oauth": bool(GITLAB_CLIENT_ID),
    }
