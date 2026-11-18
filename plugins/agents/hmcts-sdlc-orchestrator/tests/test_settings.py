import json
import os
import stat
from pathlib import Path

import pytest

from cpp_telemetry import config, settings

PORT = 4328
OURS = "http://127.0.0.1:4328"
SINK = "http://localhost:4318"
SINK_LIMIT = "262144"
ENDPOINT = "OTEL_EXPORTER_OTLP_ENDPOINT"
LIMIT = "OTEL_LOGRECORD_ATTRIBUTE_VALUE_LENGTH_LIMIT"
MARKETPLACE = "agentic-plugins-marketplace"
INVENTED_SOURCE = {"source": "github", "repo": "example-org/example-marketplace"}
# Four R-22 keys an invented developer's own sink does not set.
MISSING = (
    "OTEL_LOG_TOOL_CONTENT",
    "CLAUDE_CODE_OTEL_CONTENT_MAX_LENGTH",
    "CLAUDE_CODE_ENHANCED_TELEMETRY_BETA",
    "OTEL_METRICS_INCLUDE_ACCOUNT_UUID",
)
CHANGED = (ENDPOINT, LIMIT)
EQUAL = tuple(k for k in config.r22_keys(PORT) if k not in MISSING and k not in CHANGED)


@pytest.fixture(autouse=True)
def _no_config_dir(monkeypatch):
    """conftest redirects HOME but not CLAUDE_CONFIG_DIR; never reach a real settings file."""
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)


def _settings_file() -> Path:
    return Path.home() / ".claude" / "settings.json"


def _write_settings(doc, mode=0o640) -> Path:
    path = _settings_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    os.chmod(str(path), mode)
    return path


def _read_settings():
    return json.loads(_settings_file().read_text(encoding="utf-8"))


def _record(data_dir):
    return json.loads(settings.managed_keys_path(data_dir).read_text(encoding="utf-8"))


def _own_sink_doc(auto_update=True):
    env = {k: v for k, v in config.r22_keys(PORT).items() if k not in MISSING}
    env[ENDPOINT] = SINK
    env[LIMIT] = SINK_LIMIT
    env["EXAMPLE_TOOL_HOME"] = "/opt/example-tool"
    entry = {"source": dict(INVENTED_SOURCE)}
    if auto_update is not None:
        entry["autoUpdate"] = auto_update
    return {
        "env": env,
        "permissions": {"allow": ["Bash(ls:*)", "Read(./docs/**)"], "deny": ["Read(./.env)"]},
        "extraKnownMarketplaces": {
            MARKETPLACE: entry,
            "example-other-marketplace": {"source": {"source": "directory", "path": "/opt/example"}},
        },
        "model": "example-model",
        "statusLine": {"type": "command", "command": "example-status"},
    }


@pytest.mark.parametrize("content", [None, "", "{}\n"], ids=["missing", "zero-bytes", "empty-object"])
def test_apply_writes_all_18_keys_into_empty_file(data_dir, content):
    if content is not None:
        _settings_file().parent.mkdir(parents=True)
        _settings_file().write_text(content, encoding="utf-8")

    result = settings.apply(PORT, data_dir, "1.1.0")

    assert _read_settings() == {"env": config.r22_keys(PORT)}
    assert result.written == list(config.r22_keys(PORT)) and result.unchanged == []
    assert result.prior_endpoint is None and result.autoupdate_set is False
    assert _record(data_dir) == {
        "plugin_version": "1.1.0",
        "port": PORT,
        "written": {k: {"prior": None} for k in config.r22_keys(PORT)},
        "autoupdate_prior": None,
        "prior_endpoint": None,
    }


