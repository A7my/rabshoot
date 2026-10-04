"""Local HTTP API used by the desktop UI (127.0.0.1 only, bearer token)."""

import hmac
import logging
from datetime import date

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import __version__, connectors, history, paths, pipeline, storage
from .auth import github_device, gitlab_oauth, oauth_status, slack_oauth
from .mail import imap
from .mail.providers import PROVIDERS, guess_provider
from .models import Connection, ConnectionType, Profile, Settings, profile_problems
from .scheduler import Scheduler
from .secrets_store import store as secret_store
from .sources import slack as slack_source
from .window import DayWindow

log = logging.getLogger(__name__)

_ORIGINS = r"^(tauri://localhost|https?://tauri\.localhost|http://(localhost|127\.0\.0\.1):\d+)$"


class ConnectionIn(BaseModel):
    type: ConnectionType
    label: str = ""
    meta: dict = {}
    secret: dict | None = None


class ConnectionUpdate(BaseModel):
    label: str | None = None
    meta: dict | None = None
    secret: dict | None = None


class TestSendIn(BaseModel):
    to: str | None = None
    day: date | None = None


class RunIn(BaseModel):
    day: date | None = None


def report_day(profile: Profile, day: date | None) -> date | None:
    """A chosen report day; it can be today or any earlier day, never the future."""
    if day and day > DayWindow.today(profile.schedule.timezone).day:
        raise HTTPException(400, "Pick today or an earlier day")
    return day


class GitLabOAuthIn(BaseModel):
    base_url: str = "https://gitlab.com"


class SlackOAuthIn(BaseModel):
    client_id: str


def _public(conn: Connection) -> dict:
    return conn.model_dump()


