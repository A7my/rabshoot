"""PKCE helpers and a one-shot loopback redirect listener shared by the browser sign-in flows."""

import base64
import hashlib
import html
import secrets
import threading
import time
import uuid
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

_DONE_PAGE = """<!doctype html><html><body style="background:#0a0b10;color:#e6e8f0;
font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:100vh">
<div style="text-align:center"><h2>{title}</h2><p>{body}</p></div></body></html>"""


def pkce_pair() -> tuple[str, str]:
    """(code_verifier, S256 code_challenge)."""
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode()).digest()
    return verifier, base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


class LoopbackFlows:
    """Pending sign-ins; each one listens on 127.0.0.1:<port><path> until the browser returns."""

    def __init__(self, service: str):
        self.service = service
        self._flows: dict[str, dict] = {}
        self._lock = threading.Lock()

    def _release(self, port: int) -> None:
        """Only one browser sign-in can wait on a port, so a new attempt replaces older ones."""
        for flow in list(self._flows.values()):
            if flow.get("_port") == port and flow["status"] == "pending":
                flow.update(status="cancelled", message="A newer sign-in replaced this one")
                thread = flow.get("_thread")
                if thread:
                    thread.join(timeout=3)

    def start(self, port: int, path: str, exchange: Callable[[dict, str], dict],
              timeout: int = 600, **fields) -> tuple[str, dict]:
        """`exchange(flow, code)` turns the authorization code into the result dict."""
        with self._lock:
            self._release(port)
            return self._start(port, path, exchange, timeout, **fields)

    def _start(self, port: int, path: str, exchange: Callable[[dict, str], dict],
               timeout: int, **fields) -> tuple[str, dict]:
        flow_id = uuid.uuid4().hex
        flow = {"status": "pending", "state": secrets.token_urlsafe(24), "started": time.time(),
                "_port": port, **fields}
        self._flows[flow_id] = flow
        service = self.service

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                url = urlparse(self.path)
                if url.path != path:
                    self.send_response(404)
                    self.end_headers()
                    return
                query = parse_qs(url.query)
                ok = False
                if query.get("state", [""])[0] != flow["state"]:
                    flow.update(status="error", message="The sign-in link did not match; try again")
                elif "error" in query:
                    reason = query.get("error_description", query["error"])[0]
                    flow.update(status="denied", message="Sign-in was cancelled"
                                if reason == "access_denied" else reason)
                else:
                    try:
                        flow["result"] = exchange(flow, query.get("code", [""])[0])
                        flow["status"] = "done"
                        ok = True
                    except Exception as exc:
                        flow.update(status="error", message=str(exc))
                page = _DONE_PAGE.format(
                    title=f"RabShoot is connected to {service}" if ok else f"{service} sign-in failed",
                    body="You can close this tab and return to RabShoot." if ok
                    else html.escape(flow.get("message", "")))
                body = page.encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        server = None
        for attempt in range(6):
            try:
                server = HTTPServer(("127.0.0.1", port), Handler)
                break
            except OSError as exc:
                if attempt == 5:
                    self._flows.pop(flow_id, None)
                    raise RuntimeError(
                        f"Another program is using port {port}, which {service} sign-in needs. "
                        "If RabShoot is open twice or an old copy is still running, quit it from the "
                        "tray icon (or restart the computer) and try again.") from exc
                time.sleep(0.5)
        server.timeout = 1

        def serve():
            deadline = time.time() + timeout
            while flow["status"] == "pending" and time.time() < deadline:
                server.handle_request()
            if flow["status"] == "pending":
                flow.update(status="expired", message="The sign-in took too long; try again")
            server.server_close()

        flow["_thread"] = threading.Thread(target=serve, daemon=True)
        flow["_thread"].start()
        return flow_id, flow

    def status(self, flow_id: str) -> dict:
        flow = self._flows.get(flow_id)
        if not flow:
            return {"status": "error", "message": "Unknown sign-in session"}
        out = {"status": flow["status"], "message": flow.get("message", "")}
        if flow["status"] == "done":
            out.update(flow["result"])
        if flow["status"] != "pending":
            self._flows.pop(flow_id, None)
        return out
