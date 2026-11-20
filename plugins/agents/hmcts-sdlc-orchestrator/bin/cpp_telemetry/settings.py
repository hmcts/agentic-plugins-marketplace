"""User settings merge: the R-22 env keys, marketplace autoUpdate, and restore.

``apply`` merges the R-22 keys into the user ``settings.json``, removes the
exporter keys that would compete with them (``COMPETING_KEYS``: per-signal
endpoints, headers, protocols, TLS material, insecure flags), and records in
``<data>/managed-keys.json`` every value it changed so that ``restore`` can put
it back. A key whose current value already equals the target is ``unchanged``
and is not recorded, so ``restore`` never touches it.

The record is cumulative: ``start`` runs ``apply`` every session. A recorded
prior is kept only while the current value is still the plugin's own earlier
value (``config.r22_keys(record["port"])``, or absence for a removed key);
when the developer changed the key in between, the prior is refreshed to the
developer's latest value.

Record shape::

    {"plugin_version": str, "port": int,
     "written": {KEY: {"prior": value | null}},   # null: the key was absent
     "removed": {KEY: {"prior": value}},          # competing keys taken out
     "autoupdate_prior": value | null,            # null: the field was absent
     "autoupdate_entry_created": bool,            # the marketplace entry was added
     "prior_endpoint": str | null}

``prior_endpoint`` is kept for ``status`` and ``restore`` only; nothing ever
posts to it (D-49, no chaining).

Every write goes to ``<name>.tmp-<pid>`` in the target's directory and then
``os.replace``; an existing file keeps its mode. A settings file that cannot be
read or parsed is never replaced: ``SettingsError`` is raised and the bytes stay.
"""
from __future__ import annotations

import json
import os
import stat
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import config, paths

MANAGED_KEYS_FILE = "managed-keys.json"
MARKETPLACE_NAME = "agentic-plugins-marketplace"
# The entry shape the CLI writes for this marketplace.
MARKETPLACE_SOURCE = {"source": "github", "repo": "hmcts/agentic-plugins-marketplace"}
ENTRY_PATH = "extraKnownMarketplaces.{}".format(MARKETPLACE_NAME)
AUTOUPDATE_PATH = ENTRY_PATH + ".autoUpdate"
ENDPOINT_KEY = "OTEL_EXPORTER_OTLP_ENDPOINT"
NEW_FILE_MODE = 0o600

_SIGNALS = ("LOGS", "METRICS", "TRACES")
_TLS = ("CERTIFICATE", "CLIENT_KEY", "CLIENT_CERTIFICATE")
# Exporter keys that would send a signal elsewhere, or send the developer's
# credentials or TLS material to the forwarder. Removed by apply, never written.
COMPETING_KEYS: Tuple[str, ...] = tuple(
    ["OTEL_EXPORTER_OTLP_{}_ENDPOINT".format(s) for s in _SIGNALS]
    + ["OTEL_EXPORTER_OTLP_HEADERS"]
    + ["OTEL_EXPORTER_OTLP_{}_HEADERS".format(s) for s in _SIGNALS]
    + ["OTEL_EXPORTER_OTLP_{}_PROTOCOL".format(s) for s in _SIGNALS]
    + ["OTEL_EXPORTER_OTLP_{}".format(t) for t in _TLS]
    + ["OTEL_EXPORTER_OTLP_{}_{}".format(s, t) for s in _SIGNALS for t in _TLS]
    + ["OTEL_EXPORTER_OTLP_INSECURE"]
    + ["OTEL_EXPORTER_OTLP_{}_INSECURE".format(s) for s in _SIGNALS]
)


class SettingsError(ValueError):
    """A settings or record file exists but cannot be read or safely edited."""


@dataclass
class ApplyResult:
    written: List[str] = field(default_factory=list)
    unchanged: List[str] = field(default_factory=list)
    # True when the marketplace entry's autoUpdate is true once apply returns,
    # whether it was already true or written now. False only when the user
    # settings hold a non-object extraKnownMarketplaces or entry, or a
    # non-boolean autoUpdate, which apply leaves alone.
    autoupdate_set: bool = False
    prior_endpoint: Optional[str] = None
    # Competing keys removed by this call; print names only, never values.
    removed: List[str] = field(default_factory=list)


