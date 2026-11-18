"""Locations of the plugin's data directory and installed root."""
from __future__ import annotations

import os
from pathlib import Path

PLUGIN_NAME = "hmcts-sdlc-orchestrator"


def data_dir(create: bool = True) -> Path:
    """Return the data directory, creating it on demand with mode 0700.

    ``CLAUDE_PLUGIN_DATA`` wins when set; otherwise the per-user default under
    ``~/.claude/plugins/data``. The directory holds spooled telemetry and the
    sign-in cache, so an existing directory is tightened to 0700 as well.
    ``create=False`` only resolves the path (a dormant run creates nothing).
    """
    env = os.environ.get("CLAUDE_PLUGIN_DATA")
    path = Path(env) if env else Path.home() / ".claude" / "plugins" / "data" / PLUGIN_NAME
    if not create:
        return path
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        os.chmod(str(path), 0o700)
    except OSError:
        pass
    return path


def plugin_root() -> Path:
    """Return the installed plugin root (``CLAUDE_PLUGIN_ROOT`` or bin/..)."""
    env = os.environ.get("CLAUDE_PLUGIN_ROOT")
    return Path(env) if env else Path(__file__).resolve().parents[2]
