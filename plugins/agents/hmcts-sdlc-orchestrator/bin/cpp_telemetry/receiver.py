"""The forwarder's local HTTP receiver on 127.0.0.1.

Routes:

- ``POST /v1/logs``, ``/v1/metrics``, ``/v1/traces`` -- an OTLP http/json export
  (``Content-Encoding: gzip`` and chunked bodies accepted). The export is split by
  ``session.id`` -- read from the log record, data point or span attributes, else
  the resource attributes, else the pseudo-session ``nosession-<start ts>`` -- into
  one sub-payload per session that keeps the OTLP envelope structure. Each
  sub-payload is scrubbed and appended to that session's open batch. ``200 {}``.
- ``POST /hook`` -- the hook's stdin JSON, passed untouched to ``on_hook``; the
  envelopes it returns are appended as given (the snapshot module builds them with
  fixed keys and scrubs their values). ``200 {}``.
- ``POST /event`` -- one ``{"signal": "event", "payload": {...}}`` envelope; its
  string values are scrubbed (keys kept), it is appended and passed to ``on_event``.
- ``POST /flush`` -- close every open batch; ``200 {"closed": n}``.
- ``POST /shutdown`` -- close every open batch, reply ``200 {"closed": n}``, then
  stop serving (from another thread).
- ``GET /healthz`` -- ``200 {"status": "ok", "version": <plugin version>, "port": <port>}``.

Every request must name ``Host: 127.0.0.1:<port>`` or ``localhost:<port>`` (else
``421``) and carry no ``Origin`` header (else ``403``): a web page or a DNS-rebound
name cannot reach the receiver. Every POST needs ``Content-Type: application/json``
(else ``415``). The control routes ``/hook``, ``/event``, ``/flush`` and ``/shutdown``
also need ``X-Cpp-Telemetry-Token`` equal to ``<data>/token`` (else ``403``); the OTLP
routes stay token-less because the exporter cannot add a header.
``GET /healthz?nonce=<hex>`` adds ``"proof": HMAC-SHA256(token, nonce)`` so a client
holding the token can tell this forwarder from a listener that only echoes the body.

Exports, hooks and events get ``503`` while the spool is full or the ingest has
refused this developer (``state.rejected_until`` in the future). Anything else is
``404``. Body caps (compressed and decompressed): OTLP 32 MiB, ``/hook`` 8 MiB,
``/event``, ``/flush`` and ``/shutdown`` 1 MiB; an oversized body is drained up to the
cap and answered ``413`` (one count-only log line). At most 4 bodies are handled at
once; ``/flush`` and ``/shutdown`` never wait for a slot. Nothing about a request is
written to stderr; log lines carry counts and error types only.

The healthz proof is bound to the port and version it reports, so a listener that
relays the nonce to the real forwarder and echoes its body cannot pass as ours.
"""
from __future__ import annotations

import dataclasses
import hashlib
import hmac
import json
import os
import re
import sys
import threading
import time
import zlib
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Dict, List, Optional, Tuple

from . import log, scrub
from .config import Config
from .spool import Spool, valid_session_id

OTLP_MAX_BYTES = 32 * 1024 * 1024
HOOK_MAX_BYTES = 8 * 1024 * 1024
CONTROL_MAX_BYTES = 1024 * 1024
MAX_TRAILER_LINES = 64
MAX_EMAILS = 8
HANDLER_SLOTS = 4
UNSLOTTED_PATHS = frozenset({"/flush", "/shutdown"})
SLOT_WAIT_S = 10.0
TOKEN_HEADER = "X-Cpp-Telemetry-Token"
CONTROL_PATHS = frozenset({"/hook", "/event", "/flush", "/shutdown"})
_NONCE_RE = re.compile(r"[0-9a-f]{16,128}")
_VERSION_RE = re.compile(r"[0-9A-Za-z._-]{1,32}")