def user_settings_path() -> Path:
    """``$CLAUDE_CONFIG_DIR/settings.json`` when set, else ``~/.claude/settings.json``."""
    env = os.environ.get("CLAUDE_CONFIG_DIR")
    base = Path(env) if env else Path.home() / ".claude"
    return base / "settings.json"


def managed_keys_path(data_dir: Path) -> Path:
    return Path(data_dir) / MANAGED_KEYS_FILE


def apply(port: int, data_dir: Path, plugin_version: str) -> ApplyResult:
    """Merge the R-22 keys for ``port``, remove competing keys, set autoUpdate."""
    path = user_settings_path()
    loaded = _load_settings(path)
    doc: Dict[str, Any] = {} if loaded is None else loaded
    old_record = _read_record(data_dir)
    record = old_record or {}
    ours_before = config.r22_keys(record["port"]) if old_record else {}
    written: Dict[str, Dict[str, Any]] = dict(record.get("written", {}))
    removed: Dict[str, Dict[str, Any]] = dict(record.get("removed", {}))

    result = ApplyResult()
    env = doc.setdefault("env", {})
    targets = config.r22_keys(port)
    for key, target in targets.items():
        if key in env and env[key] == target:
            result.unchanged.append(key)
            continue
        still_ours = key in written and key in env and env[key] == ours_before.get(key)
        if not still_ours:
            written[key] = {"prior": env.get(key)}
        env[key] = target
        result.written.append(key)
    for key in COMPETING_KEYS:
        if key in env:
            removed[key] = {"prior": env.pop(key)}
            result.removed.append(key)

    autoupdate_prior = record.get("autoupdate_prior")
    entry_created = bool(record.get("autoupdate_entry_created", False))
    autoupdate_written = False
    marketplaces = doc.get("extraKnownMarketplaces")
    if marketplaces is None:
        marketplaces = doc["extraKnownMarketplaces"] = {}
    if isinstance(marketplaces, dict):
        entry = marketplaces.get(MARKETPLACE_NAME)
        if entry is None:
            marketplaces[MARKETPLACE_NAME] = {"source": dict(MARKETPLACE_SOURCE), "autoUpdate": True}
            autoupdate_prior, entry_created, autoupdate_written = None, True, True
        elif isinstance(entry, dict):
            current = entry.get("autoUpdate")
            if old_record is None or current is not True:
                autoupdate_prior = current
            if current is None or current is False:
                entry["autoUpdate"] = True
                autoupdate_written = True
        entry = marketplaces.get(MARKETPLACE_NAME)
        result.autoupdate_set = isinstance(entry, dict) and entry.get("autoUpdate") is True

    prior = written.get(ENDPOINT_KEY, {}).get("prior")
    if isinstance(prior, str) and prior != targets[ENDPOINT_KEY]:
        result.prior_endpoint = prior

    new_record = {
        "plugin_version": plugin_version,
        "port": port,
        "written": written,
        "removed": removed,
        "autoupdate_prior": autoupdate_prior,
        "autoupdate_entry_created": entry_created,
        "prior_endpoint": result.prior_endpoint,
    }
    # Record first: a crash between the two writes leaves priors that equal the
    # current values, which restore handles; the reverse order would lose them.
    if new_record != old_record:
        _write_json(managed_keys_path(data_dir), new_record)
    if result.written or result.removed or autoupdate_written:
        _write_json(path, doc)
    return result


def restore(data_dir: Path) -> List[str]:
    """Put back every recorded prior, then delete the record.

    Written keys whose prior is null are deleted, the others set back; removed
    keys are put back; a marketplace entry the plugin created is removed, else
    autoUpdate is reset to its prior (the field is removed when that is null).
    Returns the env keys, ``ENTRY_PATH`` or ``AUTOUPDATE_PATH`` this call
    changed; ``[]`` when there is no record, in which case nothing is touched.
    """
    record = _read_record(data_dir)
    if record is None:
        return []
    path = user_settings_path()
    doc = _load_settings(path)
    changed: List[str] = []
    if doc is not None:
        env = doc.get("env", {})
        for key, item in record["written"].items():
            prior = item.get("prior")
            if prior is None:
                if key in env:
                    del env[key]
                    changed.append(key)
            elif key not in env or env[key] != prior:
                env[key] = prior
                changed.append(key)
        for key, item in record.get("removed", {}).items():
            if key not in env or env[key] != item.get("prior"):
                env[key] = item.get("prior")
                changed.append(key)
        if changed and "env" not in doc:
            doc["env"] = env
        changed.extend(_restore_autoupdate(doc, record))
        if changed:
            _write_json(path, doc)
    managed_keys_path(data_dir).unlink(missing_ok=True)
    return changed


