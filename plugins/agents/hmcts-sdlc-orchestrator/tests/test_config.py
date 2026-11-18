import json
import stat
from pathlib import Path

from cpp_telemetry import config, log, paths

CONFIGURED = {
    "ingest_url": "http://127.0.0.1:18080",
    "tenant_id": "00000000-0000-0000-0000-000000000001",
    "client_id": "00000000-0000-0000-0000-000000000002",
    "api_app_id": "00000000-0000-0000-0000-000000000003",
}


def test_constants_are_empty_on_the_branch():
    from cpp_telemetry import config
    assert config.INGEST_URL == "" and config.TENANT_ID == "" and config.CLIENT_ID == "" and config.API_APP_ID == ""


def test_override_fills_config(tmp_path):
    (tmp_path / "override.json").write_text('{"ingest_url": "http://127.0.0.1:18080", "tenant_id": "00000000-0000-0000-0000-000000000001", "client_id": "00000000-0000-0000-0000-000000000002", "api_app_id": "00000000-0000-0000-0000-000000000003", "port": 4330}')
    cfg = config.load(tmp_path)
    assert cfg.is_configured() and cfg.port == 4330
    assert cfg.scope == "api://00000000-0000-0000-0000-000000000003/.default"
    assert cfg.auth_base_url == "https://login.microsoftonline.com/00000000-0000-0000-0000-000000000001"


def test_r22_keys_exact(tmp_path):
    keys = config.r22_keys(4328)
    assert keys["OTEL_EXPORTER_OTLP_ENDPOINT"] == "http://127.0.0.1:4328"
    assert len(keys) == 18 and "OTEL_SERVICE_NAME" not in keys and "OTEL_RESOURCE_ATTRIBUTES" not in keys
    assert keys["OTEL_LOGRECORD_ATTRIBUTE_VALUE_LENGTH_LIMIT"] == "2097152" and keys["OTEL_METRICS_INCLUDE_ACCOUNT_UUID"] == "0"


def test_r22_keys_full_set_and_fresh_copy():
    keys = config.r22_keys(4331)
    assert keys == {
        "CLAUDE_CODE_ENABLE_TELEMETRY": "1",
        "OTEL_METRICS_EXPORTER": "otlp",
        "OTEL_LOGS_EXPORTER": "otlp",
        "OTEL_TRACES_EXPORTER": "otlp",
        "OTEL_EXPORTER_OTLP_PROTOCOL": "http/json",
        "OTEL_EXPORTER_OTLP_ENDPOINT": "http://127.0.0.1:4331",
        "OTEL_METRIC_EXPORT_INTERVAL": "10000",
        "OTEL_LOGS_EXPORT_INTERVAL": "10000",
        "OTEL_METRICS_INCLUDE_REPOSITORY": "1",
        "OTEL_METRICS_INCLUDE_ENTRYPOINT": "1",
        "OTEL_LOG_USER_PROMPTS": "1",
        "OTEL_LOG_ASSISTANT_RESPONSES": "1",
        "OTEL_LOG_TOOL_DETAILS": "1",
        "OTEL_LOG_TOOL_CONTENT": "1",
        "OTEL_LOGRECORD_ATTRIBUTE_VALUE_LENGTH_LIMIT": "2097152",
        "CLAUDE_CODE_OTEL_CONTENT_MAX_LENGTH": "2097152",
        "CLAUDE_CODE_ENHANCED_TELEMETRY_BETA": "1",
        "OTEL_METRICS_INCLUDE_ACCOUNT_UUID": "0",
    }
    assert "OTEL_LOG_RAW_API_BODIES" not in keys
    keys["OTEL_EXPORTER_OTLP_ENDPOINT"] = "changed"
    assert config.r22_keys(4331)["OTEL_EXPORTER_OTLP_ENDPOINT"] == "http://127.0.0.1:4331"
    assert config.R22_KEYS["OTEL_EXPORTER_OTLP_ENDPOINT"] == "http://127.0.0.1:{port}"


def test_defaults_without_override(tmp_path):
    cfg = config.load(tmp_path)
    assert not cfg.is_configured()
    assert cfg.port == 4328 and cfg.port_scan == (4329, 4337)
    assert cfg.scope == "" and cfg.auth_base_url == ""
    assert (cfg.dwell_days, cfg.batch_max_bytes, cfg.batch_max_age_s) == (30, 1_000_000, 10)
    assert (cfg.spool_max_bytes, cfg.upload_max_bytes, cfg.export_interval_ms) == (2_000_000_000, 8_000_000, 10000)