def valid_version(version: Any) -> bool:
    """A version the healthz proof can carry: 1-32 ASCII characters from ``[0-9A-Za-z._-]``."""
    return isinstance(version, str) and _VERSION_RE.fullmatch(version) is not None


def healthz_proof(token: str, nonce: str, port: int, version: str) -> str:
    """HMAC-SHA256 of ``nonce|port|version`` under the data directory's token, hex."""
    message = "%s|%d|%s" % (nonce, port, version)
    return hmac.new(token.encode("ascii"), message.encode("utf-8"), hashlib.sha256).hexdigest()


def _body_cap(path: str) -> int:
    if path in EXPORT_PATHS:
        return OTLP_MAX_BYTES
    return HOOK_MAX_BYTES if path == "/hook" else CONTROL_MAX_BYTES


def claude_json_path() -> Path:
    """``$CLAUDE_CONFIG_DIR/.claude.json`` when set, else ``~/.claude.json``."""
    env = os.environ.get("CLAUDE_CONFIG_DIR")
    return (Path(env) if env else Path.home()) / ".claude.json"


def read_trusted_email() -> Optional[str]:
    """The signed-in account's email (``oauthAccount.emailAddress``); never logged, never written."""
    try:
        data = json.loads(claude_json_path().read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError, RecursionError):
        return None
    account = data.get("oauthAccount") if isinstance(data, dict) else None
    email = account.get("emailAddress") if isinstance(account, dict) else None
    return email if scrub.is_plausible_email(email) else None
EXPORT_PATHS = {"/v1/logs": "logs", "/v1/metrics": "metrics", "/v1/traces": "traces"}

# signal -> (resource list key, scope list key, record list key)
_LAYOUT = {
    "logs": ("resourceLogs", "scopeLogs", "logRecords"),
    "metrics": ("resourceMetrics", "scopeMetrics", "metrics"),
    "traces": ("resourceSpans", "scopeSpans", "spans"),
}
_SESSION_KEY = "session.id"


@dataclass
class ForwarderState:
    """State shared by the receiver, the upload loop and the hook handler."""

    rejected_until: float = 0.0
    last_ack: Optional[float] = None
    last_error: Optional[str] = None
    engine_version: Optional[str] = None


class IdentityProvider:
    """The scrub identity: the environment's literals, the trusted email and payload emails.

    The username, home and hostname are read once. ``trusted_email`` (from
    ``~/.claude.json``, read at forwarder start) always leads and is never evicted;
    each new plausible ``user.email`` found in a raw body (case-insensitive, up to
    ``MAX_EMAILS``) is added after it. The payload walk runs outside the lock and
    only when the raw body holds the bytes ``email`` (so a JSON-escaped key such as
    ``user\\u002eemail`` is still walked; the walk decides).
    """

    def __init__(self, build: Callable[[Optional[str]], scrub.Identity] = scrub.identity_from_environment,
                 trusted_email: Optional[str] = None) -> None:
        self._build = build
        self._trusted = trusted_email if scrub.is_plausible_email(trusted_email) else None
        self._lock = threading.Lock()
        self._base: Optional[scrub.Identity] = None
        self._emails: List[str] = []
        self._ident: Optional[scrub.Identity] = None

    def _compose(self) -> scrub.Identity:
        assert self._base is not None
        emails = ([self._trusted] if self._trusted else []) + self._emails
        if not emails:
            return self._base
        return dataclasses.replace(self._base, email=emails[0], other_emails=tuple(emails[1:]))

    def __call__(self, payload: Any = None, raw: Optional[bytes] = None) -> scrub.Identity:
        with self._lock:
            if self._base is None:
                self._base = self._build(None)
                self._ident = self._compose()
            room = len(self._emails) < MAX_EMAILS
        found: List[str] = []
        if room and raw is not None and b"email" in raw and isinstance(payload, (dict, list)):
            found = scrub.user_emails(payload, MAX_EMAILS + 1)
        with self._lock:
            known = {email.lower() for email in self._emails}
            if self._trusted:
                known.add(self._trusted.lower())
            fresh = [email for email in found if email.lower() not in known]
            if fresh and len(self._emails) < MAX_EMAILS:
                self._emails.extend(fresh[:MAX_EMAILS - len(self._emails)])
                self._ident = self._compose()
            assert self._ident is not None
            return self._ident


