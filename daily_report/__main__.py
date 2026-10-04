import argparse
import logging
import sys
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

from .check import print_conversations, run_checks
from .config import DEFAULT_CONFIG_PATH, load_config, update_schedule
from .scheduler import next_run, run_report, serve


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="daily_report",
                                     description="Daily GitLab + Slack report")
    parser.add_argument("-c", "--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("serve", help="Run the scheduler (picks up config changes live)")

    run = sub.add_parser("run", help="Build and send a report now")
    run.add_argument("--date", type=date.fromisoformat, help="YYYY-MM-DD (default: today)")
    run.add_argument("--dry-run", action="store_true", help="Print instead of sending")

    st = sub.add_parser("set-time", help="Change the daily send time")
    st.add_argument("time", help="HH:MM (24h)")
    st.add_argument("--days", help='e.g. "mon-fri", "sun-thu", "*"')
    st.add_argument("--timezone", help='e.g. "Africa/Cairo"')

    sub.add_parser("schedule", help="Show the current schedule and next run")
    sub.add_parser("check", help="Verify GitLab/Slack/email settings without sending anything")
    sub.add_parser("list", help="Print your Slack channels and chats, ready to paste in config")

    args = parser.parse_args(argv)
    load_dotenv()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    if not args.verbose:
        logging.getLogger("apscheduler").setLevel(logging.WARNING)

    if args.command == "serve":
        serve(args.config)
    elif args.command == "run":
        report = run_report(args.config, day=args.date, dry_run=args.dry_run)
        if args.dry_run:
            preview = Path("reports/preview.html")
            preview.parent.mkdir(exist_ok=True)
            preview.write_text(report.html, encoding="utf-8")
            print(f"Subject: {report.subject}\n")
            print(report.text)
            print(f"Email preview saved to {preview.resolve()}")
    elif args.command == "set-time":
        values = {"time": args.time}
        if args.days:
            values["days"] = args.days
        if args.timezone:
            values["timezone"] = args.timezone
        try:
            cfg = update_schedule(args.config, **values)
        except (ValueError, KeyError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 2
        print(f"Schedule updated. Next run: {next_run(cfg)}")
    elif args.command == "schedule":
        cfg = load_config(args.config)
        s = cfg["schedule"]
        print(f"Time: {s['time']}  Days: {s.get('days', '*')}  Timezone: {s.get('timezone')}")
        print(f"Next run: {next_run(cfg)}")
    elif args.command == "check":
        return 0 if run_checks(load_config(args.config)) else 1
    elif args.command == "list":
        print_conversations()
    return 0


if __name__ == "__main__":
    sys.exit(main())
