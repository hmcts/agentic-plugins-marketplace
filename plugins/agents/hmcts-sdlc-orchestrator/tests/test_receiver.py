import copy
import gzip
import json
import socket
import threading
import time
from pathlib import Path

import pytest

from cpp_telemetry import PLUGIN_VERSION, receiver, scrub, spool
from cpp_telemetry.config import Config
from tests.helpers_net import free_port_run, post_json, request

FIXTURES = Path(__file__).resolve().parent / "fixtures"
START_TS = 1_800_000_000
IDENT_FIELDS = dict(username="devuser", home="/home/devuser", hostname="laptop-01")


def _fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _invented_identity(email):
    return scrub.Identity(email=email or "", **IDENT_FIELDS)


class Harness:
    """An in-process receiver on a free loopback port with the invented identity."""

    def __init__(self, tmp_path, on_hook=None):
        self.data = tmp_path
        self.cfg = Config(port=free_port_run(1))
        self.spool = spool.Spool(tmp_path, self.cfg)
        self.state = receiver.ForwarderState()
        self.built = []
        self.hooks = []
        self.events = []
        self.shut = threading.Event()

        def build(email):
            self.built.append(email)
            return _invented_identity(email)

        def default_on_hook(hook):
            self.hooks.append(hook)
            return []

        self.receiver = receiver.Receiver(
            self.cfg, self.spool, receiver.IdentityProvider(build), PLUGIN_VERSION,
            on_hook or default_on_hook, self.events.append, self.state,
            start_ts=START_TS, on_shutdown=self.shut.set,
        )
        self.port = self.receiver.port
        self.thread = threading.Thread(target=self.receiver.serve_forever, daemon=True)
        self.thread.start()

    def close(self):
        self.receiver.close()
        self.thread.join(5)
        assert not self.thread.is_alive()

    def batches(self):
        """{session_id: [events]} of every closed batch, after closing all open ones."""
        self.spool.close_all()
        found = {}
        for path in self.spool.closed_batches_oldest_first():
            with gzip.open(str(path), "rt", encoding="utf-8") as fh:
                batch = json.load(fh)
            found.setdefault(batch["session_id"], []).extend(batch["events"])
        return found


@pytest.fixture
def harness(tmp_path):
    h = Harness(tmp_path)
    yield h
    h.close()


def test_healthz_reports_version_and_port(harness):
    assert request(harness.port, "GET", "/healthz") == (200, {"status": "ok", "version": "1.1.0", "port": harness.port})
    assert harness.receiver.server_address[0] == "127.0.0.1"


def test_logs_export_is_scrubbed_and_spooled(harness):
    status, body = post_json(harness.port, "/v1/logs", _fixture("otlp-logs-small.json"))
    assert (status, body) == (200, {})
    batches = harness.batches()
    assert list(batches) == ["session-a"]
    [event] = batches["session-a"]
    assert event["signal"] == "logs"
    dumped = json.dumps(event)
    for literal in ("devuser@example.invalid", "/home/devuser", "laptop-01", "user.email", "host.name",
                    "user.account_uuid", "organization.id", "vcs.repository.url.full"):
        assert literal not in dumped, literal
    assert "open ~/repo/app.py on [REDACTED:self]" in dumped
    assert "session-a" in dumped
    # The identity is built once, from the first user.email seen.
    post_json(harness.port, "/v1/logs", _fixture("otlp-logs-small.json"))
    assert harness.built == ["devuser@example.invalid"]


def _logs_record(session=None, body="r"):
    attributes = [{"key": "event.name", "value": {"stringValue": "user_prompt"}}]
    if session is not None:
        attributes.append({"key": "session.id", "value": {"stringValue": session}})
    return {"body": {"stringValue": body}, "attributes": attributes}


def test_export_with_two_sessions_splits_into_two_batches(harness):
    payload = _fixture("otlp-logs-small.json")
    second = copy.deepcopy(payload["resourceLogs"][0]["scopeLogs"][0]["logRecords"][1])
    for attribute in second["attributes"]:
        if attribute["key"] == "session.id":
            attribute["value"]["stringValue"] = "session-b"
    payload["resourceLogs"][0]["scopeLogs"][0]["logRecords"].insert(1, second)
    assert post_json(harness.port, "/v1/logs", payload)[0] == 200
    batches = harness.batches()
    assert sorted(batches) == ["session-a", "session-b"]
    for session_id, events in batches.items():
        [event] = events
        resource = event["payload"]["resourceLogs"][0]
        scope = resource["scopeLogs"][0]
        assert scope["scope"]["name"] == "com.example.telemetry"
        assert {"key": "service.name", "value": {"stringValue": "claude-code"}} in resource["resource"]["attributes"]
        sessions = {a["value"]["stringValue"] for r in scope["logRecords"] for a in r["attributes"]
                    if a["key"] == "session.id"}
        assert sessions == {session_id}
    assert len(batches["session-a"][0]["payload"]["resourceLogs"][0]["scopeLogs"][0]["logRecords"]) == 3
    assert len(batches["session-b"][0]["payload"]["resourceLogs"][0]["scopeLogs"][0]["logRecords"]) == 1


