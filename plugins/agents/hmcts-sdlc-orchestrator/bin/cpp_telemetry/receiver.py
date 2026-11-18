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

Exports, hooks and events get ``503`` while the spool is full or the ingest has
refused this developer (``state.rejected_until`` in the future). Anything else is
``404``. Nothing about a request is written to stderr; log lines carry counts and
error types only.
"""
from __future__ import annotations

import json
import threading
import time
import zlib
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Dict, List, Optional, Tuple

from . import log, scrub
from .config import Config
from .spool import Spool, valid_session_id

MAX_BODY_BYTES = 64 * 1024 * 1024
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
    """The scrub identity, built once from the first ``user.email`` seen.

    Until an export carries ``user.email`` the identity has no email literal; the
    first one seen is kept for the life of the process.
    """

    def __init__(self, build: Callable[[Optional[str]], scrub.Identity] = scrub.identity_from_environment) -> None:
        self._build = build
        self._lock = threading.Lock()
        self._ident: Optional[scrub.Identity] = None
        self._has_email = False

    def __call__(self, payload: Any) -> scrub.Identity:
        with self._lock:
            if not self._has_email:
                email = scrub.first_user_email(payload) if isinstance(payload, (dict, list)) else None
                if email:
                    self._ident = self._build(email)
                    self._has_email = True
                elif self._ident is None:
                    self._ident = self._build(None)
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


def _gunzip(raw: bytes) -> bytes:
    """Decompress every gzip member, refusing output beyond MAX_BODY_BYTES."""
    out = bytearray()
    data = raw
    while data:
        engine = zlib.decompressobj(16 + zlib.MAX_WBITS)
        try:
            out += engine.decompress(data, MAX_BODY_BYTES + 1 - len(out))
        except zlib.error:
            raise _HttpError(400)
        if len(out) > MAX_BODY_BYTES or engine.unconsumed_tail:
            raise _HttpError(413)
        if not engine.eof:
            raise _HttpError(400)
        data = engine.unused_data
    return bytes(out)


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    receiver: "Receiver"


class _Handler(BaseHTTPRequestHandler):
    server: _Server
    server_version = "cpp-telemetry"
    sys_version = ""

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

    def _read_chunked(self) -> bytes:
        out = bytearray()
        while True:
            line = self.rfile.readline(1024)
            try:
                size = int(line.split(b";", 1)[0].strip(), 16)
            except ValueError:
                raise _HttpError(400)
            if size == 0:
                while self.rfile.readline(1024) not in (b"\r\n", b"\n", b""):
                    pass  # trailers
                return bytes(out)
            if size < 0 or len(out) + size > MAX_BODY_BYTES:
                raise _HttpError(413)
            chunk = self.rfile.read(size)
            if len(chunk) != size:
                raise _HttpError(400)
            out += chunk
            self.rfile.readline(1024)

    def _body(self) -> bytes:
        if "chunked" in self.headers.get("Transfer-Encoding", "").lower():
            raw = self._read_chunked()
        else:
            try:
                length = int(self.headers.get("Content-Length", "0") or "0")
            except ValueError:
                raise _HttpError(400)
            if length < 0:
                raise _HttpError(400)
            if length > MAX_BODY_BYTES:
                raise _HttpError(413)
            raw = self.rfile.read(length)
        encoding = self.headers.get("Content-Encoding", "").strip().lower()
        if encoding == "gzip":
            return _gunzip(raw)
        if encoding not in ("", "identity"):
            raise _HttpError(415)
        return raw

    def _json(self) -> dict:
        try:
            data = json.loads(self._body().decode("utf-8"), parse_constant=_reject_constant)
        except (UnicodeDecodeError, ValueError, RecursionError):
            raise _HttpError(400)
        if not isinstance(data, dict):
            raise _HttpError(400)
        return data

    # -------------------------------------------------------------- verbs

    def do_GET(self) -> None:  # noqa: N802 - stdlib naming
        if self.path.split("?", 1)[0] == "/healthz":
            self._reply(200, self.server.receiver.health())
        else:
            self._reply(404)

    def do_POST(self) -> None:  # noqa: N802
        receiver = self.server.receiver
        path = self.path.split("?", 1)[0]
        try:
            if path in EXPORT_PATHS:
                receiver.gate()
                status, body = receiver.handle_export(EXPORT_PATHS[path], self._json())
            elif path == "/hook":
                receiver.gate()
                status, body = receiver.handle_hook(self._json())
            elif path == "/event":
                receiver.gate()
                status, body = receiver.handle_event(self._json())
            elif path == "/flush":
                status, body = 200, {"closed": receiver.flush()}
            elif path == "/shutdown":
                self._reply(200, {"closed": receiver.flush()})
                receiver.shutdown_soon()
                return
            else:
                status, body = 404, {}
        except _HttpError as exc:
            status, body = exc.status, {}
        self._reply(status, body)

    def _not_found(self) -> None:
        self._reply(404)

    do_PUT = do_DELETE = do_PATCH = do_OPTIONS = do_HEAD = _not_found  # noqa: N815


class Receiver:
    """The HTTP receiver; binds 127.0.0.1 at construction, serves until shut down."""

    def __init__(
        self,
        cfg: Config,
        spool: Spool,
        ident_provider: Callable[[Any], scrub.Identity],
        version: str,
        on_hook: Callable[[dict], List[dict]],
        on_event: Callable[[dict], None],
        state: ForwarderState,
        *,
        port: Optional[int] = None,
        start_ts: Optional[float] = None,
        on_shutdown: Optional[Callable[[], None]] = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
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
        self._server = _Server(("127.0.0.1", cfg.port if port is None else port), _Handler)
        self._server.receiver = self

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

    def health(self) -> dict:
        return {"status": "ok", "version": self._version, "port": self.port}

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

    def handle_export(self, signal: str, payload: dict) -> Tuple[int, dict]:
        ident = self._ident_provider(payload)
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
        scrubbed = {"signal": "event", "payload": scrub.scrub_values(payload, self._ident_provider(None))}
        self._append(self._session(scrubbed["payload"]), scrubbed)
        try:
            self._on_event(scrubbed)
        except Exception as exc:  # noqa: BLE001
            self._logger.error("event handler failed: %s", type(exc).__name__)
        return 200, {}

    def flush(self) -> int:
        return len(self._spool.close_all())
