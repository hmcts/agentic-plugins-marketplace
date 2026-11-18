"""The configured CLI: start, status, login, optout, on, uninstall, ensure-running."""
import io
import json
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from cpp_telemetry import PLUGIN_VERSION, auth, cli, config, lifecycle, receiver, settings, spool, uploader
from tests.fakes import DEVICECODE_PATH, fake_auth, make_token  # noqa: F401 - fixtures
from tests.helpers_net import free_port_run, port_is_free

CONFIGURED = {
    "ingest_url": "http://127.0.0.1:18080",
    "tenant_id": "00000000-0000-0000-0000-000000000001",
    "client_id": "00000000-0000-0000-0000-000000000002",
    "api_app_id": "00000000-0000-0000-0000-000000000003",
}
COLLECTOR = "https://collector.example.invalid:4318"


class _NoRead(io.StringIO):
    def read(self, *args):
        raise AssertionError("stdin must not be read")


@pytest.fixture
def configured(data_dir, tmp_path, monkeypatch):
    """Override present, free ports, CLAUDE_CONFIG_DIR and CPP_HARNESS_HOME in temp."""
    base = free_port_run()
    (data_dir / "override.json").write_text(json.dumps(dict(CONFIGURED, port=base, port_scan=[base + 1, base + 9])))
    claude_dir = tmp_path / "claude-config"
    claude_dir.mkdir()
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(claude_dir))
    monkeypatch.setenv("CPP_HARNESS_HOME", str(tmp_path / "harness"))
    monkeypatch.setattr(cli.sys, "stdin", io.StringIO(""))
    return SimpleNamespace(data=data_dir, base=base, settings=claude_dir / "settings.json")


@pytest.fixture
def fake_forwarder(configured):
    """A real in-process receiver on the configured port that passes the healthz proof and records control posts."""
    cfg = config.load(configured.data)
    token = lifecycle.ensure_token(configured.data)
    hooks, events = [], []

    def on_hook(hook):
        hooks.append(hook)
        return []

    sp = spool.Spool(configured.data, cfg)
    rec = receiver.Receiver(cfg, sp, receiver.IdentityProvider(trusted_email=None), PLUGIN_VERSION, on_hook,
                            events.append, receiver.ForwarderState(), port=configured.base, token=token)
    lifecycle.write_port(configured.data, configured.base)
    thread = threading.Thread(target=rec.serve_forever, daemon=True)
    thread.start()
    yield SimpleNamespace(port=configured.base, hooks=hooks, events=events, spool=sp, **vars(configured))
    rec.close()
    thread.join(5)