def test_resource_session_and_nosession_fallbacks(harness):
    payload = {"resourceLogs": [
        {"resource": {"attributes": [{"key": "session.id", "value": {"stringValue": "session-r"}}]},
         "scopeLogs": [{"logRecords": [_logs_record(), _logs_record("session-x")]}]},
        {"resource": {"attributes": []}, "scopeLogs": [{"logRecords": [_logs_record(), _logs_record("../bad")]}]},
    ]}
    assert post_json(harness.port, "/v1/logs", payload)[0] == 200
    batches = harness.batches()
    nosession = "nosession-%d" % START_TS
    assert sorted(batches) == sorted(["session-r", "session-x", nosession])
    assert len(batches[nosession][0]["payload"]["resourceLogs"][0]["scopeLogs"][0]["logRecords"]) == 2


def test_metrics_split_by_data_point_and_traces_by_span(harness):
    metrics = _fixture("otlp-metrics-small.json")
    metric = metrics["resourceMetrics"][0]["scopeMetrics"][0]["metrics"][0]
    point = copy.deepcopy(metric["sum"]["dataPoints"][0])
    point["attributes"][0]["value"]["stringValue"] = "session-b"
    metric["sum"]["dataPoints"].append(point)
    traces = _fixture("otlp-traces-small.json")
    span = copy.deepcopy(traces["resourceSpans"][0]["scopeSpans"][0]["spans"][0])
    span["attributes"][0]["value"]["stringValue"] = "session-b"
    traces["resourceSpans"][0]["scopeSpans"][0]["spans"].append(span)
    assert post_json(harness.port, "/v1/metrics", metrics)[0] == 200
    assert post_json(harness.port, "/v1/traces", traces)[0] == 200
    batches = harness.batches()
    b_events = {e["signal"]: e["payload"] for e in batches["session-b"]}
    assert set(b_events) == {"metrics", "traces"}
    [b_metric] = b_events["metrics"]["resourceMetrics"][0]["scopeMetrics"][0]["metrics"]
    assert b_metric["name"] == "claude_code.token.usage" and b_metric["sum"]["isMonotonic"] is True
    assert len(b_metric["sum"]["dataPoints"]) == 1
    assert len(b_events["traces"]["resourceSpans"][0]["scopeSpans"][0]["spans"]) == 1
    a_metrics = [e for e in batches["session-a"] if e["signal"] == "metrics"][0]["payload"]
    a_names = [m["name"] for m in a_metrics["resourceMetrics"][0]["scopeMetrics"][0]["metrics"]]
    assert "claude_code.token.usage" in a_names
    assert "devuser@example.invalid" not in json.dumps(batches)


def test_gzip_export_accepted(harness):
    assert post_json(harness.port, "/v1/logs", _fixture("otlp-logs-small.json"), gzipped=True) == (200, {})
    assert list(harness.batches()) == ["session-a"]


def test_chunked_export_accepted(harness):
    body = json.dumps(_fixture("otlp-logs-small.json")).encode("utf-8")
    pieces = [body[i:i + 500] for i in range(0, len(body), 500)]
    chunks = b"".join(b"%x\r\n" % len(piece) + piece + b"\r\n" for piece in pieces)
    raw = (b"POST /v1/logs HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Type: application/json\r\n"
           b"Transfer-Encoding: chunked\r\nConnection: close\r\n\r\n" + chunks + b"0\r\n\r\n")
    reply = b""
    with socket.create_connection(("127.0.0.1", harness.port), timeout=5) as sock:
        sock.sendall(raw)
        while True:
            data = sock.recv(65536)
            if not data:
                break
            reply += data
    assert reply.split(b"\r\n", 1)[0].endswith(b"200 OK")
    assert list(harness.batches()) == ["session-a"]


def test_503_when_spool_full(harness, monkeypatch):
    monkeypatch.setattr(harness.spool, "is_full", lambda: True)
    assert post_json(harness.port, "/v1/logs", _fixture("otlp-logs-small.json"))[0] == 503
    assert post_json(harness.port, "/hook", {"hook_event_name": "Stop"})[0] == 503
    assert harness.hooks == []
    monkeypatch.setattr(harness.spool, "is_full", lambda: False)
    harness.state.rejected_until = time.time() + 60
    assert post_json(harness.port, "/v1/logs", _fixture("otlp-logs-small.json"))[0] == 503
    assert post_json(harness.port, "/event", {"signal": "event", "payload": {"name": "x"}})[0] == 503
    harness.state.rejected_until = time.time() - 1
    assert post_json(harness.port, "/v1/logs", _fixture("otlp-logs-small.json"))[0] == 200
    assert list(harness.batches()) == ["session-a"]


