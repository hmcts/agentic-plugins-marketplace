"""Forwarder configuration: shipped constants, local override, derived values.

The four identity constants ship empty, so an installed plugin is dormant
until a local ``<data>/override.json`` supplies all four. ``API_APP_ID`` is the
fourth constant next to the ingest URL, tenant id and client id: the token
scope names the ingest API's application id, which is not the client id of the
sign-in application.

``override.json`` may set any ``Config`` field by name. Unknown keys are
ignored; a value whose type does not match the field's default is ignored; a
file that is not a JSON object is ignored with one log line. A value out of
range is ignored with one log line: ``port`` and both ``port_scan`` ends must lie
in 1024-65535 with the scan ordered low to high; every other number must be
greater than zero. Reading the override never creates the data directory.
"""
from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from . import log, paths

INGEST_URL = ""
TENANT_ID = ""
CLIENT_ID = ""
API_APP_ID = ""

OVERRIDE_FILE = "override.json"

# R-22: the settings env keys `start` writes. Never OTEL_SERVICE_NAME,
# OTEL_RESOURCE_ATTRIBUTES or OTEL_LOG_RAW_API_BODIES.
R22_KEYS: Dict[str, str] = {
    "CLAUDE_CODE_ENABLE_TELEMETRY": "1",
    "OTEL_METRICS_EXPORTER": "otlp",
    "OTEL_LOGS_EXPORTER": "otlp",
    "OTEL_TRACES_EXPORTER": "otlp",
    "OTEL_EXPORTER_OTLP_PROTOCOL": "http/json",
    "OTEL_EXPORTER_OTLP_ENDPOINT": "http://127.0.0.1:{port}",
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


def r22_keys(port: int) -> Dict[str, str]:
    """Return a fresh copy of the R-22 keys with the endpoint port filled in."""
    keys = dict(R22_KEYS)
    keys["OTEL_EXPORTER_OTLP_ENDPOINT"] = R22_KEYS["OTEL_EXPORTER_OTLP_ENDPOINT"].format(port=port)
    return keys


@dataclass
class Config:
    port: int = 4328
    port_scan: Tuple[int, int] = (4329, 4337)
    ingest_url: str = ""
    tenant_id: str = ""
    client_id: str = ""
    api_app_id: str = ""
    scope: str = ""
    auth_base_url: str = ""
    dwell_days: int = 30
    batch_max_bytes: int = 1_000_000
    batch_max_age_s: int = 10
    spool_max_bytes: int = 2_000_000_000
    upload_max_bytes: int = 8_000_000
    export_interval_ms: int = 10000

    def __post_init__(self) -> None:
        if not self.scope and self.api_app_id:
            self.scope = "api://{}/.default".format(self.api_app_id)
        if not self.auth_base_url and self.tenant_id:
            self.auth_base_url = "https://login.microsoftonline.com/{}".format(self.tenant_id)

    def is_configured(self) -> bool:
        return all((self.ingest_url, self.tenant_id, self.client_id, self.api_app_id))


def load(data_dir: Optional[Path] = None) -> Config:
    """Build the configuration from the constants and ``<data>/override.json``."""
    directory = paths.data_dir(create=False) if data_dir is None else Path(data_dir)
    values: Dict[str, Any] = {
        "ingest_url": INGEST_URL,
        "tenant_id": TENANT_ID,
        "client_id": CLIENT_ID,
        "api_app_id": API_APP_ID,
    }
    values.update(_read_override(directory))
    return Config(**values)


def _read_override(directory: Path) -> Dict[str, Any]:
    path = directory / OVERRIDE_FILE
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, NotADirectoryError):
        # No override, or no data directory at all (dormant): nothing to read, nothing to log.
        return {}
    except (OSError, ValueError):
        data = None
    logger = log.get_logger(directory)
    if not isinstance(data, dict):
        logger.warning("override.json ignored: not a readable JSON object")
        return {}
    accepted: Dict[str, Any] = {}
    for field in dataclasses.fields(Config):
        if field.name not in data:
            continue
        value = _typed(data[field.name], field.default)
        if value is None:
            logger.warning("override.json key ignored: %s has the wrong type", field.name)
        elif not _in_range(field.name, value):
            logger.warning("override.json key ignored: %s is out of range", field.name)
        else:
            accepted[field.name] = value
    return accepted


PORT_MIN = 1024
PORT_MAX = 65535


def _in_range(name: str, value: Any) -> bool:
    if name == "port":
        return PORT_MIN <= value <= PORT_MAX
    if name == "port_scan":
        low, high = value
        return PORT_MIN <= low <= high <= PORT_MAX
    if isinstance(value, int):
        return value > 0
    return True


def _typed(value: Any, default: Any) -> Any:
    """Return ``value`` in the default's type, or None when it does not fit."""
    if isinstance(default, tuple):
        if isinstance(value, (list, tuple)) and len(value) == len(default) and all(_is_int(v) for v in value):
            return tuple(value)
        return None
    if isinstance(default, int):
        return value if _is_int(value) else None
    if isinstance(default, str):
        return value if isinstance(value, str) else None
    return None


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)