def _no_choose_port(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("choose_port must not be called by the CLI")

    monkeypatch.setattr(lifecycle, "choose_port", refuse)


def test_start_configured_applies_settings_and_posts_hook(fake_forwarder, monkeypatch, capsys):
    _no_choose_port(monkeypatch)
    order = []
    real_ensure, real_apply = lifecycle.ensure_running, settings.apply
    monkeypatch.setattr(lifecycle, "ensure_running", lambda *a: order.append("ensure") or real_ensure(*a))
    monkeypatch.setattr(settings, "apply", lambda *a: order.append("apply") or real_apply(*a))
    hook = {"hook_event_name": "SessionStart", "session_id": "sess-1", "cwd": str(fake_forwarder.data)}
    monkeypatch.setattr(cli.sys, "stdin", io.StringIO(json.dumps(hook)))
    assert cli.main(["start"]) == 0
    assert order == ["ensure", "apply"]
    env = json.loads(fake_forwarder.settings.read_text())["env"]
    assert env["OTEL_EXPORTER_OTLP_ENDPOINT"] == "http://127.0.0.1:%d" % fake_forwarder.port
    assert (fake_forwarder.data / settings.MANAGED_KEYS_FILE).exists()
    assert fake_forwarder.hooks == [hook]
    out = capsys.readouterr().out
    assert out.count("\n") == 1 and "/telemetry login" in out  # signed out: the daily notice only


def test_start_without_a_hook_event_posts_nothing(fake_forwarder, monkeypatch):
    monkeypatch.setattr(cli.sys, "stdin", io.StringIO(json.dumps({"session_id": "sess-1"})))
    assert cli.main(["start"]) == 0
    assert fake_forwarder.hooks == []


def test_start_prints_removed_key_names_never_values(fake_forwarder, capsys):
    key = settings.COMPETING_KEYS[0]
    fake_forwarder.settings.write_text(json.dumps({"env": {key: COLLECTOR}}))
    auth.TokenCache(fake_forwarder.data).save(make_token("acc"), make_token("ref"), time.time() + 3600)
    assert cli.main(["start"]) == 0
    out = capsys.readouterr().out
    assert out.count("\n") == 1 and key in out and COLLECTOR not in out and "example.invalid" not in out
    assert cli.main(["start"]) == 0  # already moved aside: nothing more to say
    assert capsys.readouterr().out == ""


def test_start_is_silent_and_untouched_when_opted_out(fake_forwarder, monkeypatch, capsys):
    (fake_forwarder.data / lifecycle.OPT_OUT_FILE).write_text("")
    monkeypatch.setattr(cli.sys, "stdin", io.StringIO(json.dumps({"hook_event_name": "SessionStart"})))
    assert cli.main(["start"]) == 0
    assert capsys.readouterr().out == "" and not fake_forwarder.settings.exists() and fake_forwarder.hooks == []


@pytest.mark.parametrize("entry, notice", [("not-an-object", True), (None, False)])
def test_marketplace_notice_only_when_behind_and_autoupdate_failed(fake_forwarder, monkeypatch, capsys, entry,
                                                                   notice):
    auth.TokenCache(fake_forwarder.data).save(make_token("acc"), make_token("ref"), time.time() + 3600)
    doc = {} if entry is None else {"extraKnownMarketplaces": {settings.MARKETPLACE_NAME: entry}}
    fake_forwarder.settings.write_text(json.dumps(doc))
    monkeypatch.setattr(settings, "check_marketplace_version", lambda root: ("1.0.0", "1.2.0"))
    assert cli.main(["start"]) == 0
    out = capsys.readouterr().out
    assert ("1.2.0" in out) is notice and out.count("\n") == int(notice)


def test_start_survives_a_forwarder_that_cannot_start(configured, monkeypatch, capsys):
    def fail(*args):
        raise lifecycle.NotStarted("test")

    monkeypatch.setattr(lifecycle, "ensure_running", fail)
    assert cli.main(["start"]) == 0
    assert capsys.readouterr().out == "" and not configured.settings.exists()
    assert "NotStarted" in (configured.data / "forwarder.log").read_text()


def test_start_calls_install_shims_when_the_module_exists(fake_forwarder, monkeypatch):
    calls = []
    fake_module = SimpleNamespace(install_shims=lambda root, version: calls.append((root, version)))
    monkeypatch.setitem(cli.sys.modules, "cpp_telemetry.git_event", fake_module)
    assert cli.main(["start"]) == 0
    assert calls and calls[0][1] == PLUGIN_VERSION


def test_ensure_running_prints_the_proof_checked_port(fake_forwarder, monkeypatch, capsys):
    _no_choose_port(monkeypatch)
    assert cli.main(["ensure-running"]) == 0
    assert capsys.readouterr().out == "%d\n" % fake_forwarder.port


def _sign_in(data):
    auth.TokenCache(data).save(make_token("acc"), make_token("ref"), time.time() + 3600)


def test_optout_restores_and_posts_opt_out_event(fake_forwarder, capsys):
    _sign_in(fake_forwarder.data)
    key = settings.COMPETING_KEYS[0]
    fake_forwarder.settings.write_text(json.dumps({"env": {key: COLLECTOR}}))
    assert cli.main(["start"]) == 0
    capsys.readouterr()
    assert cli.main(["optout"]) == 0
    assert json.loads(fake_forwarder.settings.read_text())["env"] == {key: COLLECTOR}
    assert (fake_forwarder.data / lifecycle.OPT_OUT_FILE).exists()
    (event,) = fake_forwarder.events
    assert event["signal"] == "event"
    assert set(event["payload"]) == {"name", "plugin_version", "ts"} and event["payload"]["name"] == "opt_out"
    assert event["payload"]["plugin_version"] == PLUGIN_VERSION
    (batch,) = fake_forwarder.spool.closed_batches_oldest_first()  # /flush closed it
    assert "opt_out" in json.dumps(json.loads(__import__("gzip").decompress(batch.read_bytes())))
    out = capsys.readouterr().out
    assert out.count("\n") == 1 and COLLECTOR not in out


def _no_spawn(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("a signed-out opt-out must not start a forwarder")

    monkeypatch.setattr(lifecycle, "ensure_running", refuse)


def test_signed_out_optout_without_a_forwarder_deletes_the_spool_and_spawns_nothing(configured, monkeypatch,
                                                                                     capsys):
    _no_spawn(monkeypatch)
    sp = spool.Spool(configured.data, config.load(configured.data))
    sp.append("sess-1", {"signal": "event", "payload": {"name": "x"}})
    sp.close_all()
    sp.append("sess-2", {"signal": "event", "payload": {"name": "y"}})
    assert cli.main(["optout"]) == 0
    assert (configured.data / lifecycle.OPT_OUT_FILE).exists()
    assert sp.is_empty() and list(sp.root.glob("*/*.jsonl")) == [] and port_is_free(configured.base)
    assert capsys.readouterr().out.count("\n") == 1


def test_signed_out_optout_posts_to_a_running_forwarder_without_spawning(fake_forwarder, monkeypatch):
    _no_spawn(monkeypatch)
    assert cli.main(["optout"]) == 0
    (event,) = fake_forwarder.events
    assert event["payload"]["name"] == "opt_out"
    assert (fake_forwarder.data / lifecycle.OPT_OUT_FILE).exists()


def test_optout_when_the_data_dir_cannot_be_made_says_one_line(tmp_path, monkeypatch, capsys):
    (tmp_path / "file").write_text("x")
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(tmp_path / "file" / "data"))
    assert cli.main(["optout"]) == 1
    assert capsys.readouterr().out.count("\n") == 1


def test_signed_in_uninstall_waits_for_the_forwarder_to_drain(fake_forwarder, monkeypatch):
    _sign_in(fake_forwarder.data)
    held = iter([True, True, False])
    monkeypatch.setattr(lifecycle, "lock_held", lambda data: next(held, False))
    stopped = []
    monkeypatch.setattr(lifecycle, "stop", lambda data: stopped.append(data) or True)
    monkeypatch.setattr(cli, "DRAIN_POLL_S", 0.01)
    assert cli.main(["uninstall"]) == 0
    assert stopped == [] and fake_forwarder.events[0]["payload"]["name"] == "opt_out"


def test_signed_in_uninstall_stops_the_forwarder_after_the_drain_wait(fake_forwarder, monkeypatch):
    _sign_in(fake_forwarder.data)
    monkeypatch.setattr(lifecycle, "lock_held", lambda data: True)
    stopped = []
    monkeypatch.setattr(lifecycle, "stop", lambda data: stopped.append(data) or True)
    monkeypatch.setattr(cli, "DRAIN_WAIT_S", 0.1)
    monkeypatch.setattr(cli, "DRAIN_POLL_S", 0.01)
    started = time.monotonic()
    assert cli.main(["uninstall"]) == 0
    assert stopped == [fake_forwarder.data] and time.monotonic() - started < 5


def test_drain_wait_is_30_s():
    assert cli.DRAIN_WAIT_S == 30.0


def test_on_removes_opt_out_and_starts_without_reading_stdin(fake_forwarder, monkeypatch, capsys):
    (fake_forwarder.data / lifecycle.OPT_OUT_FILE).write_text("")
    monkeypatch.setattr(cli.sys, "stdin", _NoRead())
    assert cli.main(["on"]) == 0
    assert not (fake_forwarder.data / lifecycle.OPT_OUT_FILE).exists()
    assert "OTEL_EXPORTER_OTLP_ENDPOINT" in json.loads(fake_forwarder.settings.read_text())["env"]
    assert fake_forwarder.hooks == []


def test_uninstall_opts_out_stops_and_removes_the_shims(fake_forwarder, monkeypatch, tmp_path):
    shims = tmp_path / "harness" / "git-hooks"
    shims.mkdir(parents=True)
    (shims / "post-commit").write_text("#!/bin/sh\n")
    stopped = []
    monkeypatch.setattr(lifecycle, "stop", lambda data: stopped.append(Path(data)) or True)
    assert cli.main(["uninstall"]) == 0
    assert (fake_forwarder.data / lifecycle.OPT_OUT_FILE).exists() and fake_forwarder.events
    assert stopped == [fake_forwarder.data] and not shims.exists()


def test_status_reports_every_line_and_no_values(fake_forwarder, monkeypatch, capsys):
    key = settings.COMPETING_KEYS[0]
    fake_forwarder.settings.write_text(json.dumps({"env": {key: COLLECTOR}}))
    assert cli.main(["start"]) == 0
    auth.TokenCache(fake_forwarder.data).save(make_token("acc"), make_token("ref"), time.time() + 3600)
    fake_forwarder.spool.append("sess-1", {"signal": "event", "payload": {"name": "x"}})
    fake_forwarder.spool.close_all()
    (fake_forwarder.data / uploader.LAST_ACK_FILE).write_text("%f\n" % (time.time() - 120))
    monkeypatch.setattr(uploader, "probe_me", lambda cfg, cache: {"on_roster": True, "team": "team-invented"})
    capsys.readouterr()
    assert cli.main(["status"]) == 0
    out = capsys.readouterr().out
    for expected in (PLUGIN_VERSION, str(fake_forwarder.port), "1 closed batch", "oldest batch", "last ack",
                     "signed in", "on roster", "team-invented", "opt-out: no", key):
        assert expected in out
    assert COLLECTOR not in out and "example.invalid" not in out


def test_status_when_not_running_creates_no_files(configured, capsys):
    before = sorted(p.name for p in configured.data.iterdir())
    assert cli.main(["status"]) == 0
    out = capsys.readouterr().out
    assert "not running" in out and "needs sign-in" in out and "unknown" in out and "last ack: never" in out
    assert sorted(p.name for p in configured.data.iterdir()) == before
    assert port_is_free(configured.base)


def test_login_not_configured_prints_one_line_and_exits_1(data_dir, capsys):
    assert cli.main(["login"]) == 1
    out = capsys.readouterr().out
    assert out.count("\n") == 1 and list(data_dir.iterdir()) == []


def test_login_prints_the_device_message_and_polls(configured, fake_auth, monkeypatch, capsys):
    override = json.loads((configured.data / "override.json").read_text())
    (configured.data / "override.json").write_text(json.dumps(dict(override, auth_base_url=fake_auth.url)))
    fake_auth.script(DEVICECODE_PATH, (200, {
        "device_code": make_token("dev"), "user_code": "ABCD-EFGH",
        "verification_uri": "https://example.invalid/devicelogin", "expires_in": 900, "interval": 1,
        "message": "Open https://example.invalid/devicelogin and enter ABCD-EFGH."}))
    polled = []
    monkeypatch.setattr(auth, "poll_device_flow", lambda cfg, flow, cache=None: polled.append(flow) or True)
    assert cli.main(["login"]) == 0
    out = capsys.readouterr().out
    assert out.splitlines()[0] == "Open https://example.invalid/devicelogin and enter ABCD-EFGH."
    assert "signed in" in out and len(polled) == 1
    monkeypatch.setattr(auth, "poll_device_flow", lambda cfg, flow, cache=None: False)
    fake_auth.script(DEVICECODE_PATH, (200, dict(polled[0]._asdict(), expires_in=900, interval=1)))
    assert cli.main(["login"]) == 1
