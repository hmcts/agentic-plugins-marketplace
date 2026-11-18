import gzip
import http.client
import json
import os
import signal
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from cpp_telemetry import PLUGIN_VERSION, cli, forwarder, lifecycle, receiver, spool
from cpp_telemetry.config import Config
from tests.helpers_net import free_port_run, post_json, request

HOLDER_CODE = "import time; time.sleep(60)"

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"
CONFIGURED = {
    "ingest_url": "http://127.0.0.1:18080",
    "tenant_id": "00000000-0000-0000-0000-000000000001",
    "client_id": "00000000-0000-0000-0000-000000000002",
    "api_app_id": "00000000-0000-0000-0000-000000000003",
}


def _cfg(base):
    return Config(port=base, port_scan=(base + 1, base + 9), **CONFIGURED)


def _write_override(data_dir, base):
    (Path(data_dir) / "override.json").write_text(
        json.dumps(dict(CONFIGURED, port=base, port_scan=[base + 1, base + 9])), encoding="utf-8")


def _a_dead_pid():
    proc = subprocess.Popen([sys.executable, "-B", "-c", "pass"])
    proc.wait()
    return proc.pid


@pytest.fixture
def holder():
    """A live process whose command line names cpp_telemetry, standing in for a running forwarder."""
    proc = subprocess.Popen([sys.executable, "-B", "-c", HOLDER_CODE, str(PLUGIN_ROOT / "bin" / "cpp_telemetry"),
                             "forwarder"])
    yield proc.pid
    proc.kill()
    proc.wait(5)


@pytest.fixture
def unrelated():
    """A live process whose command line does not name the forwarder (never the test's parent shell)."""
    proc = subprocess.Popen([sys.executable, "-B", "-c", HOLDER_CODE])
    yield proc.pid
    proc.kill()
    proc.wait(5)


def _token(data_dir):
    return lifecycle.ensure_token(data_dir)


