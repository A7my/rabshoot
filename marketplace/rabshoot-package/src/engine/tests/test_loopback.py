import socket
import time
from urllib.parse import urlencode
from urllib.request import urlopen

from rabshoot_engine.auth.loopback import LoopbackFlows


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_signing_in_again_replaces_the_waiting_sign_in():
    flows = LoopbackFlows("Slack")
    port = free_port()
    exchange = lambda flow, code: {"code": code, "client_id": flow["client_id"]}

    first_id, _ = flows.start(port, "/cb", exchange, client_id="old")
    second_id, second = flows.start(port, "/cb", exchange, client_id="new")

    assert flows.status(first_id)["status"] == "cancelled"
    query = urlencode({"state": second["state"], "code": "abc"})
    urlopen(f"http://127.0.0.1:{port}/cb?{query}", timeout=5).read()
    for _ in range(20):
        result = flows.status(second_id)
        if result["status"] != "pending":
            break
        time.sleep(0.1)
    assert result == {"status": "done", "message": "", "code": "abc", "client_id": "new"}


def test_port_held_by_another_program_gives_a_clear_message():
    with socket.socket() as other:
        other.bind(("127.0.0.1", 0))
        other.listen()
        port = other.getsockname()[1]
        try:
            LoopbackFlows("Slack").start(port, "/cb", lambda f, c: {})
        except RuntimeError as exc:
            assert "Another program is using port" in str(exc)
        else:
            raise AssertionError("expected the busy port to be reported")
