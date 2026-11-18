import gzip
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
            port = lifecycle.read_port(data)
            if port is not None:
                lifecycle._post(port, "/shutdown", timeout=1)
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
                             lambda hook: [], lambda event: None, receiver.ForwarderState())
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


def test_lock_holds_the_pid_and_a_stale_lock_is_taken_over(tmp_path):
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
    (tmp_path / "forwarder.lock").write_text("%d\n" % os.getppid())
    assert lifecycle.lock_held(tmp_path) and lifecycle.acquire_lock(tmp_path) is None


# ---------------------------------------------------------------- forwarder.run in-process


def test_forwarder_exits_0_when_a_live_pid_holds_the_lock(tmp_path, monkeypatch):
    (tmp_path / "forwarder.lock").write_text("%d\n" % os.getppid())
    reaped = []
    monkeypatch.setattr(spool.Spool, "reap_orphans", lambda self: reaped.append(1) or [])
    assert forwarder.run(_cfg(free_port_run()), tmp_path, PLUGIN_ROOT, PLUGIN_VERSION) == 0
    assert reaped == [] and not (tmp_path / "port").exists()
    assert (tmp_path / "forwarder.lock").read_text().strip() == str(os.getppid())


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


def test_forwarder_loop_ticks_and_waits_for_an_empty_spool_before_opt_out_exit(tmp_path, monkeypatch):
    monkeypatch.setattr(forwarder, "LOOP_INTERVAL_S", 0.02)
    base = free_port_run()
    ticks = []
    result = []
    thread = threading.Thread(
        target=lambda: result.append(forwarder.run(_cfg(base), tmp_path, PLUGIN_ROOT, PLUGIN_VERSION,
                                                   tick=ticks.append)), daemon=True)
    thread.start()
    deadline = time.monotonic() + 5
    while lifecycle.healthz(base) is None and time.monotonic() < deadline:
        time.sleep(0.02)
    assert post_json(base, "/v1/logs", json.loads((FIXTURES / "otlp-logs-small.json").read_text()))[0] == 200
    (tmp_path / "opt-out").write_text("")
    time.sleep(0.3)
    assert thread.is_alive() and len(ticks) > 3 and all(isinstance(t, float) for t in ticks)
    sp = spool.Spool(tmp_path, _cfg(base))
    assert post_json(base, "/flush", {})[0] == 200
    for path in sp.closed_batches_oldest_first():
        sp.delete(path)
    thread.join(5)
    assert result == [0] and lifecycle.healthz(base) is None


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
    assert lifecycle.healthz(port) == {"status": "ok", "version": PLUGIN_VERSION, "port": port}
    assert lifecycle.read_lock_pid(tmp_path) == spawned[0][0].pid
    # A second call finds the running forwarder and starts nothing.
    assert lifecycle.ensure_running(_cfg(base), tmp_path, PLUGIN_ROOT, PLUGIN_VERSION) == port
    assert len(spawned) == 1
    assert lifecycle.stop(tmp_path) is True
    assert spawned[0][0].wait(5) == 0
    assert lifecycle.healthz(port) is None and not (tmp_path / "forwarder.lock").exists()
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
                            lambda hook: [], lambda event: None, receiver.ForwarderState(), on_shutdown=stopped.set)
    thread = threading.Thread(target=old.serve_forever, daemon=True)
    thread.start()
    (tmp_path / "port").write_text(str(base))
    try:
        port = lifecycle.ensure_running(cfg, tmp_path, PLUGIN_ROOT, PLUGIN_VERSION)
        assert stopped.is_set() and len(spawned) == 1
        assert lifecycle.healthz(port)["version"] == PLUGIN_VERSION
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
    assert len(spawned) == 1 and lifecycle.healthz(base)["version"] == PLUGIN_VERSION
    # A second forwarder finds the lock held and exits 0 at once.
    assert cli.main(["forwarder"]) == 0
    captured = capsys.readouterr()
    assert (captured.out, captured.err) == ("", "")
    assert lifecycle.stop(data_dir) is True