def _restore_autoupdate(doc: Dict[str, Any], record: Dict[str, Any]) -> List[str]:
    marketplaces = doc.get("extraKnownMarketplaces")
    if not isinstance(marketplaces, dict):
        return []
    if record.get("autoupdate_entry_created"):
        if MARKETPLACE_NAME not in marketplaces:
            return []
        del marketplaces[MARKETPLACE_NAME]
        if not marketplaces:
            del doc["extraKnownMarketplaces"]
        return [ENTRY_PATH]
    entry = marketplaces.get(MARKETPLACE_NAME)
    if not isinstance(entry, dict):
        return []
    prior = record.get("autoupdate_prior")
    if prior is None:
        if "autoUpdate" not in entry:
            return []
        del entry["autoUpdate"]
    elif "autoUpdate" not in entry or entry["autoUpdate"] != prior:
        entry["autoUpdate"] = prior
    else:
        return []
    return [AUTOUPDATE_PATH]


def check_marketplace_version(plugin_root: Path) -> Optional[Tuple[str, str]]:
    """Return (installed version, marketplace version), or None when unknown.

    None when the marketplace clone is absent, or either version cannot be read.
    """
    manifest = (
        Path.home() / ".claude" / "plugins" / "marketplaces" / MARKETPLACE_NAME / ".claude-plugin" / "marketplace.json"
    )
    if not manifest.is_file():
        return None
    try:
        installed = json.loads((Path(plugin_root) / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        catalogue = json.loads(manifest.read_text(encoding="utf-8"))
        listed = [p for p in catalogue.get("plugins", []) if isinstance(p, dict) and p.get("name") == paths.PLUGIN_NAME]
        installed_version = installed.get("version")
        marketplace_version = listed[0].get("version") if listed else None
    except (OSError, ValueError, AttributeError):
        return None
    if isinstance(installed_version, str) and isinstance(marketplace_version, str):
        return installed_version, marketplace_version
    return None


def _load_settings(path: Path) -> Optional[Dict[str, Any]]:
    """Parse the settings file; None when absent, {} when empty."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except (OSError, UnicodeDecodeError) as exc:
        raise SettingsError("{} cannot be read ({}); left unchanged".format(path, type(exc).__name__))
    if not text.strip():
        return {}
    try:
        doc = json.loads(text)
    except ValueError:
        raise SettingsError("{} is not valid JSON; left unchanged".format(path))
    if not isinstance(doc, dict) or not isinstance(doc.get("env", {}), dict):
        raise SettingsError("{} is not a settings object with an env object; left unchanged".format(path))
    return doc


def _read_record(data_dir: Path) -> Optional[Dict[str, Any]]:
    path = managed_keys_path(data_dir)
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        raise SettingsError("{} cannot be read ({})".format(path, type(exc).__name__))
    if not isinstance(record, dict):
        raise SettingsError("{} does not have the managed-keys shape".format(path))
    port = record.get("port")
    maps = (record.get("written"), record.get("removed", {}))
    if not (isinstance(port, int) and not isinstance(port, bool)) or not all(
        isinstance(m, dict) and all(isinstance(v, dict) for v in m.values()) for m in maps
    ):
        raise SettingsError("{} does not have the managed-keys shape".format(path))
    return record


def _write_json(path: Path, doc: Dict[str, Any]) -> None:
    """Write ``doc`` atomically with 2-space indent and a trailing newline."""
    try:
        mode = stat.S_IMODE(os.stat(str(path)).st_mode)
    except FileNotFoundError:
        mode = NEW_FILE_MODE
        path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name("{}.tmp-{}".format(path.name, os.getpid()))
    text = json.dumps(doc, indent=2, ensure_ascii=False) + "\n"
    try:
        fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, NEW_FILE_MODE)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(str(tmp), mode)
        os.replace(str(tmp), str(path))
    except BaseException:
        try:
            os.unlink(str(tmp))
        except OSError:
            pass
        raise
