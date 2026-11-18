"""uninstall removes the data directory and reports each step; a dormant start takes back keys left in place."""
import json
from pathlib import Path

import pytest

from cpp_telemetry import auth, cli, lifecycle, settings
from tests.test_cli import COLLECTOR, _sign_in, configured, fake_forwarder  # noqa: F401 - fixtures

ENDPOINT = "OTEL_EXPORTER_OTLP_ENDPOINT"


def _applied(ff, capsys):
    """Start once so the keys are applied and recorded; the user's own collector key is moved aside."""
    key = settings.COMPETING_KEYS[0]
    ff.settings.write_text(json.dumps({"env": {key: COLLECTOR}}))
    assert cli.main(["start"]) == 0
    capsys.readouterr()
    assert ENDPOINT in json.loads(ff.settings.read_text())["env"]
    assert settings.managed_keys_path(ff.data).exists()
    return key


def test_uninstall_removes_the_whole_data_directory_and_reports_each_step(fake_forwarder, capsys):
    key = _applied(fake_forwarder, capsys)
    _sign_in(fake_forwarder.data)
    assert auth.TokenCache(fake_forwarder.data).path.exists()
    fake_forwarder.spool.append("sess-1", {"signal": "event", "payload": {"name": "x"}})
    fake_forwarder.spool.close_all()
    assert cli.main(["uninstall"]) == 0
    out = capsys.readouterr().out
    assert not fake_forwarder.data.exists()  # tokens, token, port, log, markers and spool all gone
    assert json.loads(fake_forwarder.settings.read_text())["env"] == {key: COLLECTOR}
    assert out.count("\n") == 1 and COLLECTOR not in out
    for part in ("setting(s) restored", "no forwarder running", "git hooks path restored", "data removed"):
        assert part in out, part


def test_uninstall_clears_the_token_cache_first(fake_forwarder, monkeypatch, capsys):
    _sign_in(fake_forwarder.data)
    cleared = []
    real = auth.TokenCache.clear
    monkeypatch.setattr(auth.TokenCache, "clear", lambda self: cleared.append(self.path.exists()) or real(self))
    assert cli.main(["uninstall"]) == 0
    assert cleared == [True] and not fake_forwarder.data.exists()


def test_uninstall_reports_a_forwarder_it_could_not_stop_and_keeps_the_data(fake_forwarder, monkeypatch, capsys):
    monkeypatch.setattr(lifecycle, "stop", lambda data: False)
    monkeypatch.setattr(lifecycle, "lock_held", lambda data: True)
    monkeypatch.setattr(lifecycle, "read_lock_pid", lambda data: 4242)
    monkeypatch.setattr(cli, "DRAIN_WAIT_S", 0.05)
    monkeypatch.setattr(cli, "DRAIN_POLL_S", 0.01)
    assert cli.main(["uninstall"]) == 0
    out = capsys.readouterr().out
    assert "forwarder still running (pid 4242)" in out and "forwarder stopped" not in out
    assert "data directory kept" in out and "data removed" not in out
    assert fake_forwarder.data.exists() and (fake_forwarder.data / lifecycle.OPT_OUT_FILE).exists()


def test_uninstall_names_the_keys_it_could_not_restore(fake_forwarder, monkeypatch, capsys):
    _applied(fake_forwarder, capsys)

    def fail(data):
        raise settings.SettingsError("settings.json cannot be read")

    monkeypatch.setattr(settings, "restore", fail)
    assert cli.main(["uninstall"]) == 0
    out = capsys.readouterr().out
    assert "could not restore" in out and ENDPOINT in out and COLLECTOR not in out
    assert "setting(s) restored" not in out


def test_uninstall_says_when_git_could_not_restore_the_hooks_path(fake_forwarder, monkeypatch, capsys):
    from cpp_telemetry import git_event

    monkeypatch.setattr(git_event, "uninstall_shims", lambda: False)
    assert cli.main(["uninstall"]) == 0
    out = capsys.readouterr().out
    assert "git hooks path left as is" in out and "git hooks path restored" not in out


@pytest.mark.parametrize("override", [None, "{not json"])
def test_dormant_start_with_keys_left_restores_them_and_stops_the_forwarder(fake_forwarder, capsys, override):
    key = _applied(fake_forwarder, capsys)
    path = fake_forwarder.data / "override.json"
    if override is None:
        path.unlink()  # the maintainer turned the override off
    else:
        path.write_text(override)
    assert cli.main(["start"]) == 0
    assert capsys.readouterr().out == ""
    assert json.loads(fake_forwarder.settings.read_text())["env"] == {key: COLLECTOR}
    assert not settings.managed_keys_path(fake_forwarder.data).exists()
    assert lifecycle.healthz(fake_forwarder.port, fake_forwarder.data) is None  # stopped through the proof path


def test_plain_dormant_start_touches_nothing(data_dir, capsys):
    assert cli.main(["start"]) == 0
    assert capsys.readouterr() == ("", "") and list(Path(data_dir).iterdir()) == []
