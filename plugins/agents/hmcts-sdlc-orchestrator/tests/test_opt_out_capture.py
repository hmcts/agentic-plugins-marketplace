"""After an opt-out nothing new is captured, the drain still ends, and a later start drains what is left."""
import json
import logging
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from cpp_telemetry import PLUGIN_VERSION, auth, cli, config, forwarder, lifecycle, receiver, spool, uploader
from cpp_telemetry.config import Config
from tests.helpers_net import free_port_run, post_json
from tests.test_cli import configured  # noqa: F401 - fixture
from tests.test_lifecycle import FIXTURES, _cfg, _run_in_thread, _signed_in, _spool_files
from tests.test_receiver import TOKEN, Harness

T0 = 1_800_000_000.0
DAY = 86_400


def _logs():
    return json.loads((FIXTURES / "otlp-logs-small.json").read_text(encoding="utf-8"))


def _opt_out_event():
    return {"signal": "event",
            "payload": {"name": "opt_out", "plugin_version": PLUGIN_VERSION, "ts": "2026-11-18T09:00:00.000Z"}}


@pytest.fixture
def harness(tmp_path):
    h = Harness(tmp_path)
    yield h
    h.close()


def test_exports_and_hooks_after_the_opt_out_event_are_refused_and_nothing_new_is_spooled(harness):
    assert post_json(harness.port, "/v1/logs", _logs())[0] == 200
    (harness.data / "opt-out").write_text("")  # cli writes the file first, then posts the event
    assert post_json(harness.port, "/event", _opt_out_event(), token=TOKEN) == (200, {})
    for _ in range(3):  # an open session keeps exporting every 10 s
        assert post_json(harness.port, "/v1/logs", _logs())[0] == 503
    assert post_json(harness.port, "/hook", {"hook_event_name": "Stop"}, token=TOKEN)[0] == 503
    assert harness.hooks == []
    assert post_json(harness.port, "/flush", {}, token=TOKEN)[0] == 200
    batches = harness.batches()
    assert len(batches["session-a"]) == 1  # only the export from before the opt-out
    names = [event["payload"]["name"] for events in batches.values() for event in events
             if event["signal"] == "event"]
    assert names == ["opt_out"]


def test_the_opt_out_file_alone_refuses_capture_and_its_removal_resumes_it(harness, monkeypatch):
    monkeypatch.setattr(receiver, "OPT_OUT_RECHECK_S", 0.0)
    (harness.data / "opt-out").write_text("")
    assert post_json(harness.port, "/v1/logs", _logs())[0] == 503
    assert post_json(harness.port, "/hook", {"hook_event_name": "Stop"}, token=TOKEN)[0] == 503
    assert post_json(harness.port, "/event", {"signal": "event", "payload": {"name": "x"}}, token=TOKEN)[0] == 200
    (harness.data / "opt-out").unlink()  # /telemetry on: a forwarder still draining captures again
    assert post_json(harness.port, "/v1/logs", _logs())[0] == 200


def test_the_opt_out_stat_is_cached_between_checks(harness):
    assert receiver.OPT_OUT_RECHECK_S == 2.0
    assert harness.receiver.opted_out() is False
    (harness.data / "opt-out").write_text("")
    assert harness.receiver.opted_out() is False  # still the cached stat
    harness.receiver.note_opt_out()
    assert harness.receiver.opted_out() is True


def test_signed_in_forwarder_refuses_capture_after_opt_out_and_still_drains(tmp_path, monkeypatch):
    monkeypatch.setattr(forwarder, "LOOP_INTERVAL_S", 0.02)
    _signed_in(tmp_path)
    base = free_port_run()
    result = []
    thread = _run_in_thread(base, tmp_path, result)
    token = lifecycle.read_token(tmp_path)
    try:
        assert post_json(base, "/v1/logs", _logs())[0] == 200
        (tmp_path / "opt-out").write_text("")
        assert post_json(base, "/event", _opt_out_event(), token=token)[0] == 200
        assert post_json(base, "/flush", {}, token=token)[0] == 200
        before = _spool_files(tmp_path)
        for _ in range(3):
            assert post_json(base, "/v1/logs", _logs())[0] == 503
        assert post_json(base, "/hook", {"hook_event_name": "Stop"}, token=token)[0] == 503
        time.sleep(0.1)
        assert thread.is_alive() and _spool_files(tmp_path) == before
        sp = spool.Spool(tmp_path, _cfg(base))
        for path in sp.closed_batches_oldest_first():  # the upload empties the spool
            sp.delete(path)
        thread.join(5)
        assert result == [0] and not thread.is_alive()
    finally:
        if thread.is_alive():
            post_json(base, "/shutdown", {}, token=lifecycle.read_token(tmp_path))
            thread.join(5)