def test_missing_api_app_id_keeps_config_dormant(tmp_path):
    partial = dict(CONFIGURED, api_app_id="")
    (tmp_path / "override.json").write_text(json.dumps(partial))
    assert not config.load(tmp_path).is_configured()


def test_explicit_scope_and_auth_base_url_win(tmp_path):
    override = dict(CONFIGURED, scope="api://custom/.default", auth_base_url="http://127.0.0.1:18081")
    (tmp_path / "override.json").write_text(json.dumps(override))
    cfg = config.load(tmp_path)
    assert cfg.scope == "api://custom/.default" and cfg.auth_base_url == "http://127.0.0.1:18081"


def test_direct_config_computes_derived_defaults():
    cfg = config.Config(**CONFIGURED)
    assert cfg.scope == "api://00000000-0000-0000-0000-000000000003/.default"
    assert cfg.auth_base_url == "https://login.microsoftonline.com/00000000-0000-0000-0000-000000000001"


def test_override_ignores_unknown_keys_and_wrong_types(tmp_path):
    override = dict(CONFIGURED, colour="blue", port="4330", batch_max_age_s=True, port_scan=[4340, 4345])
    (tmp_path / "override.json").write_text(json.dumps(override))
    cfg = config.load(tmp_path)
    assert cfg.is_configured() and not hasattr(cfg, "colour")
    assert cfg.port == 4328 and cfg.batch_max_age_s == 10
    assert cfg.port_scan == (4340, 4345)


def test_invalid_override_is_ignored_with_one_log_line(tmp_path):
    (tmp_path / "override.json").write_text('{"tenant_id": "00000000-0000-0000-0000-000000000001",')
    cfg = config.load(tmp_path)
    assert cfg.tenant_id == "" and not cfg.is_configured()
    lines = (tmp_path / "forwarder.log").read_text().splitlines()
    assert len(lines) == 1 and "override.json" in lines[0]
    assert "00000000" not in lines[0] and str(tmp_path) not in lines[0]


def test_non_object_override_is_ignored(tmp_path):
    (tmp_path / "override.json").write_text('["tenant_id"]')
    assert config.load(tmp_path) == config.Config()
    assert len((tmp_path / "forwarder.log").read_text().splitlines()) == 1


def test_load_without_argument_reads_the_data_dir(data_dir):
    (data_dir / "override.json").write_text(json.dumps(CONFIGURED))
    assert config.load().is_configured()


def test_data_dir_from_environment_is_created_0700(tmp_path, monkeypatch):
    target = tmp_path / "nested" / "data"
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(target))
    assert paths.data_dir() == target
    assert stat.S_IMODE(target.stat().st_mode) == 0o700


def test_existing_data_dir_is_tightened_to_0700(data_dir):
    data_dir.chmod(0o755)
    assert paths.data_dir() == data_dir
    assert stat.S_IMODE(data_dir.stat().st_mode) == 0o700


def test_data_dir_defaults_under_home():
    expected = Path.home() / ".claude" / "plugins" / "data" / "hmcts-sdlc-orchestrator"
    assert paths.data_dir() == expected
    assert stat.S_IMODE(expected.stat().st_mode) == 0o700


def test_plugin_root_from_environment_or_package(tmp_path, monkeypatch):
    plugin_dir = Path(__file__).resolve().parent.parent
    assert paths.plugin_root() == plugin_dir
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(tmp_path))
    assert paths.plugin_root() == tmp_path


def test_logger_writes_to_current_data_dir_only(tmp_path):
    first, second = tmp_path / "a", tmp_path / "b"
    first.mkdir()
    second.mkdir()
    log.get_logger(first).info("one")
    logger = log.get_logger(second)
    logger.info("two")
    log.get_logger(second).info("three")
    assert (first / "forwarder.log").read_text().count("\n") == 1
    assert (second / "forwarder.log").read_text().count("\n") == 2
    assert len(logger.handlers) == 1 and not logger.propagate
    handler = logger.handlers[0]
    assert (handler.maxBytes, handler.backupCount) == (5_000_000, 2)


def test_logger_creates_no_file_until_used(tmp_path):
    log.get_logger(tmp_path)
    assert not (tmp_path / "forwarder.log").exists()