# ---------------------------------------------------------------------- session split


def _session_of(node: Any) -> Optional[str]:
    """The ``session.id`` string attribute of a record or resource, when valid as a spool id."""
    if not isinstance(node, dict):
        return None
    attributes = node.get("attributes")
    if not isinstance(attributes, list):
        return None
    for item in attributes:
        if isinstance(item, dict) and item.get("key") == _SESSION_KEY:
            value = item.get("value")
            text = value.get("stringValue") if isinstance(value, dict) else None
            return text if valid_session_id(text) else None
    return None


def _metric_by_session(metric: Any, default: str) -> List[Tuple[str, Any]]:
    """Split one metric by its data points' sessions; each copy keeps the metric's other fields."""
    if isinstance(metric, dict):
        for kind, body in metric.items():
            if isinstance(body, dict) and isinstance(body.get("dataPoints"), list):
                groups: Dict[str, list] = {}
                for point in body["dataPoints"]:
                    groups.setdefault(_session_of(point) or default, []).append(point)
                if not groups:
                    return [(default, metric)]
                return [(session, dict(metric, **{kind: dict(body, dataPoints=points)}))
                        for session, points in groups.items()]
    return [(default, metric)]


def split_by_session(signal: str, payload: dict, fallback: str) -> Dict[str, dict]:
    """``{session_id: sub_payload}`` in first-seen order; each keeps the OTLP envelope shape."""
    top, scope_key, record_key = _LAYOUT[signal]
    resources = payload.get(top)
    if not isinstance(resources, list):
        return {fallback: payload}
    rest = {key: value for key, value in payload.items() if key != top}
    out: Dict[str, dict] = {}

    def add(session: str, resource: Any) -> None:
        out.setdefault(session, dict(rest, **{top: []}))[top].append(resource)

    for resource in resources:
        if not isinstance(resource, dict):
            add(fallback, resource)
            continue
        default = _session_of(resource.get("resource")) or fallback
        scopes = resource.get(scope_key)
        if not isinstance(scopes, list):
            add(default, resource)
            continue
        per_session: Dict[str, list] = {}
        for scope in scopes:
            records = scope.get(record_key) if isinstance(scope, dict) else None
            if not isinstance(records, list):
                per_session.setdefault(default, []).append(scope)
                continue
            groups: Dict[str, list] = {}
            for record in records:
                if signal == "metrics":
                    for session, part in _metric_by_session(record, default):
                        groups.setdefault(session, []).append(part)
                else:
                    groups.setdefault(_session_of(record) or default, []).append(record)
            for session, kept in groups.items():
                per_session.setdefault(session, []).append(dict(scope, **{record_key: kept}))
        if not per_session:
            per_session[default] = []
        for session, kept_scopes in per_session.items():
            add(session, dict(resource, **{scope_key: kept_scopes}))
    return out


# ---------------------------------------------------------------------- HTTP


class _HttpError(Exception):
    def __init__(self, status: int) -> None:
        super().__init__(status)
        self.status = status


def _reject_constant(name: str) -> Any:
    raise ValueError("non-finite number")


