import sys
from pathlib import Path

import pytest

BIN_DIR = Path(__file__).resolve().parent.parent / "bin"
if str(BIN_DIR) not in sys.path:
    sys.path.insert(0, str(BIN_DIR))


@pytest.fixture(autouse=True)
def _isolated_environment(tmp_path, monkeypatch):
    """Keep every test away from the real home directory and plugin data."""
    home = tmp_path / "_home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("CLAUDE_PLUGIN_DATA", raising=False)
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
    # settings.user_settings_path() honours CLAUDE_CONFIG_DIR; never reach a real settings file.
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    # git config --global (uninstall, the shims) and the shims directory stay in temp files.
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(home / ".gitconfig"))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setenv("CPP_HARNESS_HOME", str(tmp_path / "_harness"))
    monkeypatch.delenv("CPP_HARNESS_TELEMETRY", raising=False)


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    path = tmp_path / "data"
    path.mkdir(mode=0o700)
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(path))
    return path
