import json
import logging
import os
import re
import time

import requests

log = logging.getLogger(__name__)

RETRYABLE = {429, 500, 502, 503, 504}
# Seconds to wait before each round over all models (busy models often recover in minutes).
RETRY_WAITS = (0, 20, 60, 120)
FAST_RETRY_WAITS = (0,)


def _error_message(resp: requests.Response) -> str:
    try:
        data = resp.json()
        if isinstance(data, list) and data:
            data = data[0]
        return str(data["error"]["message"])[:160]
    except (ValueError, KeyError, TypeError, IndexError):
        return resp.text[:160]

_SYSTEM = ("You write concise daily engineering reports for managers. "
           "Always write in {language}, in clear plain sentences.")

_PROJECT_PROMPT = """Project: {name}

Commit messages (hints only, they may be vague or misleading; trust the code):
{commits}
{mrs}
Code changes today (unified diffs, some files truncated or omitted):
{diff}

Task: describe what ACTUALLY changed in this project today, based on the code.
- 1 to {max_points} bullet points, most important first.
- One sentence each, focused on behavior: features added, bugs fixed, logic changed, and why if visible.
- Mention a module/file only when it helps understanding.
- Skip trivial changes (formatting, typos, comments, dependency bumps) unless that is all there is.
- Start a bullet with "[Major]" when it is significant: new feature, database/migration change,
  API or contract change, security, payment, configuration or infrastructure change.
{extra}
Respond with JSON only: {{"points": ["...", "..."]}}"""

_SLACK_PROMPT = """Conversation: {name}
Messages (time, author: text; thread replies are indented under their parent):
{messages}

Task: extract the work-related points from this conversation for today's report.
- Include: work done or in progress, decisions, bugs/problems/blockers, requests and action items
  (who should do what), deadlines, deployments, client feedback.
- Exclude: greetings, small talk, thanks, jokes, emoji-only messages, "ok"-style acknowledgements,
  and anything personal.
- Translate to {language}. Merge related messages into one point. Keep people's names.
- At most {max_points} points. If nothing is work-related, return an empty list.
{extra}
Respond with JSON only: {{"points": ["...", "..."]}}"""


class AIClient:
    def __init__(self, cfg: dict):
        self.base_url = cfg.get("base_url", "").rstrip("/")
        self.model = cfg["model"]
        self.models = [self.model, *(cfg.get("fallback_models") or [])]
        self.language = cfg.get("language", "English")
        self.extra = (cfg.get("extra_instructions") or "").strip()
        self.max_points = int(cfg.get("max_points", 6))
        self.session = requests.Session()
        key = os.environ.get("AI_API_KEY")
        if key:
            self.session.headers["Authorization"] = f"Bearer {key}"
        # Set after a request exhausted every retry, so later items in the run fail fast.
        self.unavailable = False

    def _chat(self, prompt: str) -> str:
        """Try every model; when all are busy, wait and go round again."""
        messages = [
            {"role": "system", "content": _SYSTEM.format(language=self.language)},
            {"role": "user", "content": prompt},
        ]
        errors: dict[str, str] = {}
        dead: set[str] = set()
        for wait in (FAST_RETRY_WAITS if self.unavailable else RETRY_WAITS):
            candidates = [m for m in self.models if m not in dead]
            if not candidates:
                break
            if wait:
                log.warning("All AI models are busy; retrying in %ss", wait)
                time.sleep(wait)
            for model in candidates:
                body = {"model": model, "temperature": 0.2, "messages": messages}
                try:
                    resp = self.session.post(f"{self.base_url}/chat/completions", json=body,
                                             timeout=90)
                except requests.RequestException as exc:
                    errors[model] = exc.__class__.__name__
                    continue
                if resp.ok:
                    if model != self.models[0]:
                        # Stick with the model that works for the rest of this run.
                        self.models.remove(model)
                        self.models.insert(0, model)
                    self.model = model
                    self.unavailable = False
                    return resp.json()["choices"][0]["message"]["content"] or ""
                if resp.status_code not in RETRYABLE:
                    dead.add(model)
                errors[model] = f"{resp.status_code} {_error_message(resp)}"
                log.warning("AI model %s unavailable (%s)", model, errors[model])
        self.unavailable = True
        raise RuntimeError("AI service unavailable: "
                           + " | ".join(f"{m}: {e}" for m, e in errors.items()))

    def _points(self, prompt: str) -> list[str]:
        raw = self._chat(prompt)
        start, end = raw.find("{"), raw.rfind("}")
        if start != -1 and end > start:
            try:
                points = json.loads(raw[start:end + 1]).get("points", [])
                return [str(p).strip() for p in points if str(p).strip()][: self.max_points]
            except json.JSONDecodeError:
                pass
        lines = [re.sub(r"^\s*[-*•\d.)]+\s*", "", ln).strip() for ln in raw.splitlines()]
        return [ln for ln in lines if ln][: self.max_points]

    def summarize_project(self, project: dict) -> list[str]:
        commits = "\n".join(f"- {c['title']} ({c['author']})" for c in project["commits"]) or "- none"
        mrs = ""
        if project["merge_requests"]:
            mrs = "\nMerge requests today:\n" + "\n".join(
                f"- [{m['action']}] !{m['iid']} {m['title']}" for m in project["merge_requests"]
            ) + "\n"
        return self._points(_PROJECT_PROMPT.format(
            name=project["name"], commits=commits, mrs=mrs,
            diff=project.get("diff_text") or "(no diff available)",
            max_points=self.max_points, extra=self.extra,
        ))

    def summarize_conversation(self, conv: dict) -> list[str]:
        lines = []
        for t in conv["threads"]:
            when = f"(thread from {t['date']})" if t["from_earlier"] else t["time"]
            lines.append(f"{when} {t['user']}: {t['text']}")
            lines.extend(f"    {r['time']} {r['user']}: {r['text']}" for r in t["replies"])
        return self._points(_SLACK_PROMPT.format(
            name=conv["name"], messages="\n".join(lines), language=self.language,
            max_points=self.max_points, extra=self.extra,
        ))


def enrich(cfg: dict, gitlab: dict, slack: dict) -> None:
    """Add AI `changes` to projects and `points` to Slack conversations, in place."""
    ai_cfg = cfg.get("ai") or {}
    if not ai_cfg.get("enabled"):
        return
    client = AIClient(ai_cfg)

    for project in gitlab.get("projects", []):
        if project.get("error") or not (project["commits"] or project["merge_requests"]):
            continue
        try:
            project["changes"] = client.summarize_project(project)
        except Exception as exc:
            log.error("AI summary failed for %s: %s", project["name"], exc)

    for conv in slack.get("conversations", []):
        if conv.get("error") or not conv["threads"]:
            conv["points"] = []
            continue
        try:
            conv["points"] = client.summarize_conversation(conv)
        except Exception as exc:
            log.error("AI summary failed for %s: %s", conv["name"], exc)
            conv["ai_failed"] = True
