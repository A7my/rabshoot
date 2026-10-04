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


class DraftContent(BaseModel):
    subject: str = ""
    body: str = ""  # the email as editable text (see render.editable_text)


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

    def edited_body(self, content: DraftContent) -> str | None:
        """The edited text, or None while it is unchanged (the original layout is kept then)."""
        return content.body if content.body.strip() != self.content.body.strip() else None


_drafts: dict[str, Draft] = {}
_lock = threading.Lock()


def save(profile_id: str, day: date, subject: str, body: str, projects: list[dict],
         conversations: list[dict], steps: list[dict]) -> Draft:
    draft = Draft(id=new_id("draft"), profile_id=profile_id, day=day,
                  projects=copy.deepcopy(projects), conversations=copy.deepcopy(conversations),
                  steps=[dict(s) for s in steps if s.get("key") != "email"],
                  content=DraftContent(subject=subject, body=body))
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
