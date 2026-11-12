import argparse
import json
import logging
import os
import secrets
import socket
import sys
import threading
from datetime import date
from logging.handlers import RotatingFileHandler
from pathlib import Path

from . import __version__, paths


def _logging(verbose: bool) -> None:
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stderr)]
    try:
        handlers.append(RotatingFileHandler(paths.logs_dir() / "engine.log", maxBytes=2_000_000,
                                            backupCount=3, encoding="utf-8"))
    except OSError:
        pass
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO, handlers=handlers,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("apscheduler").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def _watch_parent() -> None:
    """Exit when the desktop shell goes away (its end of our stdin closes)."""
    def watch():
        try:
            while sys.stdin.read(1024):
                pass
        except Exception:
            pass
        os._exit(0)
    threading.Thread(target=watch, daemon=True).start()


def cmd_serve(args) -> None:
    import uvicorn

    from . import storage
    from .api import create_app
    from .scheduler import Scheduler

    log = logging.getLogger("rabshoot_engine")

    token = args.token or os.environ.get("RABSHOOT_TOKEN") or secrets.token_urlsafe(32)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", args.port))
    port = sock.getsockname()[1]

    try:
        if removed := storage.merge_saved_duplicates():
            log.info("Merged %d duplicate account(s)", removed)
    except Exception:
        log.exception("Could not merge duplicate accounts")
    scheduler = Scheduler()
    scheduler.start(catch_up=not args.no_catch_up)
    app = create_app(token, scheduler)

    print(json.dumps({"event": "ready", "port": port, "token": token, "version": __version__}),
          flush=True)
    if args.watch_stdin:
        _watch_parent()
    config = uvicorn.Config(app, log_level="warning", access_log=False)
    try:
        uvicorn.Server(config).run(sockets=[sock])
    finally:
        scheduler.shutdown()


def cmd_run(args) -> None:
    from . import pipeline, storage

    profiles = storage.list_profiles()
    target = next((p for p in profiles if args.profile in (p.id, p.name)), None)
    if not target:
        sys.exit(f"Profile {args.profile!r} not found. Available: "
                 + ", ".join(f"{p.name} ({p.id})" for p in profiles))
    day = date.fromisoformat(args.date) if args.date else None
    result = pipeline.run(target, trigger="manual" if not args.dry_run else "preview", day=day,
                          send=not args.dry_run)
    for step in result.steps:
        print(f"[{step['status']:>7}] {step['key']}: {step['message']}")
    print(f"Status: {result.status} {result.error}")
    if args.dry_run and result.report:
        out = Path("rabshoot-preview.html")
        out.write_text(result.report.html_for_display(), encoding="utf-8")
        print(result.report.text)
        print(f"HTML preview saved to {out.resolve()}")


def cmd_list(_args) -> None:
    from . import storage

    for c in storage.list_connections():
        print(f"connection {c.id}  {c.type:<7} {c.label}  [{c.status}]")
    for p in storage.list_profiles():
        s = p.schedule
        when = {"recurring": f"{s.time} {s.days}", "once": f"once {s.once_date} {s.time}",
                "now": "manual only"}[s.mode]
        print(f"profile    {p.id}  {p.name}  {when} {s.timezone}  enabled={p.enabled}")


def cmd_import(args) -> None:
    from . import legacy

    profile = legacy.import_legacy(Path(args.folder))
    print(f"Imported profile '{profile.name}' ({profile.id})")


def main() -> None:
    parser = argparse.ArgumentParser(prog="rabshoot-engine")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("serve", help="Run the local API and the scheduler")
    p.add_argument("--port", type=int, default=int(os.environ.get("RABSHOOT_PORT", "0")))
    p.add_argument("--token", default="")
    p.add_argument("--watch-stdin", action="store_true")
    p.add_argument("--no-catch-up", action="store_true")
    p.set_defaults(func=cmd_serve)

    p = sub.add_parser("run", help="Build (and send) one profile's report now")
    p.add_argument("profile", help="profile id or name")
    p.add_argument("--date", help="YYYY-MM-DD (default: today)")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_run)

    sub.add_parser("list", help="Show connections and profiles").set_defaults(func=cmd_list)

    p = sub.add_parser("import-legacy", help="Import config.yaml + .env from daily_report")
    p.add_argument("folder")
    p.set_defaults(func=cmd_import)

    args = parser.parse_args()
    _logging(args.verbose)
    args.func(args)


if __name__ == "__main__":
    main()
