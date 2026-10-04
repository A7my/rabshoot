"""Reports built by a preview or test, kept in memory so they can be edited and sent as they are."""

import copy
import threading
import time
from dataclasses import dataclass, field
from datetime import date

from pydantic import BaseModel

from .models import new_id

MAX_AGE_SECONDS = 12 * 3600
MAX_DRAFTS = 20


class DraftItem(BaseModel):
    key: str  # "p<index>" for a project, "c<index>" for a Slack conversation
    kind: str = ""
    name: str = ""
    points: list[str] = []


class DraftContent(BaseModel):
    subject: str = ""
    note: str = ""
    items: list[DraftItem] = []


@dataclass
class Draft:
    id: str
    profile_id: str
    day: date
    projects: list[dict]
    conversations: list[dict]
    steps: list[dict]
    content: DraftContent
    created: float = field(default_factory=time.monotonic)


_drafts: dict[str, Draft] = {}
_lock = threading.Lock()


def _initial_content(subject: str, projects: list[dict], conversations: list[dict]) -> DraftContent:
    items = [DraftItem(key=f"p{i}", kind="project", name=p["name"], points=list(p.get("changes") or []))
             for i, p in enumerate(projects) if not p.get("error")]
    items += [DraftItem(key=f"c{i}", kind="conversation", name=c["name"], points=list(c.get("points") or []))
              for i, c in enumerate(conversations) if not c.get("error")]
    return DraftContent(subject=subject, items=items)


def save(profile_id: str, day: date, subject: str, projects: list[dict], conversations: list[dict],
         steps: list[dict]) -> Draft:
    draft = Draft(id=new_id("draft"), profile_id=profile_id, day=day,
                  projects=copy.deepcopy(projects), conversations=copy.deepcopy(conversations),
                  steps=[dict(s) for s in steps if s.get("key") != "email"],
                  content=_initial_content(subject, projects, conversations))
    with _lock:
        now = time.monotonic()
        for old in [k for k, d in _drafts.items() if now - d.created > MAX_AGE_SECONDS]:
            del _drafts[old]
        while len(_drafts) >= MAX_DRAFTS:
            del _drafts[next(iter(_drafts))]
        _drafts[draft.id] = draft
    return draft


def get(draft_id: str) -> Draft:
    with _lock:
        draft = _drafts.get(draft_id)
    if not draft or time.monotonic() - draft.created > MAX_AGE_SECONDS:
        raise KeyError(draft_id)
    return draft


def _clean(points: list[str]) -> list[str]:
    return [" ".join(str(p).split()) for p in points if str(p).strip()]


def apply(draft: Draft, content: DraftContent) -> tuple[list[dict], list[dict]]:
    """Copies of the draft's projects and conversations with the edited points in place."""
    projects, conversations = copy.deepcopy(draft.projects), copy.deepcopy(draft.conversations)
    for item in content.items:
        kind, index = item.key[:1], item.key[1:]
        target, name = {"p": (projects, "changes"), "c": (conversations, "points")}.get(kind, (None, ""))
        if target is None or not index.isdigit() or int(index) >= len(target):
            continue
        points = _clean(item.points)
        # Without AI points the email shows the raw commits / messages; keep that unless points were added.
        if points or name in target[int(index)]:
            target[int(index)][name] = points
    return projects, conversations


def merge_ai(content: DraftContent, answer: dict) -> DraftContent:
    """Take the AI's edited points per known item; anything it dropped or invented is ignored."""
    edited = {}
    for item in answer.get("items") or []:
        if isinstance(item, dict) and isinstance(item.get("points"), list):
            edited[str(item.get("key"))] = item["points"]
    subject, note = answer.get("subject"), answer.get("note")
    return DraftContent(
        subject=subject.strip() if isinstance(subject, str) and subject.strip() else content.subject,
        note=note.strip() if isinstance(note, str) else content.note,
        items=[item.model_copy(update={"points": _clean(edited[item.key])}) if item.key in edited else item
               for item in content.items],
    )
