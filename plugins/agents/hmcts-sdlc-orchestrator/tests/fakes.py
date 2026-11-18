"""In-process fakes on ``http.server``: a token endpoint and an ingest, both scripted.

Each fake binds ``127.0.0.1:0``, records every request (method, path, headers,
raw body) and answers from a per-path reply queue, falling back to a per-path
default. Tokens are built at run time; nothing here is a real value.
"""
import json
import socket
import threading
import urllib.parse
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Deque, Dict, List, NamedTuple, Optional, Tuple

import pytest

DEVICECODE_PATH = "/oauth2/v2.0/devicecode"
TOKEN_PATH = "/oauth2/v2.0/token"
BATCHES_PATH = "/v1/batches"
ME_PATH = "/v1/me"

Reply = Tuple[int, object]
_PROXY_VARS = ("http_proxy", "HTTP_PROXY", "https_proxy", "HTTPS_PROXY", "all_proxy", "ALL_PROXY")


def make_token(prefix: str) -> str:
    """A fake token, built at run time."""
    return prefix + "-" + prefix[0] * 40


def closed_port() -> int:
    """A loopback port that was free a moment ago and has no listener (connection refused)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class Captured(NamedTuple):
    method: str
    path: str
    headers: Any  # http.client.HTTPMessage: case-insensitive lookup
    body: bytes

    def form(self) -> Dict[str, str]:
        return {k: v[0] for k, v in urllib.parse.parse_qs(self.body.decode("utf-8")).items()}


class FakeServer:
    """A scripted HTTP server on 127.0.0.1:0."""

    def __init__(self) -> None:
        self.requests: List[Captured] = []
        self._queues: Dict[str, Deque[Reply]] = {}
        self._defaults: Dict[str, Reply] = {}
        self._lock = threading.Lock()
        fake = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def _serve(self) -> None:
                length = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(length) if length else b""
                path = self.path.split("?", 1)[0]
                status, payload = fake._next(Captured(self.command, path, self.headers, body))
                data = b"" if payload is None else json.dumps(payload).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(data)
                self.close_connection = True

            do_GET = _serve
            do_POST = _serve

            def log_message(self, fmt, *args) -> None:  # keep stderr quiet
                return None

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._server.daemon_threads = True
        self._thread = threading.Thread(target=self._server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
        self._thread.start()

    @property
    def url(self) -> str:
        return "http://127.0.0.1:%d" % self._server.server_address[1]

    def script(self, path: str, *replies: Reply) -> None:
        """Queue replies for ``path``; each request takes the next one."""
        with self._lock:
            self._queues.setdefault(path, deque()).extend(replies)

    def default(self, path: str, reply: Reply) -> None:
        """The reply for ``path`` once its queue is empty."""
        with self._lock:
            self._defaults[path] = reply

    def calls(self, path: str) -> List[Captured]:
        with self._lock:
            return [r for r in self.requests if r.path == path]

    def _next(self, captured: Captured) -> Reply:
        with self._lock:
            self.requests.append(captured)
            queue = self._queues.get(captured.path)
            if queue:
                return queue.popleft()
            return self._defaults.get(captured.path, (404, {"error": "not_found"}))

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(5)


def token_reply(access: Optional[str] = None, refresh: Optional[str] = None, expires_in: int = 3600) -> Reply:
    """A 200 token answer as the identity platform sends it."""
    return 200, {
        "token_type": "Bearer",
        "expires_in": expires_in,
        "access_token": access or make_token("acc"),
        "refresh_token": refresh or make_token("ref"),
    }


def oauth_error(word: str) -> Reply:
    """A 400 OAuth error answer (``authorization_pending``, ``slow_down`` ...)."""
    return 400, {"error": word}


def _no_proxy(monkeypatch) -> None:
    for name in _PROXY_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("NO_PROXY", "127.0.0.1")
    monkeypatch.setenv("no_proxy", "127.0.0.1")


@pytest.fixture
def fake_auth(monkeypatch):
    _no_proxy(monkeypatch)
    server = FakeServer()
    try:
        yield server
    finally:
        server.close()


@pytest.fixture
def fake_ingest(monkeypatch):
    _no_proxy(monkeypatch)
    server = FakeServer()
    server.default(BATCHES_PATH, (200, {"accepted": []}))
    try:
        yield server
    finally:
        server.close()
