"""User settings merge: the R-22 env keys, marketplace autoUpdate, and restore.

``apply`` merges the R-22 keys into the user ``settings.json`` and records, in
``<data>/managed-keys.json``, every key it changed together with that key's
value before the plugin first wrote it. A key whose current value already
equals the target is ``unchanged`` and is not recorded, so ``restore`` never
touches it. The record is cumulative: ``start`` runs ``apply`` every session,
and a later run (or a port change) keeps the first recorded prior of each key.

Record shape::

    {"plugin_version": str, "port": int,
     "written": {KEY: {"prior": value | null}},   # null: the key was absent
     "autoupdate_prior": false | null,            # null: autoUpdate not written
     "prior_endpoint": str | null}

``prior_endpoint`` is kept for ``status`` and ``restore`` only; nothing ever
posts to it (D-49, no chaining).

Every write goes to ``<name>.tmp-<pid>`` in the target's directory and then
``os.replace``; an existing file keeps its mode. A settings file that cannot be
parsed is never replaced: ``SettingsError`` is raised and the bytes stay.
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
AUTOUPDATE_PATH = "extraKnownMarketplaces.{}.autoUpdate".format(MARKETPLACE_NAME)
ENDPOINT_KEY = "OTEL_EXPORTER_OTLP_ENDPOINT"
NEW_FILE_MODE = 0o600


class SettingsError(ValueError):
    """A settings or record file exists but is not in a shape we can safely edit."""


@dataclass
class ApplyResult:
    written: List[str] = field(default_factory=list)
    unchanged: List[str] = field(default_factory=list)
    # True when the marketplace entry's autoUpdate is true once apply returns,
    # whether it was already true or written now. False when the user settings
    # hold no entry for the marketplace (or a non-boolean value): nothing written.
    autoupdate_set: bool = False
    prior_endpoint: Optional[str] = None


def user_settings_path() -> Path:
    """``$CLAUDE_CONFIG_DIR/settings.json`` when set, else ``~/.claude/settings.json``."""
    env = os.environ.get("CLAUDE_CONFIG_DIR")
    base = Path(env) if env else Path.home() / ".claude"
    return base / "settings.json"


def managed_keys_path(data_dir: Path) -> Path:
    return Path(data_dir) / MANAGED_KEYS_FILE


def apply(port: int, data_dir: Path, plugin_version: str) -> ApplyResult:
    """Merge the R-22 keys for ``port`` and set autoUpdate; record what changed."""
    path = user_settings_path()
    loaded = _load_settings(path)
    doc: Dict[str, Any] = {} if loaded is None else loaded
    old_record = _read_record(data_dir)
    record = old_record or {}
    recorded: Dict[str, Dict[str, Any]] = dict(record.get("written", {}))

    result = ApplyResult()
    env = doc.setdefault("env", {})
    targets = config.r22_keys(port)
    for key, target in targets.items():
        if key in env and env[key] == target:
            result.unchanged.append(key)
            continue
        if key not in recorded:
            recorded[key] = {"prior": env.get(key)}
        env[key] = target
        result.written.append(key)

    autoupdate_prior = record.get("autoupdate_prior")
    autoupdate_written = False
    entry = _marketplace_entry(doc)
    if entry is not None:
        if entry.get("autoUpdate", False) is False:
            entry["autoUpdate"] = True
            autoupdate_prior = False
            autoupdate_written = True
        result.autoupdate_set = entry.get("autoUpdate") is True

    prior = recorded.get(ENDPOINT_KEY, {}).get("prior")
    if isinstance(prior, str) and prior != targets[ENDPOINT_KEY]:
        result.prior_endpoint = prior

    new_record = {
        "plugin_version": plugin_version,
        "port": port,
        "written": recorded,
        "autoupdate_prior": autoupdate_prior,
        "prior_endpoint": result.prior_endpoint,
    }
    # Record first: a crash between the two writes leaves priors that equal the
    # current values, which restore handles; the reverse order would lose them.
    if new_record != old_record:
        _write_json(managed_keys_path(data_dir), new_record)
    if result.written or autoupdate_written:
        _write_json(path, doc)
    return result


def restore(data_dir: Path) -> List[str]:
    """Put back every recorded prior, then delete the record.

    Keys whose prior is null are deleted; the others are set back. autoUpdate is
    reset when ``autoupdate_prior`` is not null. Returns the env keys (and
    ``AUTOUPDATE_PATH``) whose value this call changed; ``[]`` when there is no
    record, in which case nothing is touched.
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
        if changed and "env" not in doc:
            doc["env"] = env
        autoupdate_prior = record.get("autoupdate_prior")
        entry = _marketplace_entry(doc)
        if autoupdate_prior is not None and entry is not None and entry.get("autoUpdate") is not autoupdate_prior:
            entry["autoUpdate"] = autoupdate_prior
            changed.append(AUTOUPDATE_PATH)
        if changed:
            _write_json(path, doc)
    managed_keys_path(data_dir).unlink()
    return changed


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


def _marketplace_entry(doc: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    marketplaces = doc.get("extraKnownMarketplaces")
    entry = marketplaces.get(MARKETPLACE_NAME) if isinstance(marketplaces, dict) else None
    return entry if isinstance(entry, dict) else None


def _load_settings(path: Path) -> Optional[Dict[str, Any]]:
    """Parse the settings file; None when absent, {} when empty."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
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
    except ValueError:
        raise SettingsError("{} is not valid JSON".format(path))
    written = record.get("written") if isinstance(record, dict) else None
    if not isinstance(written, dict) or not all(isinstance(v, dict) for v in written.values()):
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