def test_hook_post_calls_on_hook(tmp_path):
    seen = []
    # A username inside a structural key: the raw hook JSON must reach on_hook untouched.
    hook = {"hook_event_name": "Stop", "session_id": "33333333-3333-3333-3333-333333333333",
            "cwd": "/home/devuser/repo", "tool": {"devuser": "laptop-01"}}

    def on_hook(raw):
        seen.append(raw)
        return [{"signal": "hook", "payload": {"name": "turn", "session_id": raw["session_id"], "seq": 1}},
                {"signal": "hook", "payload": {"name": "orphan"}}]

    h = Harness(tmp_path, on_hook=on_hook)
    try:
        assert post_json(h.port, "/hook", hook) == (200, {})
        assert seen == [hook]
        batches = h.batches()
    finally:
        h.close()
    assert batches["33333333-3333-3333-3333-333333333333"][0]["payload"] == {
        "name": "turn", "session_id": "33333333-3333-3333-3333-333333333333", "seq": 1}
    assert batches["nosession-%d" % START_TS][0]["payload"] == {"name": "orphan"}


def test_event_post_scrubs_values_only_and_calls_on_event(harness):
    payload = {"name": "git", "branch": "devuser/feature", "remote": "origin", "repo": "repo",
               "session_id": "sess-devuser-01", "user.email": "devuser@example.invalid"}
    assert post_json(harness.port, "/event", {"signal": "event", "payload": payload}) == (200, {})
    expected = {"name": "git", "branch": "[REDACTED:self]/feature", "remote": "origin", "repo": "repo",
                "session_id": "sess-devuser-01"}
    assert harness.events == [{"signal": "event", "payload": expected}]
    assert harness.batches()["sess-devuser-01"][0]["payload"] == expected
    assert post_json(harness.port, "/event", {"signal": "logs", "payload": {}})[0] == 400


def test_flush_closes_batches_and_counts(harness):
    post_json(harness.port, "/v1/logs", _fixture("otlp-logs-small.json"))
    assert post_json(harness.port, "/flush", {}) == (200, {"closed": 1})
    assert len(harness.spool.closed_batches_oldest_first()) == 1


def test_bad_requests_and_unknown_routes(harness):
    assert request(harness.port, "POST", "/v1/logs", body=b"{not json")[0] == 400
    assert request(harness.port, "POST", "/v1/logs", body=b"[]")[0] == 400
    assert request(harness.port, "POST", "/v1/logs", body=b"x", headers={"Content-Encoding": "br"})[0] == 415
    assert request(harness.port, "POST", "/v1/logs", body=b"not gzip", headers={"Content-Encoding": "gzip"})[0] == 400
    assert request(harness.port, "GET", "/v1/logs")[0] == 404
    assert request(harness.port, "POST", "/nothing", body=b"{}")[0] == 404
    assert request(harness.port, "PUT", "/healthz", body=b"{}")[0] == 404
    assert request(harness.port, "GET", "/healthz?x=1")[0] == 200
    log_file = harness.data / "forwarder.log"
    assert not log_file.exists() or "devuser" not in log_file.read_text()


def test_shutdown_drains_open_batches(harness):
    post_json(harness.port, "/v1/logs", _fixture("otlp-logs-small.json"))
    assert list((harness.data / "spool" / "session-a").glob("*.open.jsonl"))
    assert post_json(harness.port, "/shutdown", {}) == (200, {"closed": 1})
    assert harness.shut.wait(5)
    harness.thread.join(5)
    assert not harness.thread.is_alive()
    assert not list((harness.data / "spool" / "session-a").glob("*.open.jsonl"))
    assert len(harness.spool.closed_batches_oldest_first()) == 1
    with pytest.raises(OSError):
        request(harness.port, "GET", "/healthz", timeout=1)


def test_identity_provider_keeps_the_first_email():
    built = []
    provider = receiver.IdentityProvider(lambda email: built.append(email) or _invented_identity(email))
    assert provider({"resourceLogs": []}).email == ""
    assert provider(_fixture("otlp-logs-small.json")).email == "devuser@example.invalid"
    other = json.loads(json.dumps(_fixture("otlp-logs-small.json")).replace("devuser@", "other@"))
    assert provider(other).email == "devuser@example.invalid"
    assert built == [None, "devuser@example.invalid"]