def create_app(token: str, scheduler: Scheduler | None = None) -> FastAPI:
    app = FastAPI(title="RabShoot engine", version=__version__, docs_url=None, redoc_url=None)
    app.add_middleware(CORSMiddleware, allow_origin_regex=_ORIGINS, allow_methods=["*"],
                       allow_headers=["*"])
    app.state.scheduler = scheduler

    def auth(request: Request) -> None:
        host = request.client.host if request.client else ""
        if host not in ("127.0.0.1", "::1", "localhost", "testclient"):
            raise HTTPException(403, "Local access only")
        header = request.headers.get("authorization", "")
        if not hmac.compare_digest(header, f"Bearer {token}"):
            raise HTTPException(401, "Invalid token")

    guarded = [Depends(auth)]

    def fail(exc: Exception, code: int = 400):
        raise HTTPException(code, connectors._friendly(exc))

    def get_conn(conn_id: str) -> Connection:
        try:
            return storage.get_connection(conn_id)
        except KeyError:
            raise HTTPException(404, "Connection not found")

    def get_prof(profile_id: str) -> Profile:
        try:
            return storage.get_profile(profile_id)
        except KeyError:
            raise HTTPException(404, "Profile not found")

    # --- system -------------------------------------------------------------

    @app.get("/health", dependencies=guarded)
    def health():
        store = secret_store()
        return {"ok": True, "version": __version__, "secrets_backend": store.backend,
                "secrets_secure": store.secure, "oauth": oauth_status(),
                "paths": {"config": str(paths.config_dir()), "data": str(paths.data_dir()),
                          "logs": str(paths.logs_dir())}}

    @app.get("/settings", dependencies=guarded)
    def get_settings():
        return storage.get_settings()

    @app.put("/settings", dependencies=guarded)
    def put_settings(settings: Settings):
        storage.save_settings(settings)
        if app.state.scheduler:
            app.state.scheduler.sync()
        return settings

    # --- connections ---------------------------------------------------------

    @app.get("/connections", dependencies=guarded)
    def list_connections():
        return [_public(c) for c in storage.list_connections()]

    @app.post("/connections", dependencies=guarded)
    def create_connection(body: ConnectionIn):
        conn = Connection(type=body.type, label=body.label, meta=body.meta)
        if conn.type == "email":
            conn.meta.setdefault("provider", guess_provider(conn.meta.get("address", "")))
        storage.save_connection(conn, secret=body.secret or {})
        result = connectors.test(conn)
        if not result["ok"]:
            storage.delete_connection(conn.id)
            raise HTTPException(400, result["message"])
        if not conn.label:
            conn.label = connectors.default_label(conn)
            storage.save_connection(conn)
        conn = storage.merge_duplicate(conn)
        return {**_public(conn), "test": result}

    @app.put("/connections/{conn_id}", dependencies=guarded)
    def update_connection(conn_id: str, body: ConnectionUpdate):
        conn = get_conn(conn_id)
        old_meta, old_secret = dict(conn.meta), storage.get_secret(conn_id)
        if body.label is not None:
            conn.label = body.label
        if body.meta is not None:
            conn.meta.update(body.meta)
        storage.save_connection(conn, secret=body.secret if body.secret else None)
        if body.secret or body.meta:
            result = connectors.test(conn)
            if not result["ok"]:
                conn.meta = old_meta
                storage.save_connection(conn, secret=old_secret)
                raise HTTPException(400, result["message"])
        return _public(storage.get_connection(conn_id))

    @app.delete("/connections/{conn_id}", dependencies=guarded)
    def delete_connection(conn_id: str, detach: bool = False):
        """`detach` also removes the account from the reports that use it."""
        get_conn(conn_id)
        used = [p.name for p in storage.list_profiles() if storage.uses(p, conn_id)]
        if used and not detach:
            raise HTTPException(409, ", ".join(used))
        storage.detach_connection(conn_id)
        storage.delete_connection(conn_id)
        return {"ok": True}

    @app.post("/connections/{conn_id}/test", dependencies=guarded)
    def test_connection(conn_id: str):
        return connectors.test(get_conn(conn_id))

    # --- OAuth ----------------------------------------------------------------

    @app.post("/auth/github/device/start", dependencies=guarded)
    def github_start():
        try:
            return github_device.start()
        except Exception as exc:
            fail(exc)

    @app.get("/auth/github/device/poll", dependencies=guarded)
    def github_poll(flow_id: str):
        result = github_device.poll(flow_id)
        if result["status"] != "done":
            return result
        conn = Connection(type="github", meta={"auth": "device"})
        storage.save_connection(conn, secret=result["token"])
        test = connectors.test(conn)
        conn.label = connectors.default_label(conn)
        storage.save_connection(conn)
        conn = storage.merge_duplicate(conn)
        return {"status": "done", "connection": _public(conn), "test": test}

    @app.post("/auth/gitlab/oauth/start", dependencies=guarded)
    def gitlab_start(body: GitLabOAuthIn):
        try:
            return gitlab_oauth.start(body.base_url)
        except Exception as exc:
            fail(exc)

    @app.get("/auth/gitlab/oauth/status", dependencies=guarded)
    def gitlab_status(flow_id: str):
        result = gitlab_oauth.status(flow_id)
        if result["status"] != "done":
            return result
        conn = Connection(type="gitlab", meta={"url": result["base_url"], "auth": "oauth"})
        storage.save_connection(conn, secret=result["token"])
        test = connectors.test(conn)
        conn.label = connectors.default_label(conn)
        storage.save_connection(conn)
        conn = storage.merge_duplicate(conn)
        return {"status": "done", "connection": _public(conn), "test": test}

    @app.post("/auth/slack/oauth/start", dependencies=guarded)
    def slack_start(body: SlackOAuthIn):
        try:
            return slack_oauth.start(body.client_id)
        except Exception as exc:
            fail(exc)

    @app.get("/auth/slack/oauth/status", dependencies=guarded)
    def slack_status(flow_id: str):
        result = slack_oauth.status(flow_id)
        if result["status"] != "done":
            return result
        conn = Connection(type="slack", meta={"auth": "oauth", "client_id": result["client_id"]})
        storage.save_connection(conn, secret=result["token"])
        test = connectors.test(conn)
        conn.label = connectors.default_label(conn)
        storage.save_connection(conn)
        conn = storage.merge_duplicate(conn)
        return {"status": "done", "connection": _public(conn), "test": test}

    @app.get("/auth/links", dependencies=guarded)
    def auth_links(gitlab_url: str = "https://gitlab.com"):
        return {"github_token_page": github_device.TOKEN_PAGE,
                "gitlab_token_page": gitlab_oauth.token_page(gitlab_url),
                "slack_manifest_url": slack_source.manifest_url(),
                "slack_manifest": slack_source.manifest(),
                "slack_redirect_url": slack_source.SLACK_REDIRECT_URL,
                "ai_key_page": "https://aistudio.google.com/apikey",
                **oauth_status()}

    # --- helpers for pickers -------------------------------------------------------

    @app.get("/email/providers", dependencies=guarded)
    def email_providers():
        return PROVIDERS

    @app.get("/email/{conn_id}/threads", dependencies=guarded)
    def email_threads(conn_id: str, q: str = ""):
        conn = get_conn(conn_id)
        try:
            meta, password = connectors.email_credentials(conn)
            return imap.list_threads(meta, password, query=q.strip())
        except Exception as exc:
            fail(exc)

    @app.get("/email/{conn_id}/contacts", dependencies=guarded)
    def email_contacts(conn_id: str, q: str = ""):
        conn = get_conn(conn_id)
        try:
            meta, password = connectors.email_credentials(conn)
            return imap.contacts(meta, password, query=q)
        except Exception as exc:
            fail(exc)

    @app.get("/slack/manifest-url", dependencies=guarded)
    def slack_manifest():
        return {"url": slack_source.manifest_url(), "manifest": slack_source.manifest()}

    @app.get("/slack/{conn_id}/conversations", dependencies=guarded)
    def slack_conversations(conn_id: str):
        conn = get_conn(conn_id)
        try:
            return connectors.slack_client(conn).conversation_list()
        except Exception as exc:
            fail(exc)

    @app.get("/code/{conn_id}/projects", dependencies=guarded)
    def code_projects(conn_id: str):
        conn = get_conn(conn_id)
        try:
            return connectors.list_projects(conn)
        except Exception as exc:
            fail(exc)

    # --- profiles --------------------------------------------------------------

    def _profile_view(p: Profile, conns: dict) -> dict:
        last = history.last_run(p.id, statuses=("sent", "failed", "running"))
        upcoming = (app.state.scheduler.upcoming(p) if app.state.scheduler
                    else {"next_run": None, "skipped_run": None})
        return {**p.model_dump(), "problems": profile_problems(p, conns), **upcoming,
                "last_run": last, "running": pipeline.is_running(p.id),
                "progress": pipeline.progress(p.id)}

    @app.get("/profiles", dependencies=guarded)
    def list_profiles():
        conns = storage.connections_by_id()
        return [_profile_view(p, conns) for p in storage.list_profiles()]

    @app.get("/profiles/{profile_id}", dependencies=guarded)
    def get_profile(profile_id: str):
        return _profile_view(get_prof(profile_id), storage.connections_by_id())

    @app.get("/profiles/{profile_id}/progress", dependencies=guarded)
    def get_progress(profile_id: str):
        get_prof(profile_id)
        return {"running": pipeline.is_running(profile_id),
                "progress": pipeline.progress(profile_id)}

    @app.post("/profiles", dependencies=guarded)
    def create_profile(profile: Profile):
        return storage.save_profile(profile)

    @app.put("/profiles/{profile_id}", dependencies=guarded)
    def update_profile(profile_id: str, profile: Profile):
        existing = get_prof(profile_id)
        profile.id, profile.created_at = existing.id, existing.created_at
        return storage.save_profile(profile)

    @app.delete("/profiles/{profile_id}", dependencies=guarded)
    def delete_profile(profile_id: str):
        get_prof(profile_id)
        storage.delete_profile(profile_id)
        return {"ok": True}

    @app.post("/profiles/{profile_id}/preview", dependencies=guarded)
    def preview(profile_id: str, body: RunIn | None = None):
        profile = get_prof(profile_id)
        day = report_day(profile, body.day if body else None)
        try:
            result = pipeline.run(profile, trigger="preview", day=day, send=False)
        except pipeline.ProfileBusy as exc:
            raise HTTPException(409, str(exc))
        return result.as_dict(include_html=True)

    @app.post("/profiles/{profile_id}/test-send", dependencies=guarded)
    def test_send(profile_id: str, body: TestSendIn):
        profile = get_prof(profile_id)
        to = body.to
        if not to:
            to = storage.get_connection(profile.sender_connection_id or "").meta.get("address")
        try:
            result = pipeline.run(profile, trigger="test", day=report_day(profile, body.day),
                                  send=True, test_to=to)
        except pipeline.ProfileBusy as exc:
            raise HTTPException(409, str(exc))
        return result.as_dict(include_html=True)

    @app.post("/profiles/{profile_id}/send", dependencies=guarded)
    def send_now(profile_id: str, body: RunIn | None = None):
        profile = get_prof(profile_id)
        day = report_day(profile, body.day if body else None)
        if pipeline.is_running(profile.id):
            raise HTTPException(409, f"'{profile.name}' is already running")
        problems = profile_problems(profile, storage.connections_by_id())
        if problems:
            raise HTTPException(400, "Setup incomplete: " + ", ".join(problems))
        if app.state.scheduler:
            app.state.scheduler.run_now(profile.id, day=day)
            return {"started": True}
        result = pipeline.run(profile, trigger="manual", day=day)
        return result.as_dict()

    # --- runs ------------------------------------------------------------------

    @app.get("/runs", dependencies=guarded)
    def list_runs(profile_id: str | None = None, limit: int = 100):
        return history.list_runs(profile_id, limit)

    @app.get("/runs/{run_id}", dependencies=guarded)
    def get_run(run_id: str):
        run = history.get_run(run_id)
        if not run:
            raise HTTPException(404, "Run not found")
        html = ""
        if run.get("html_path"):
            try:
                with open(run["html_path"], encoding="utf-8") as f:
                    html = f.read()
            except OSError:
                pass
        return {**run, "html": html}

    @app.get("/scheduler/next", dependencies=guarded)
    def next_runs():
        return app.state.scheduler.next_runs() if app.state.scheduler else {}

    return app
