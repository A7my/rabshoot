import pytest

from rabshoot_engine import connectors, pipeline, storage
from rabshoot_engine.mail import imap
from rabshoot_engine.mail.imap import ThreadParent, reply_all_recipients
from rabshoot_engine.models import Connection, Delivery, Profile, ThreadRef

ME = "me@example.com"


def _parent(**kw) -> ThreadParent:
    base = dict(message_id="<m@x>", references="", subject="Daily Report — 2026-09-28",
                reply_to=[ME], to=[ME], cc=[], participants=[ME])
    return ThreadParent(**{**base, **kw})


def test_latest_message_to_myself_falls_back_to_the_rest_of_the_thread():
    parent = _parent(participants=[ME, "boss@x.com", "team@x.com"])
    assert reply_all_recipients(parent, ME) == (["boss@x.com", "team@x.com"], [])


def test_latest_message_recipients_win_over_older_participants():
    parent = _parent(to=[ME, "lead@x.com"], participants=[ME, "lead@x.com", "old@x.com"])
    assert reply_all_recipients(parent, ME) == (["lead@x.com"], [])


def _thread_profile(reply_all=True, **delivery) -> Profile:
    return Profile(delivery=Delivery(mode="thread", thread=ThreadRef(subject="Daily Report"),
                                     reply_all=reply_all, **delivery))


def test_thread_with_only_me_replies_to_me_instead_of_failing(monkeypatch):
    monkeypatch.setattr(imap, "find_parent", lambda *a: _parent())
    plan = pipeline.plan_email(_thread_profile(), {"address": ME}, "pw", "")
    assert plan.to == [ME] and plan.only_me
    assert plan.subject == "Re: Daily Report — 2026-09-28"
    assert "only you" in pipeline._sent_message(plan)


def test_extra_recipients_are_used_with_a_self_only_thread(monkeypatch):
    monkeypatch.setattr(imap, "find_parent", lambda *a: _parent())
    plan = pipeline.plan_email(_thread_profile(to=["boss@x.com"]), {"address": ME}, "pw", "")
    assert plan.to == ["boss@x.com"] and not plan.only_me


def test_reply_all_off_without_recipients_is_a_clear_error(monkeypatch):
    monkeypatch.setattr(imap, "find_parent", lambda *a: _parent(participants=[ME, "b@x.com"]))
    with pytest.raises(ValueError, match="Reply to everyone"):
        pipeline.plan_email(_thread_profile(reply_all=False), {"address": ME}, "pw", "")


def test_delivery_problem_fails_before_collecting_anything(monkeypatch):
    sender = storage.save_connection(Connection(type="email", meta={"address": ME}),
                                     secret={"password": "x"})
    profile = storage.save_profile(_thread_profile().model_copy(
        update={"sender_connection_id": sender.id}))
    monkeypatch.setattr(pipeline, "profile_problems", lambda p, c: [])
    monkeypatch.setattr(connectors, "email_credentials", lambda c: ({"address": ME}, "x"))

    def missing(*a):
        raise LookupError("The selected email thread was not found in the sender's mailbox")

    monkeypatch.setattr(imap, "find_parent", missing)
    monkeypatch.setattr(pipeline, "build", lambda *a: pytest.fail("should not collect"))
    result = pipeline.run(profile, trigger="manual")
    assert result.status == "failed" and "not found" in result.error
    assert pipeline.progress(profile.id)["percent"] < 10