def test_apply_is_atomic_and_keeps_other_content(data_dir, monkeypatch):
    before = _own_sink_doc()
    path = _write_settings(before, mode=0o640)
    calls = []
    real_replace = os.replace

    def spy(src, dst):
        calls.append((Path(src), Path(dst)))
        assert Path(src).exists()
        real_replace(src, dst)

    monkeypatch.setattr(os, "replace", spy)

    settings.apply(PORT, data_dir, "1.1.0")

    assert (path.parent / "settings.json.tmp-{}".format(os.getpid()), path) in calls
    after = _read_settings()
    assert list(after) == list(before)
    for key in before:
        if key != "env":
            assert json.dumps(after[key]) == json.dumps(before[key])
    assert after["env"]["EXAMPLE_TOOL_HOME"] == "/opt/example-tool"
    assert {k: after["env"][k] for k in config.r22_keys(PORT)} == config.r22_keys(PORT)
    assert stat.S_IMODE(path.stat().st_mode) == 0o640
    assert list(path.parent.glob("settings.json.tmp-*")) == []
    assert path.read_text(encoding="utf-8") == json.dumps(after, indent=2) + "\n"


def test_apply_marks_pre_existing_equal_keys_unchanged(data_dir):
    _write_settings(_own_sink_doc())

    result = settings.apply(PORT, data_dir, "1.1.0")

    assert sorted(result.written) == sorted(MISSING + CHANGED)
    assert sorted(result.unchanged) == sorted(EQUAL) and len(result.unchanged) == 12
    assert result.prior_endpoint == SINK
    record = _record(data_dir)
    assert record["written"] == dict(
        {k: {"prior": None} for k in MISSING}, **{ENDPOINT: {"prior": SINK}, LIMIT: {"prior": SINK_LIMIT}}
    )
    assert record["prior_endpoint"] == SINK and record["port"] == PORT and record["plugin_version"] == "1.1.0"
    assert _read_settings()["env"][ENDPOINT] == OURS


def test_optout_restores_prior_values_and_deletes_only_new_keys(data_dir):
    before = _own_sink_doc()
    _write_settings(before)
    settings.apply(PORT, data_dir, "1.1.0")

    restored = settings.restore(data_dir)

    after = _read_settings()
    assert after["env"][ENDPOINT] == SINK and after["env"][LIMIT] == SINK_LIMIT
    assert not any(k in after["env"] for k in MISSING)
    assert {k: after["env"][k] for k in EQUAL} == {k: before["env"][k] for k in EQUAL}
    assert after == before
    assert sorted(restored) == sorted(MISSING + CHANGED)
    assert not settings.managed_keys_path(data_dir).exists()


def test_restore_never_touches_keys_that_were_unchanged(data_dir):
    _write_settings(_own_sink_doc())
    settings.apply(PORT, data_dir, "1.1.0")
    doc = _read_settings()
    doc["env"]["OTEL_METRIC_EXPORT_INTERVAL"] = "5000"
    _write_settings(doc)

    settings.restore(data_dir)

    assert _read_settings()["env"]["OTEL_METRIC_EXPORT_INTERVAL"] == "5000"


def test_repeated_apply_keeps_first_priors_across_a_port_change(data_dir):
    before = _own_sink_doc()
    path = _write_settings(before)
    settings.apply(PORT, data_dir, "1.1.0")
    applied_text = path.read_text(encoding="utf-8")
    applied_mtime = path.stat().st_mtime_ns

    again = settings.apply(PORT, data_dir, "1.1.0")

    assert again.written == [] and len(again.unchanged) == 18
    assert again.prior_endpoint == SINK and again.autoupdate_set is True
    assert path.read_text(encoding="utf-8") == applied_text and path.stat().st_mtime_ns == applied_mtime

    moved = settings.apply(4329, data_dir, "1.1.0")

    assert moved.written == [ENDPOINT] and moved.prior_endpoint == SINK
    record = _record(data_dir)
    assert record["port"] == 4329 and record["written"][ENDPOINT] == {"prior": SINK}
    settings.restore(data_dir)
    assert _read_settings() == before