class _Mimic(BaseHTTPRequestHandler):
    """Echoes a healthz body without a valid proof."""

    def do_GET(self):
        port = self.server.server_address[1]
        body = json.dumps({"status": "ok", "version": PLUGIN_VERSION, "port": port, "proof": "0" * 64}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


class _Foreign(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(404)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *args):
        pass


@pytest.fixture
def spawned(monkeypatch):
    """Track every forwarder process a test starts; the finaliser always stops it."""
    procs = []
    real = lifecycle._spawn

    def tracking(plugin_root, data_dir):
        proc = real(plugin_root, data_dir)
        procs.append((proc, Path(data_dir)))
        return proc

    monkeypatch.setattr(lifecycle, "_spawn", tracking)
    yield procs
    for proc, data in procs:
        if proc.poll() is None:
            try:
                port = lifecycle.read_port(data)
                if port is not None:
                    lifecycle._post(port, "/shutdown", data, timeout=1)
            except Exception:  # noqa: BLE001 - the kill below must always run
                pass
            try:
                proc.wait(5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(5)
        assert proc.poll() is not None


# ---------------------------------------------------------------- port and lock


def test_choose_port_skips_foreign_listener(tmp_path):
    # Free ports chosen at run time stand in for 4328/4329 so a real forwarder is never disturbed.
    base = free_port_run()
    foreign = ThreadingHTTPServer(("127.0.0.1", base), _Foreign)
    thread = threading.Thread(target=foreign.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    thread.start()
    try:
        assert lifecycle.choose_port(_cfg(base), tmp_path) == base + 1
    finally:
        foreign.shutdown()
        foreign.server_close()
        thread.join(5)
    assert (tmp_path / "port").read_text().strip() == str(base + 1)
    assert lifecycle.read_port(tmp_path) == base + 1
    assert lifecycle.choose_port(_cfg(base), tmp_path) == base


def test_choose_port_accepts_our_own_forwarder_and_fails_when_all_foreign(tmp_path):
    base = free_port_run()
    cfg = _cfg(base)
    ours = receiver.Receiver(cfg, spool.Spool(tmp_path, cfg), receiver.IdentityProvider(), "1.1.0",
                             lambda hook: [], lambda event: None, receiver.ForwarderState(), token=_token(tmp_path))
    thread = threading.Thread(target=ours.serve_forever, daemon=True)
    thread.start()
    try:
        assert lifecycle.choose_port(cfg, tmp_path) == base
    finally:
        ours.close()
        thread.join(5)
    servers = [ThreadingHTTPServer(("127.0.0.1", p), _Foreign) for p in range(base, base + 10)]
    threads = [threading.Thread(target=s.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
               for s in servers]
    for t in threads:
        t.start()
    try:
        with pytest.raises(lifecycle.NotStarted):
            lifecycle.choose_port(cfg, tmp_path)
    finally:
        for s in servers:
            s.shutdown()
            s.server_close()


def test_lock_holds_the_pid_and_a_stale_lock_is_taken_over(tmp_path, holder):
    lock = lifecycle.acquire_lock(tmp_path)
    assert lock is not None
    assert lifecycle.lock_path(tmp_path) == tmp_path / "forwarder.lock"
    assert (tmp_path / "forwarder.lock").read_text().strip() == str(os.getpid())
    lock.release()
    assert not (tmp_path / "forwarder.lock").exists()
    (tmp_path / "forwarder.lock").write_text("%d\n" % _a_dead_pid())
    assert not lifecycle.lock_held(tmp_path)
    taken = lifecycle.acquire_lock(tmp_path)
    assert taken is not None and lifecycle.read_lock_pid(tmp_path) == os.getpid()
    taken.release()
    (tmp_path / "forwarder.lock").write_text("%d\n" % holder)
    assert lifecycle.lock_held(tmp_path) and lifecycle.acquire_lock(tmp_path) is None


# ---------------------------------------------------------------- forwarder.run in-process


def test_forwarder_exits_0_when_a_live_pid_holds_the_lock(tmp_path, monkeypatch, holder):
    (tmp_path / "forwarder.lock").write_text("%d\n" % holder)
    assert lifecycle.lock_held(tmp_path)  # else run() would take the lock and never return
    reaped = []
    monkeypatch.setattr(spool.Spool, "reap_orphans", lambda self: reaped.append(1) or [])
    assert forwarder.run(_cfg(free_port_run()), tmp_path, PLUGIN_ROOT, PLUGIN_VERSION) == 0
    assert reaped == [] and not (tmp_path / "port").exists()
    assert (tmp_path / "forwarder.lock").read_text().strip() == str(holder)


def test_forwarder_takes_the_lock_before_reaping_and_exits_on_opt_out(tmp_path, monkeypatch):
    seen = []
    real = spool.Spool.reap_orphans

    def reap(self):
        seen.append(lifecycle.read_lock_pid(tmp_path))
        return real(self)

    monkeypatch.setattr(spool.Spool, "reap_orphans", reap)
    monkeypatch.setattr(forwarder, "LOOP_INTERVAL_S", 0.02)
    (tmp_path / "opt-out").write_text("")
    ticks = []
    assert forwarder.run(_cfg(free_port_run()), tmp_path, PLUGIN_ROOT, PLUGIN_VERSION, tick=ticks.append) == 0
    assert seen == [os.getpid()] and len(ticks) >= 1
    assert not (tmp_path / "forwarder.lock").exists()
    assert "opt-out" in (tmp_path / "forwarder.log").read_text()


def _signed_in(data_dir):
    from cpp_telemetry import auth
    from tests.fakes import make_token
    auth.TokenCache(data_dir).save(make_token("acc"), make_token("ref"), time.time() + 3600)


def _run_in_thread(base, data_dir, result):
    thread = threading.Thread(
        target=lambda: result.append(forwarder.run(_cfg(base), data_dir, PLUGIN_ROOT, PLUGIN_VERSION,
                                                   tick=lambda now: None)), daemon=True)
    thread.start()
    deadline = time.monotonic() + 5
    while lifecycle.healthz(base, data_dir) is None and time.monotonic() < deadline:
        time.sleep(0.02)
    return thread


def _spool_files(data_dir):
    return sorted(p.name for p in (Path(data_dir) / "spool").glob("*/*") if p.is_file())


def test_signed_out_opt_out_deletes_the_spool_and_exits(tmp_path, monkeypatch):
    monkeypatch.setattr(forwarder, "LOOP_INTERVAL_S", 0.02)
    base = free_port_run()
    result = []
    thread = _run_in_thread(base, tmp_path, result)
    try:
        assert post_json(base, "/v1/logs", json.loads((FIXTURES / "otlp-logs-small.json").read_text()))[0] == 200
        assert post_json(base, "/flush", {}, token=lifecycle.read_token(tmp_path))[0] == 200
        assert post_json(base, "/v1/logs", json.loads((FIXTURES / "otlp-logs-small.json").read_text()))[0] == 200
        assert any(name.endswith(".json.gz") for name in _spool_files(tmp_path))
        (tmp_path / "opt-out").write_text("")
        thread.join(5)
        assert result == [0] and lifecycle.healthz(base, tmp_path) is None
        assert [n for n in _spool_files(tmp_path) if n.endswith((".json.gz", ".jsonl"))] == []
        assert not lifecycle.lock_held(tmp_path)
    finally:
        if thread.is_alive():
            post_json(base, "/shutdown", {}, token=lifecycle.read_token(tmp_path))
            thread.join(5)


def test_signed_out_opt_out_also_deletes_the_spool_on_shutdown(tmp_path, monkeypatch):
    monkeypatch.setattr(forwarder, "LOOP_INTERVAL_S", 5.0)  # the loop never reaches its opt-out check
    base = free_port_run()
    result = []
    thread = _run_in_thread(base, tmp_path, result)
    try:
        assert post_json(base, "/v1/logs", json.loads((FIXTURES / "otlp-logs-small.json").read_text()))[0] == 200
        (tmp_path / "opt-out").write_text("")
        assert lifecycle.stop(tmp_path) is True
        thread.join(5)
        assert [n for n in _spool_files(tmp_path) if n.endswith((".json.gz", ".jsonl"))] == []
    finally:
        if thread.is_alive():
            post_json(base, "/shutdown", {}, token=lifecycle.read_token(tmp_path))
            thread.join(5)


def test_signed_in_opt_out_keeps_the_spool_for_upload_on_shutdown(tmp_path, monkeypatch):
    monkeypatch.setattr(forwarder, "LOOP_INTERVAL_S", 0.02)
    _signed_in(tmp_path)
    base = free_port_run()
    result = []
    thread = _run_in_thread(base, tmp_path, result)
    try:
        assert post_json(base, "/v1/logs", json.loads((FIXTURES / "otlp-logs-small.json").read_text()))[0] == 200
        (tmp_path / "opt-out").write_text("")
        time.sleep(0.3)
        assert thread.is_alive()  # waits for the upload to empty the spool
        assert lifecycle.stop(tmp_path) is True
        thread.join(5)
        assert any(name.endswith(".json.gz") for name in _spool_files(tmp_path))
    finally:
        if thread.is_alive():
            post_json(base, "/shutdown", {}, token=lifecycle.read_token(tmp_path))
            thread.join(5)


def test_forwarder_loop_ticks_and_waits_for_an_empty_spool_before_opt_out_exit(tmp_path, monkeypatch):
    monkeypatch.setattr(forwarder, "LOOP_INTERVAL_S", 0.02)
    _signed_in(tmp_path)  # signed out, an opt-out deletes the spool at once instead
    base = free_port_run()
    ticks = []
    result = []
    thread = threading.Thread(
        target=lambda: result.append(forwarder.run(_cfg(base), tmp_path, PLUGIN_ROOT, PLUGIN_VERSION,
                                                   tick=ticks.append)), daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 5
        while lifecycle.healthz(base, tmp_path) is None and time.monotonic() < deadline:
            time.sleep(0.02)
        assert post_json(base, "/v1/logs", json.loads((FIXTURES / "otlp-logs-small.json").read_text()))[0] == 200
        (tmp_path / "opt-out").write_text("")
        time.sleep(0.3)
        assert thread.is_alive() and len(ticks) > 3 and all(isinstance(t, float) for t in ticks)
        sp = spool.Spool(tmp_path, _cfg(base))
        assert post_json(base, "/flush", {}, token=lifecycle.read_token(tmp_path))[0] == 200
        for path in sp.closed_batches_oldest_first():
            sp.delete(path)
        thread.join(5)
        assert result == [0] and lifecycle.healthz(base, tmp_path) is None
    finally:
        if thread.is_alive():
            post_json(base, "/shutdown", {}, token=lifecycle.read_token(tmp_path))
            thread.join(5)


def test_forwarder_tick_errors_are_logged_by_type_only(tmp_path, monkeypatch):
    monkeypatch.setattr(forwarder, "LOOP_INTERVAL_S", 0.02)
    (tmp_path / "opt-out").write_text("")

    def tick(now):
        raise RuntimeError("devuser secret detail")

    assert forwarder.run(_cfg(free_port_run()), tmp_path, PLUGIN_ROOT, PLUGIN_VERSION, tick=tick) == 0
    text = (tmp_path / "forwarder.log").read_text()
    assert "RuntimeError" in text and "devuser" not in text


# ---------------------------------------------------------------- the detached process


def test_spawn_command_is_detached_with_dash_b(tmp_path, monkeypatch):
    calls = []

    class FakePopen:
        def __init__(self, args, **kwargs):
            calls.append((args, kwargs))

    monkeypatch.setattr(lifecycle.subprocess, "Popen", FakePopen)
    lifecycle._spawn(PLUGIN_ROOT, tmp_path)
    [(args, kwargs)] = calls
    assert args == [sys.executable, "-B", str(PLUGIN_ROOT / "bin" / "cpp_telemetry"), "forwarder"]
    assert kwargs["start_new_session"] is True and kwargs["close_fds"] is True
    assert kwargs["stdin"] == kwargs["stdout"] == kwargs["stderr"] == subprocess.DEVNULL
    assert kwargs["env"]["CLAUDE_PLUGIN_DATA"] == str(tmp_path)


def test_ensure_running_starts_process_and_healthz_answers(tmp_path, spawned):
    base = free_port_run()
    _write_override(tmp_path, base)
    port = lifecycle.ensure_running(_cfg(base), tmp_path, PLUGIN_ROOT, PLUGIN_VERSION)
    assert port == base and len(spawned) == 1
    body = lifecycle.healthz(port, tmp_path)
    assert body is not None and (body["status"], body["version"], body["port"]) == ("ok", PLUGIN_VERSION, port)
    assert len(body["proof"]) == 64 and lifecycle.lock_held(tmp_path)
    assert ((tmp_path / "token").stat().st_mode & 0o777) == 0o600
    assert lifecycle.read_lock_pid(tmp_path) == spawned[0][0].pid
    # A second call finds the running forwarder and starts nothing.
    assert lifecycle.ensure_running(_cfg(base), tmp_path, PLUGIN_ROOT, PLUGIN_VERSION) == port
    assert len(spawned) == 1
    assert lifecycle.stop(tmp_path) is True
    assert spawned[0][0].wait(5) == 0
    assert lifecycle.healthz(port, tmp_path) is None and not (tmp_path / "forwarder.lock").exists()
    assert lifecycle.stop(tmp_path) is False


def test_sigterm_drains_and_exits(tmp_path, spawned):
    base = free_port_run()
    _write_override(tmp_path, base)
    port = lifecycle.ensure_running(_cfg(base), tmp_path, PLUGIN_ROOT, PLUGIN_VERSION)
    assert post_json(port, "/v1/logs", json.loads((FIXTURES / "otlp-logs-small.json").read_text()))[0] == 200
    assert list((tmp_path / "spool" / "session-a").glob("*.open.jsonl"))
    proc = spawned[0][0]
    os.kill(proc.pid, signal.SIGTERM)
    assert proc.wait(5) == 0
    assert not list((tmp_path / "spool" / "session-a").glob("*.open.jsonl"))
    [closed] = list((tmp_path / "spool" / "session-a").glob("*.json.gz"))
    with gzip.open(str(closed), "rt", encoding="utf-8") as fh:
        assert json.load(fh)["events"][0]["signal"] == "logs"
    assert not (tmp_path / "forwarder.lock").exists()
    log_text = (tmp_path / "forwarder.log").read_text()
    assert "stopped" in log_text and "devuser" not in log_text


def test_ensure_running_replaces_an_older_forwarder(tmp_path, spawned):
    base = free_port_run()
    _write_override(tmp_path, base)
    cfg = _cfg(base)
    stopped = threading.Event()
    old = receiver.Receiver(cfg, spool.Spool(tmp_path, cfg), receiver.IdentityProvider(), "1.0.9",
                            lambda hook: [], lambda event: None, receiver.ForwarderState(), on_shutdown=stopped.set,
                            token=_token(tmp_path))
    thread = threading.Thread(target=old.serve_forever, daemon=True)
    thread.start()
    (tmp_path / "port").write_text(str(base))
    try:
        port = lifecycle.ensure_running(cfg, tmp_path, PLUGIN_ROOT, PLUGIN_VERSION)
        assert stopped.is_set() and len(spawned) == 1
        assert lifecycle.healthz(port, tmp_path)["version"] == PLUGIN_VERSION
    finally:
        old.close()
        thread.join(5)


def test_ensure_running_does_not_start_when_opted_out_and_spool_empty(tmp_path, spawned):
    base = free_port_run()
    _write_override(tmp_path, base)
    (tmp_path / "opt-out").write_text("")
    with pytest.raises(lifecycle.NotStarted):
        lifecycle.ensure_running(_cfg(base), tmp_path, PLUGIN_ROOT, PLUGIN_VERSION)
    assert spawned == []


def test_cli_ensure_running_and_forwarder_bodies(data_dir, spawned, capsys):
    base = free_port_run()
    _write_override(data_dir, base)
    assert cli.main(["ensure-running"]) == 0
    assert len(spawned) == 1 and lifecycle.healthz(base, data_dir)["version"] == PLUGIN_VERSION
    # A second forwarder finds the lock held and exits 0 at once.
    assert cli.main(["forwarder"]) == 0
    captured = capsys.readouterr()
    # ensure-running prints the proof-checked port for the nudge script; the forwarder prints nothing.
    assert (captured.out, captured.err) == ("%d\n" % base, "")
    assert lifecycle.stop(data_dir) is True


def test_ensure_running_finds_a_locked_forwarder_on_a_scan_port(tmp_path, spawned, holder):
    # The forwarder sits on base+1 (base was foreign when it started); base is free now and the port file is stale.
    base = free_port_run()
    cfg = _cfg(base)
    running = receiver.Receiver(cfg, spool.Spool(tmp_path, cfg), receiver.IdentityProvider(), PLUGIN_VERSION,
                                lambda hook: [], lambda event: None, receiver.ForwarderState(), port=base + 1,
                                token=_token(tmp_path))
    thread = threading.Thread(target=running.serve_forever, daemon=True)
    thread.start()
    (tmp_path / "forwarder.lock").write_text("%d\n" % holder)
    (tmp_path / "port").write_text(str(base))
    try:
        assert lifecycle.ensure_running(cfg, tmp_path, PLUGIN_ROOT, PLUGIN_VERSION) == base + 1
        assert spawned == [] and lifecycle.read_port(tmp_path) == base + 1
    finally:
        running.close()
        thread.join(5)


def test_mimic_listener_echoing_healthz_is_foreign(tmp_path):
    base = free_port_run()
    _token(tmp_path)
    mimic = ThreadingHTTPServer(("127.0.0.1", base), _Mimic)
    thread = threading.Thread(target=mimic.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    thread.start()
    try:
        assert lifecycle.healthz(base, tmp_path) is None
        assert lifecycle.choose_port(_cfg(base), tmp_path) == base + 1
    finally:
        mimic.shutdown()
        mimic.server_close()
        thread.join(5)


def test_unrelated_live_pid_in_lock_is_stale_and_never_signalled(tmp_path, unrelated, monkeypatch):
    (tmp_path / "forwarder.lock").write_text("%d\n" % unrelated)
    (tmp_path / "port").write_text(str(free_port_run(1)))
    sent = []
    real_kill = lifecycle.os.kill

    def kill(pid, sig):
        if sig != 0:
            sent.append((pid, sig))
            return None
        return real_kill(pid, sig)

    monkeypatch.setattr(lifecycle.os, "kill", kill)
    try:
        assert not lifecycle.lock_held(tmp_path)
        assert lifecycle.stop(tmp_path) is False
    finally:
        monkeypatch.setattr(lifecycle.os, "kill", real_kill)  # the fixtures' own kills must be real
    assert sent == []
    lock = lifecycle.acquire_lock(tmp_path)
    assert lock is not None and lifecycle.read_lock_pid(tmp_path) == os.getpid()
    lock.release()


def test_token_is_32_hex_and_0600_and_kept(tmp_path):
    token = lifecycle.ensure_token(tmp_path)
    assert len(token) == 32 and int(token, 16) >= 0
    assert ((tmp_path / "token").stat().st_mode & 0o777) == 0o600
    assert lifecycle.ensure_token(tmp_path) == token == lifecycle.read_token(tmp_path)
    (tmp_path / "token").write_text("not a token")
    assert lifecycle.read_token(tmp_path) is None and lifecycle.ensure_token(tmp_path) != token


class _Relay(BaseHTTPRequestHandler):
    """Relays /healthz to the real forwarder and echoes its body with its own port number."""

    target = 0

    def do_GET(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.target, timeout=2)
        try:
            conn.request("GET", self.path)
            body = json.loads(conn.getresponse().read().decode("utf-8"))
        finally:
            conn.close()
        body["port"] = self.server.server_address[1]
        data = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


def _ours_on(tmp_path, cfg, port):
    ours = receiver.Receiver(cfg, spool.Spool(tmp_path, cfg), receiver.IdentityProvider(), PLUGIN_VERSION,
                             lambda hook: [], lambda event: None, receiver.ForwarderState(), port=port,
                             token=_token(tmp_path))
    thread = threading.Thread(target=ours.serve_forever, daemon=True)
    thread.start()
    return ours, thread


def test_relay_mimic_on_another_port_is_foreign(tmp_path):
    base = free_port_run()
    cfg = _cfg(base)
    ours, ours_thread = _ours_on(tmp_path, cfg, base + 5)
    relay_handler = type("RelayTo", (_Relay,), {"target": base + 5})
    relay = ThreadingHTTPServer(("127.0.0.1", base), relay_handler)
    relay_thread = threading.Thread(target=relay.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    relay_thread.start()
    try:
        assert lifecycle.healthz(base + 5, tmp_path) is not None
        assert lifecycle.healthz(base, tmp_path) is None
        assert lifecycle.choose_port(cfg, tmp_path) == base + 1
    finally:
        relay.shutdown()
        relay.server_close()
        relay_thread.join(5)
        ours.close()
        ours_thread.join(5)


def test_forwarder_argv_rule():
    rule = lifecycle._forwarder_argv
    assert rule(["/usr/bin/python3", "-B", "/x/bin/cpp_telemetry", "forwarder"])
    assert rule(["cpp_telemetry", "forwarder"])
    assert not rule(["zsh", "-c", "python3 -B /x/bin/cpp_telemetry forwarder"])
    assert not rule(["python3", "/x/bin/cpp_telemetry", "status"])
    assert not rule(["python3", "/x/bin/cpp_telemetry_old", "forwarder"])
    assert not rule(["python3", "-c", "pass", "cpp_telemetry"])


def test_proof_only_holder_counts_as_held(tmp_path, unrelated):
    base = free_port_run()
    cfg = _cfg(base)
    (tmp_path / "forwarder.lock").write_text("%d\n" % unrelated)
    ours, thread = _ours_on(tmp_path, cfg, base)
    (tmp_path / "port").write_text(str(base))
    try:
        assert not lifecycle._names_forwarder(unrelated)
        assert lifecycle.lock_held(tmp_path) and lifecycle.acquire_lock(tmp_path) is None
    finally:
        ours.close()
        thread.join(5)
    assert not lifecycle.lock_held(tmp_path)


class _RawHealthz(BaseHTTPRequestHandler):
    """Answers /healthz with a fixed raw JSON body; ``{port}`` is filled with the listener's own port."""

    template = b"{}"

    def do_GET(self):
        body = self.template.replace(b"{port}", str(self.server.server_address[1]).encode())
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.mark.parametrize("template", [
    b'{"status": "ok", "version": "\\ud800", "port": {port}, "proof": "x"}',
    b'{"status": "ok", "version": 110, "port": {port}, "proof": "x"}',
    b'{"status": "ok", "version": "1.1.0", "port": "{port}", "proof": "x"}',
    b'{"status": "ok", "version": "1.1.0", "port": {port}.0, "proof": "x"}',
    b'{"status": "ok", "version": "1.1.0 beta", "port": {port}, "proof": "x"}',
    b'{"status": "ok", "version": "' + b"1" * 33 + b'", "port": {port}, "proof": "x"}',
], ids=["lone-surrogate-version", "int-version", "string-port", "float-port", "space-in-version", "long-version"])
def test_malformed_healthz_bodies_are_foreign(tmp_path, template):
    base = free_port_run()
    _token(tmp_path)
    handler = type("Raw", (_RawHealthz,), {"template": template})
    listener = ThreadingHTTPServer(("127.0.0.1", base), handler)
    thread = threading.Thread(target=listener.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    thread.start()
    try:
        assert lifecycle._probe(base, tmp_path)[0] == lifecycle.FOREIGN
        assert lifecycle.healthz(base, tmp_path) is None
        assert lifecycle.choose_port(_cfg(base), tmp_path) == base + 1
    finally:
        listener.shutdown()
        listener.server_close()
        thread.join(5)


def test_receiver_refuses_a_version_it_could_not_prove(tmp_path):
    cfg = _cfg(free_port_run())
    for bad in ("1.1.0\u00e9", "", "1" * 33):
        with pytest.raises(ValueError):
            receiver.Receiver(cfg, spool.Spool(tmp_path, cfg), receiver.IdentityProvider(), bad,
                              lambda hook: [], lambda event: None, receiver.ForwarderState(), token=_token(tmp_path))
