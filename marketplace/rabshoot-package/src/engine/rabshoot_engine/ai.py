import json
import logging
import re
import time

import requests

log = logging.getLogger(__name__)

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai"
DEFAULT_MODEL = "gemini-3.5-flash"
DEFAULT_FALLBACKS = ["gemini-3.6-flash", "gemini-3.1-flash-lite", "gemini-flash-latest",
                     "gemini-3-flash-preview"]
KEY_PAGE = "https://aistudio.google.com/apikey"
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


_POLISH_SYSTEM = "You polish daily work report emails for their author."

_POLISH_PROMPT = """Here is a daily work report email in a simple text format: a line starting with
"## " is a section heading, "### " is a project or chat name, "• " is a bullet point, and "[Major]"
at the start of a bullet marks an important change.

Report:
<<<
{body}
>>>

{request}

Always:
- Make it read well: clear, professional and short. Never make it longer, except to add what the author asks for.
- Fix spelling, grammar and punctuation.
- Put things in a sensible order: most important first, related points together.
- Keep every fact, name, project name, number and code identifier. Don't invent work.
- Keep the same format markers (##, ###, •, [Major]).
- Keep the report's language ({language}) unless the author asks for another one.
Respond with the full edited report only, in the same format, without explanations or code fences."""


class AIClient:
    def __init__(self, api_key: str, base_url: str = GEMINI_BASE_URL, model: str = DEFAULT_MODEL,
                 fallback_models: list[str] | None = None, language: str = "English",
                 extra_instructions: str = "", max_points: int = 6, timeout: int = 90):
        self.base_url = (base_url or GEMINI_BASE_URL).rstrip("/")
        self.model = model or DEFAULT_MODEL
        fallbacks = DEFAULT_FALLBACKS if fallback_models is None else fallback_models
        self.models = list(dict.fromkeys([self.model, *fallbacks]))
        self.language = language or "English"
        self.extra = (extra_instructions or "").strip()
        self.max_points = int(max_points)
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"Bearer {api_key}"
        # Set after a request exhausted every retry, so later items in the run fail fast.
        self.unavailable = False

    def chat(self, prompt: str, system: str | None = None,
             waits: tuple[int, ...] | None = None) -> str:
        """Try every model; when all are busy, wait and go round again (`waits` seconds)."""
        messages = [
            {"role": "system", "content": system or _SYSTEM.format(language=self.language)},
            {"role": "user", "content": prompt},
        ]
        if waits is None:
            waits = FAST_RETRY_WAITS if self.unavailable else RETRY_WAITS
        errors: dict[str, str] = {}
        dead: set[str] = set()
        for wait in waits:
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
                                             timeout=self.timeout)
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
                if resp.status_code in (401, 403):
                    raise PermissionError("The AI key was rejected (invalid or revoked key)")
                if resp.status_code not in RETRYABLE:
                    dead.add(model)
                errors[model] = f"{resp.status_code} {_error_message(resp)}"
                log.warning("AI model %s unavailable (%s)", model, errors[model])
        self.unavailable = True
        raise RuntimeError("AI service unavailable: "
                           + " | ".join(f"{m}: {e}" for m, e in errors.items()))

    def ping(self) -> str:
        """Cheap validation call; returns the model that answered."""
        self.chat('Reply with the single word "OK".', system="You are a health check.",
                  waits=(0, 5))
        return self.model

    def _points(self, prompt: str) -> list[str]:
        raw = self.chat(prompt)
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
            mrs = "\nMerge/pull requests today:\n" + "\n".join(
                f"- [{m['action']}] {m['ref']} {m['title']}" for m in project["merge_requests"]
            ) + "\n"
        return self._points(_PROJECT_PROMPT.format(
            name=project["name"], commits=commits, mrs=mrs,
            diff=project.get("diff_text") or "(no diff available)",
            max_points=self.max_points, extra=self.extra,
        ))

    def polish_report(self, body: str, instruction: str = "") -> str:
        """Rewrite the editable report text nicely; `instruction` is the author's own request."""
        request = (f"The author also asks: {instruction.strip()}" if instruction.strip()
                   else "The author asks you to polish it.")
        raw = self.chat(_POLISH_PROMPT.format(body=body.strip(), request=request,
                                              language=self.language),
                        system=_POLISH_SYSTEM, waits=(0, 10))
        text = re.sub(r"^\s*```[a-z]*\s*\n|\n\s*```\s*$", "", raw.strip())
        text = text.strip().removeprefix("<<<").removesuffix(">>>").strip()
        if not text:
            raise RuntimeError("The AI sent back an empty answer. Try again.")
        return text + "\n"

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


def enrich(client: AIClient, projects: list[dict], conversations: list[dict],
           progress=None) -> dict:
    """Add `changes` to projects and `points` to conversations in place; returns counts.

    progress(done, total, name) is called before each item is summarized.
    """
    stats = {"ok": 0, "failed": 0, "errors": []}
    todo = [p["name"] for p in projects
            if not p.get("error") and (p["commits"] or p["merge_requests"])]
    todo += [c["name"] for c in conversations if not c.get("error") and c["threads"]]
    done = 0

    def tick(name: str) -> None:
        nonlocal done
        if progress:
            progress(done, len(todo), name)
        done += 1

    for project in projects:
        if project.get("error") or not (project["commits"] or project["merge_requests"]):
            continue
        tick(project["name"])
        try:
            project["changes"] = client.summarize_project(project)
            stats["ok"] += 1
        except PermissionError:
            raise
        except Exception as exc:
            log.error("AI summary failed for %s: %s", project["name"], exc)
            stats["failed"] += 1
            stats["errors"].append(f"{project['name']}: {exc}")

    for conv in conversations:
        if conv.get("error") or not conv["threads"]:
            conv["points"] = []
            continue
        tick(conv["name"])
        try:
            conv["points"] = client.summarize_conversation(conv)
            stats["ok"] += 1
        except PermissionError:
            raise
        except Exception as exc:
            log.error("AI summary failed for %s: %s", conv["name"], exc)
            conv["ai_failed"] = True
            stats["failed"] += 1
            stats["errors"].append(f"{conv['name']}: {exc}")
    return stats
