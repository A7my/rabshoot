import os

from .ai import AIClient
from .config import DayWindow
from .delivery import plan_email, smtp_connection
from .gitlab_source import GitLabClient
from .slack_source import SlackClient, configured_conversations, reader_client

OK, FAIL = "[OK]  ", "[FAIL]"


def check_gitlab(cfg: dict) -> bool:
    gl_cfg = cfg.get("gitlab") or {}
    if not gl_cfg.get("enabled"):
        print("GitLab: disabled in config")
        return True
    if not os.environ.get("GITLAB_TOKEN"):
        print(f"{FAIL} GITLAB_TOKEN is not set in .env")
        return False
    try:
        client = GitLabClient(gl_cfg["url"], os.environ["GITLAB_TOKEN"])
        resp = client.session.get(f"{client.api}/user", timeout=client.timeout)
        resp.raise_for_status()
        print(f"{OK} GitLab {gl_cfg['url']} as @{resp.json()['username']}")

        window = DayWindow.today(cfg["schedule"].get("timezone", "UTC"))
        projects = client.active_projects(window.start)
        print(f"{OK} {len(projects)} project(s) with activity today")
        for p in projects[:15]:
            print(f"       - {p['path_with_namespace']}")
        return True
    except Exception as exc:
        print(f"{FAIL} GitLab: {exc}")
        return False


def check_slack(cfg: dict) -> bool:
    sl_cfg = cfg.get("slack") or {}
    ok = True
    try:
        reader = reader_client()
        who = reader.call("auth.test")
        kind = "user token" if os.environ.get("SLACK_USER_TOKEN") else "bot token"
        print(f"{OK} Slack workspace '{who['team']}' as {who['user']} ({kind})")
    except Exception as exc:
        print(f"{FAIL} Slack: {exc}")
        return False

    if sl_cfg.get("enabled"):
        refs = configured_conversations(sl_cfg)
        if not refs:
            print(f"{FAIL} slack.channels and slack.direct_messages are both empty")
            ok = False
        for ref in refs:
            try:
                conv_id, name = reader.resolve(ref)
                reader.call("conversations.history", channel=conv_id, limit=1)
                print(f"{OK} read  {ref:<20} -> {name} ({conv_id})")
            except Exception as exc:
                print(f"{FAIL} read  {ref:<20} -> {exc}")
                ok = False

    target = (cfg.get("delivery") or {}).get("slack") or {}
    if target.get("enabled"):
        try:
            conv_id, name = reader.resolve(target["channel"])
            bot_token = os.environ.get("SLACK_BOT_TOKEN")
            if bot_token:
                bot = SlackClient(bot_token)
                info = bot.call("conversations.info", channel=conv_id)["channel"]
                if not info.get("is_member", True):
                    raise RuntimeError("bot is not in this channel, run /invite @Daily Report")
            print(f"{OK} post  {target['channel']:<20} -> {name} ({conv_id})")
        except Exception as exc:
            print(f"{FAIL} post  {target['channel']:<20} -> {exc}")
            ok = False
    return ok


def check_email(cfg: dict) -> bool:
    email = (cfg.get("delivery") or {}).get("email") or {}
    if not email.get("enabled"):
        print("Email: disabled in config")
        return True
    ok = True
    try:
        with smtp_connection(email):
            pass
        print(f"{OK} SMTP login to {email['smtp_host']}:{email.get('smtp_port', 587)}")
    except Exception as exc:
        print(f"{FAIL} SMTP {email.get('smtp_host')}: {exc}")
        ok = False

    try:
        plan = plan_email(email, "{title} — {date}")
    except Exception as exc:
        print(f"{FAIL} email: {exc}")
        return False
    if plan.parent:
        print(f"{OK} thread found: \"{plan.parent.subject}\"")
        print(f"       replying as: \"{plan.subject}\"")
    print(f"{OK} email to: {', '.join(plan.to)}")
    if plan.cc:
        print(f"       cc: {', '.join(plan.cc)}")
    if plan.bcc:
        print(f"       bcc: {', '.join(plan.bcc)}")
    return ok


def check_ai(cfg: dict) -> bool:
    ai_cfg = cfg.get("ai") or {}
    if not ai_cfg.get("enabled"):
        print("AI: disabled in config (raw commits and messages will be sent)")
        return True
    if not os.environ.get("AI_API_KEY") and "localhost" not in ai_cfg.get("base_url", ""):
        print(f"{FAIL} AI_API_KEY is not set in .env")
        return False
    try:
        client = AIClient(ai_cfg)
        points = client._points(
            'Reply with exactly this JSON and nothing else: {"points": ["ready"]}')
        print(f"{OK} AI {client.model} replied: {points}")
        return True
    except Exception as exc:
        print(f"{FAIL} AI: {exc}")
        return False


def run_checks(cfg: dict) -> bool:
    results = [check_gitlab(cfg), check_slack(cfg), check_email(cfg), check_ai(cfg)]
    return all(results)


def print_conversations() -> None:
    client = reader_client()
    convs = client.conversations()
    users = client.users()

    channels = sorted(
        (c for c in convs if (c.get("is_channel") or c.get("is_group"))
         and not c.get("is_mpim") and c.get("is_member")),
        key=lambda c: c.get("name", ""),
    )
    print("# Paste the lines you want under slack.channels in config.yaml\n")
    for c in channels:
        private = "    # private" if c.get("is_private") else ""
        print(f'    - "#{c["name"]}"{private}')

    print("\n# Paste the lines you want under slack.direct_messages in config.yaml\n")
    dms = []
    for c in convs:
        u = users.get(c.get("user"), {}) if c.get("is_im") else None
        if u is None or not u or u.get("is_bot") or u.get("deleted") \
                or c.get("user") == "USLACKBOT":
            continue
        dms.append((u["name"], client.user_name(u["id"])))
    for handle, display in sorted(dms, key=lambda d: d[1].lower()):
        print(f'    - "@{handle}"    # {display}')

    groups = [c for c in convs if c.get("is_mpim")]
    if groups:
        print("\n# Group chats (also go under slack.direct_messages)\n")
        for c in groups:
            members = c.get("purpose", {}).get("value") or c.get("name", "")
            print(f'    - "{c["id"]}"    # {members}')