def test_after_opt_out_expired_batches_go_without_a_gap_so_the_drain_ends(tmp_path):
    cfg = Config()
    sp = spool.Spool(tmp_path, cfg, clock=lambda: T0)
    sp.append("sess-1", {"signal": "event", "payload": {"name": "x"}})
    sp.close_all()
    (tmp_path / "opt-out").write_text("")
    up = uploader.Uploader(cfg, sp, auth.TokenCache(tmp_path), receiver.ForwarderState(),
                           logging.getLogger("test"), data_dir=tmp_path)
    up.tick(T0 + 31 * DAY)
    assert sp.is_empty()


def test_expired_batches_still_leave_a_gap_while_opted_in(tmp_path):
    cfg = Config()
    sp = spool.Spool(tmp_path, cfg, clock=lambda: T0)
    sp.append("sess-1", {"signal": "event", "payload": {"name": "x"}})
    sp.close_all()
    up = uploader.Uploader(cfg, sp, auth.TokenCache(tmp_path), receiver.ForwarderState(),
                           logging.getLogger("test"), data_dir=tmp_path)
    up.tick(T0 + 31 * DAY)
    assert not sp.is_empty()  # the gap record waits for upload


@pytest.fixture
def drain_spawn(monkeypatch):
    """``lifecycle._spawn`` runs ``forwarder.run`` in a thread; its tick uploads once ``allow`` is set.

    The finaliser shuts down every forwarder the test started.
    """
    runs = []
    allow = threading.Event()
    monkeypatch.setattr(forwarder, "LOOP_INTERVAL_S", 0.02)

    def spawn(plugin_root, data_dir):
        cfg = config.load(data_dir)

        def tick(now):
            if allow.is_set():
                sp = spool.Spool(data_dir, cfg)
                for path in sp.closed_batches_oldest_first():
                    sp.delete(path)

        result = []
        thread = threading.Thread(
            target=lambda: result.append(forwarder.run(cfg, data_dir, plugin_root, PLUGIN_VERSION, tick=tick)),
            daemon=True)
        thread.start()
        runs.append(SimpleNamespace(thread=thread, result=result, data=Path(data_dir)))
        return thread

    monkeypatch.setattr(lifecycle, "_spawn", spawn)
    yield runs, allow
    for run in runs:
        if run.thread.is_alive():
            port = lifecycle.read_port(run.data)
            if port is not None:
                post_json(port, "/shutdown", {}, token=lifecycle.read_token(run.data))
            run.thread.join(5)
        assert not run.thread.is_alive()


def _closed_batch(data):
    sp = spool.Spool(data, config.load(data))
    sp.append("sess-1", {"signal": "event", "payload": {"name": "x"}})
    sp.close_all()
    return sp


def test_start_after_opt_out_with_batches_left_runs_a_drain_only_forwarder(configured, drain_spawn, capsys):
    runs, allow = drain_spawn
    _signed_in(configured.data)
    sp = _closed_batch(configured.data)
    (configured.data / "opt-out").write_text("")
    assert cli.main(["start"]) == 0
    assert capsys.readouterr().out == "" and not configured.settings.exists()
    (run,) = runs
    port = lifecycle.read_port(configured.data)
    assert post_json(port, "/v1/logs", _logs())[0] == 503  # drain only: nothing new is captured
    allow.set()
    run.thread.join(5)
    assert run.result == [0] and sp.is_empty()


def test_start_after_opt_out_with_an_empty_spool_starts_nothing(configured, drain_spawn, capsys):
    runs, _ = drain_spawn
    _signed_in(configured.data)
    (configured.data / "opt-out").write_text("")
    assert cli.main(["start"]) == 0
    assert runs == [] and capsys.readouterr().out == ""


def test_signed_out_start_after_opt_out_deletes_the_batches_left_and_starts_nothing(configured, drain_spawn,
                                                                                    capsys):
    runs, _ = drain_spawn
    sp = _closed_batch(configured.data)
    (configured.data / "opt-out").write_text("")
    assert cli.main(["start"]) == 0
    assert runs == [] and sp.is_empty() and capsys.readouterr().out == ""