@pytest.mark.parametrize("prior", [None, False], ids=["absent", "false"])
def test_autoupdate_true_written_when_absent_and_restored(data_dir, prior):
    _write_settings(_own_sink_doc(auto_update=prior))

    result = settings.apply(PORT, data_dir, "1.1.0")

    entry = _read_settings()["extraKnownMarketplaces"][MARKETPLACE]
    assert entry == {"source": INVENTED_SOURCE, "autoUpdate": True}
    assert result.autoupdate_set is True and _record(data_dir)["autoupdate_prior"] is False

    restored = settings.restore(data_dir)

    entry = _read_settings()["extraKnownMarketplaces"][MARKETPLACE]
    assert entry["source"] == INVENTED_SOURCE and entry.get("autoUpdate", False) is False
    assert "extraKnownMarketplaces.{}.autoUpdate".format(MARKETPLACE) in restored


def test_autoupdate_already_true_is_not_recorded(data_dir):
    _write_settings(_own_sink_doc(auto_update=True))

    result = settings.apply(PORT, data_dir, "1.1.0")

    assert result.autoupdate_set is True and _record(data_dir)["autoupdate_prior"] is None
    settings.restore(data_dir)
    assert _read_settings()["extraKnownMarketplaces"][MARKETPLACE]["autoUpdate"] is True


def test_autoupdate_not_written_when_marketplace_entry_absent(data_dir):
    doc = _own_sink_doc()
    del doc["extraKnownMarketplaces"][MARKETPLACE]
    _write_settings(doc)

    result = settings.apply(PORT, data_dir, "1.1.0")

    assert result.autoupdate_set is False and _record(data_dir)["autoupdate_prior"] is None
    assert MARKETPLACE not in _read_settings()["extraKnownMarketplaces"]


def test_restore_without_record_changes_nothing(data_dir):
    path = _write_settings(_own_sink_doc())
    original = path.read_bytes()

    assert settings.restore(data_dir) == []
    assert path.read_bytes() == original


@pytest.mark.parametrize("content", ["{not json", "[]\n", '{"env": ["x"]}\n'], ids=["invalid", "array", "env-array"])
def test_unparseable_settings_are_left_alone(data_dir, content):
    path = _settings_file()
    path.parent.mkdir(parents=True)
    path.write_text(content, encoding="utf-8")

    with pytest.raises(settings.SettingsError):
        settings.apply(PORT, data_dir, "1.1.0")

    assert path.read_text(encoding="utf-8") == content
    assert not settings.managed_keys_path(data_dir).exists()
    assert list(path.parent.glob("settings.json.tmp-*")) == []


def test_user_settings_path_honours_claude_config_dir(tmp_path, monkeypatch, data_dir):
    assert settings.user_settings_path() == Path.home() / ".claude" / "settings.json"
    sandbox = tmp_path / "sandbox-config"
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(sandbox))

    assert settings.user_settings_path() == sandbox / "settings.json"
    settings.apply(PORT, data_dir, "1.1.0")
    assert json.loads((sandbox / "settings.json").read_text(encoding="utf-8"))["env"][ENDPOINT] == OURS
    assert not _settings_file().exists()


def _plugin_root(tmp_path, version="1.1.0") -> Path:
    root = tmp_path / "plugin-root"
    (root / ".claude-plugin").mkdir(parents=True)
    (root / ".claude-plugin" / "plugin.json").write_text(json.dumps({"name": "hmcts-sdlc-orchestrator", "version": version}))
    return root


def test_marketplace_version_none_when_clone_absent(tmp_path):
    assert settings.check_marketplace_version(_plugin_root(tmp_path)) is None


def test_marketplace_version_reads_installed_and_marketplace_versions(tmp_path):
    manifest = Path.home() / ".claude" / "plugins" / "marketplaces" / MARKETPLACE / ".claude-plugin" / "marketplace.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps({"plugins": [
        {"name": "example-other-plugin", "version": "9.9.9"},
        {"name": "hmcts-sdlc-orchestrator", "version": "1.2.0"},
    ]}))

    assert settings.check_marketplace_version(_plugin_root(tmp_path)) == ("1.1.0", "1.2.0")