def _gunzip(raw: bytes, cap: int) -> bytes:
    """Decompress every gzip member, refusing output beyond ``cap``."""
    out = bytearray()
    data = raw
    while data:
        engine = zlib.decompressobj(16 + zlib.MAX_WBITS)
        try:
            out += engine.decompress(data, cap + 1 - len(out))
        except zlib.error:
            raise _HttpError(400)
        if len(out) > cap or engine.unconsumed_tail:
            raise _HttpError(413)
        if not engine.eof:
            raise _HttpError(400)
        data = engine.unused_data
    return bytes(out)


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    receiver: "Receiver"
    slots: threading.BoundedSemaphore

    def handle_error(self, request: Any, client_address: Any) -> None:
        """Log the exception type and reply 500; nothing goes to stderr."""
        exc_type = sys.exc_info()[0]
        self.receiver.log_error_type("request failed", exc_type.__name__ if exc_type else "unknown")
        try:
            request.sendall(b"HTTP/1.0 500 Internal Server Error\r\nContent-Type: application/json\r\n"
                            b"Content-Length: 2\r\n\r\n{}")
        except OSError:
            pass


class _Handler(BaseHTTPRequestHandler):
    server: _Server
    server_version = "cpp-telemetry"
    sys_version = ""
    timeout = 10

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - stdlib signature
        """No request lines on stderr or in the log."""

    # -------------------------------------------------------------- plumbing

    def _reply(self, status: int, body: Optional[dict] = None) -> None:
        data = json.dumps({} if body is None else body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def _drain(self, count: int) -> None:
        while count > 0:
            data = self.rfile.read(min(count, 65536))
            if not data:
                return
            count -= len(data)

    def _too_large(self, path: str, size: int) -> _HttpError:
        self.server.receiver.log_413(path, size)
        return _HttpError(413)

    def _read_chunked(self, path: str, cap: int) -> bytes:
        out = bytearray()
        while True:
            line = self.rfile.readline(1024)
            try:
                size = int(line.split(b";", 1)[0].strip(), 16)
            except ValueError:
                raise _HttpError(400)
            if size == 0:
                for _ in range(MAX_TRAILER_LINES):
                    if self.rfile.readline(1024) in (b"\r\n", b"\n", b""):
                        return bytes(out)
                raise _HttpError(400)
            if size < 0:
                raise _HttpError(400)
            if len(out) + size > cap:
                self._drain(cap - len(out))
                raise self._too_large(path, len(out) + size)
            chunk = self.rfile.read(size)
            if len(chunk) != size:
                raise _HttpError(400)
            out += chunk
            self.rfile.readline(1024)

    def _body(self, path: str) -> bytes:
        """The request body, decompressed; 413 past the route's cap (drained up to the cap first)."""
        cap = _body_cap(path)
        if "chunked" in self.headers.get("Transfer-Encoding", "").lower():
            raw = self._read_chunked(path, cap)
        else:
            try:
                length = int(self.headers.get("Content-Length", "0") or "0")
            except ValueError:
                raise _HttpError(400)
            if length < 0:
                raise _HttpError(400)
            if length > cap:
                self._drain(cap)
                raise self._too_large(path, length)
            raw = self.rfile.read(length)
        encoding = self.headers.get("Content-Encoding", "").strip().lower()
        if encoding == "gzip":
            try:
                return _gunzip(raw, cap)
            except _HttpError as exc:
                if exc.status == 413:
                    self.server.receiver.log_413(path, len(raw))
                raise
        if encoding not in ("", "identity"):
            raise _HttpError(415)
        return raw

    @staticmethod
    def _parse(raw: bytes) -> dict:
        try:
            data = json.loads(raw.decode("utf-8"), parse_constant=_reject_constant)
        except (UnicodeDecodeError, ValueError, RecursionError):
            raise _HttpError(400)
        if not isinstance(data, dict):
            raise _HttpError(400)
        return data

    def _guarded(self) -> bool:
        """Reply 421 for a foreign Host and 403 for any Origin; True when the request may go on."""
        port = self.server.receiver.port
        host = (self.headers.get("Host") or "").strip().lower()
        if host not in ("127.0.0.1:%d" % port, "localhost:%d" % port):
            self._reply(421)
            return False
        if self.headers.get("Origin") is not None:
            self._reply(403)
            return False
        return True

    def do_GET(self) -> None:  # noqa: N802 - stdlib naming
        if not self._guarded():
            return
        parts = urlsplit(self.path)
        if parts.path == "/healthz":
            nonce = parse_qs(parts.query).get("nonce", [""])[0]
            self._reply(200, self.server.receiver.health(nonce))
        else:
            self._reply(404)

    def do_POST(self) -> None:  # noqa: N802
        if not self._guarded():
            return
        receiver = self.server.receiver
        path = urlsplit(self.path).path
        if path not in EXPORT_PATHS and path not in CONTROL_PATHS:
            self._reply(404)
            return
        if self.headers.get_content_type() != "application/json":
            self._reply(415)
            return
        if path in CONTROL_PATHS and not receiver.token_ok(self.headers.get(TOKEN_HEADER)):
            self._reply(403)
            return
        slotted = path not in UNSLOTTED_PATHS
        if slotted and not self.server.slots.acquire(timeout=SLOT_WAIT_S):
            self._reply(503)
            return
        try:
            if path in EXPORT_PATHS:
                receiver.gate()
                raw = self._body(path)
                status, body = receiver.handle_export(EXPORT_PATHS[path], self._parse(raw), raw)
            elif path == "/hook":
                receiver.gate()
                status, body = receiver.handle_hook(self._parse(self._body(path)))
            elif path == "/event":
                receiver.gate()
                status, body = receiver.handle_event(self._parse(self._body(path)))
            elif path == "/flush":
                self._body(path)
                status, body = 200, {"closed": receiver.flush()}
            else:  # /shutdown
                self._body(path)
                self._reply(200, {"closed": receiver.flush()})
                receiver.shutdown_soon()
                return
        except _HttpError as exc:
            status, body = exc.status, {}
        finally:
            if slotted:
                self.server.slots.release()
        self._reply(status, body)

    def _not_found(self) -> None:
        if self._guarded():
            self._reply(404)

    do_PUT = do_DELETE = do_PATCH = do_OPTIONS = do_HEAD = _not_found  # noqa: N815


class Receiver:
    """The HTTP receiver; binds 127.0.0.1 at construction, serves until shut down."""

    def __init__(
        self,
        cfg: Config,
        spool: Spool,
        ident_provider: Callable[[Any, Optional[bytes]], scrub.Identity],
        version: str,
        on_hook: Callable[[dict], List[dict]],
        on_event: Callable[[dict], None],
        state: ForwarderState,
        *,
        port: Optional[int] = None,
        start_ts: Optional[float] = None,
        on_shutdown: Optional[Callable[[], None]] = None,
        clock: Callable[[], float] = time.time,
        token: Optional[str] = None,
    ) -> None:
        if not valid_version(version):
            raise ValueError("version must be 1-32 characters of [0-9A-Za-z._-]")
        self._cfg = cfg
        self._spool = spool
        self._ident_provider = ident_provider
        self._version = version
        self._on_hook = on_hook
        self._on_event = on_event
        self._state = state
        self._on_shutdown = on_shutdown
        self._clock = clock
        self._fallback = "nosession-%d" % int(clock() if start_ts is None else start_ts)
        self._logger = log.get_logger(spool.root.parent)
        self._guard = threading.Lock()
        self._serving = False
        self._closing = False
        self._closed = False
        self._token = token
        self._server = _Server(("127.0.0.1", cfg.port if port is None else port), _Handler)
        self._server.receiver = self
        self._server.slots = threading.BoundedSemaphore(HANDLER_SLOTS)

    @property
    def port(self) -> int:
        return int(self._server.server_address[1])

    @property
    def server_address(self) -> Tuple[str, int]:
        host, port = self._server.server_address[:2]
        return str(host), int(port)

    # -------------------------------------------------------------- lifecycle

    def serve_forever(self) -> None:
        with self._guard:
            if self._closing:
                return
            self._serving = True
        self._server.serve_forever(poll_interval=0.2)

    def close(self) -> None:
        """Stop serving (when serving) and close the socket; safe to call more than once."""
        with self._guard:
            self._closing = True
            serving, self._serving = self._serving, False
            closed, self._closed = self._closed, True
        if serving:
            self._server.shutdown()
        if not closed:
            self._server.server_close()

    def shutdown_soon(self) -> None:
        """Stop from another thread: a handler thread must not wait on its own server."""

        def stop() -> None:
            self.close()
            if self._on_shutdown is not None:
                self._on_shutdown()

        threading.Thread(target=stop, name="cpp-telemetry-shutdown", daemon=True).start()

    # -------------------------------------------------------------- handlers

    def health(self, nonce: str = "") -> dict:
        body: Dict[str, Any] = {"status": "ok", "version": self._version, "port": self.port}
        if self._token and _NONCE_RE.fullmatch(nonce or ""):
            body["proof"] = healthz_proof(self._token, nonce, self.port, self._version)
        return body

    def token_ok(self, presented: Optional[str]) -> bool:
        """True when the control token matches; always False when this receiver has none."""
        if not self._token or not presented:
            return False
        return hmac.compare_digest(presented.encode("utf-8", "replace"), self._token.encode("ascii"))

    def log_413(self, path: str, size: int) -> None:
        if path in EXPORT_PATHS:
            self._logger.warning("event=export_rejected_413 bytes=%d", size)
        else:
            self._logger.warning("event=request_rejected_413 route=%s bytes=%d", path, size)

    def log_error_type(self, what: str, type_name: str) -> None:
        self._logger.error("%s: %s", what, type_name)

    def gate(self) -> None:
        """503 while the developer is refused by the ingest or the spool is full."""
        if self._state.rejected_until > self._clock() or self._spool.is_full():
            raise _HttpError(503)

    def _session(self, payload: Any) -> str:
        session_id = payload.get("session_id") if isinstance(payload, dict) else None
        return session_id if valid_session_id(session_id) else self._fallback

    def _append(self, session_id: str, envelope: dict) -> None:
        try:
            self._spool.append(session_id, envelope)
        except OSError as exc:
            self._logger.error("spool append failed: %s", type(exc).__name__)
            raise _HttpError(503)

    def handle_export(self, signal: str, payload: dict, raw: Optional[bytes] = None) -> Tuple[int, dict]:
        ident = self._ident_provider(payload, raw)
        dropped = 0
        for session_id, sub_payload in split_by_session(signal, payload, self._fallback).items():
            try:
                scrubbed = scrub.scrub_payload(signal, sub_payload, ident)
            except scrub.TooManyKeys:
                dropped += 1
                continue
            self._append(session_id, {"signal": signal, "payload": scrubbed})
        if dropped:
            self._logger.warning("export: dropped %d %s sub-payload(s) over the key limit", dropped, signal)
        return 200, {}

    def handle_hook(self, hook: dict) -> Tuple[int, dict]:
        try:
            envelopes = self._on_hook(hook)
        except Exception as exc:  # noqa: BLE001 - a hook must never break the receiver
            self._logger.error("hook handler failed: %s", type(exc).__name__)
            return 500, {}
        for envelope in envelopes or []:
            if isinstance(envelope, dict):
                self._append(self._session(envelope.get("payload")), envelope)
        return 200, {}

    def handle_event(self, envelope: dict) -> Tuple[int, dict]:
        payload = envelope.get("payload")
        if envelope.get("signal", "event") != "event" or not isinstance(payload, dict):
            return 400, {}
        scrubbed = {"signal": "event", "payload": scrub.scrub_values(payload, self._ident_provider(None, None))}
        self._append(self._session(scrubbed["payload"]), scrubbed)
        try:
            self._on_event(scrubbed)
        except Exception as exc:  # noqa: BLE001
            self._logger.error("event handler failed: %s", type(exc).__name__)
        return 200, {}

    def flush(self) -> int:
        return len(self._spool.close_all())
