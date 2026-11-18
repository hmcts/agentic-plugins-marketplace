import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

PACKAGE_DIR = Path(__file__).resolve().parent.parent / "bin" / "cpp_telemetry"
SUBCOMMANDS = ["start", "forwarder", "status", "login", "optout", "on", "git-event", "uninstall", "ensure-running"]


def test_start_is_dormant_without_override(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(tmp_path / "data"))
    monkeypatch.setenv("HOME", str(tmp_path / "home")); (tmp_path / "home" / ".claude").mkdir(parents=True)
    (tmp_path / "home" / ".claude" / "settings.json").write_text('{"env": {"X": "1"}}')
    from cpp_telemetry import cli
    assert cli.main(["start"]) == 0
    assert capsys.readouterr().out == ""
    assert json.loads((tmp_path / "home" / ".claude" / "settings.json").read_text()) == {"env": {"X": "1"}}
    assert not (tmp_path / "data" / "spool").exists() and not (tmp_path / "data" / "forwarder.lock").exists()


def test_dormant_start_writes_no_files(data_dir, capsys):
    from cpp_telemetry import cli
    assert cli.main(["start"]) == 0
    captured = capsys.readouterr()
    assert captured.out == "" and captured.err == ""
    assert list(data_dir.iterdir()) == []


@pytest.mark.parametrize("argv", [["bogus"], []])
def test_unknown_or_missing_subcommand_exits_2(argv):
    from cpp_telemetry import cli
    assert cli.main(argv) == 2


@pytest.mark.parametrize("name", SUBCOMMANDS)
def test_every_subcommand_is_accepted(name, data_dir):
    from cpp_telemetry import cli
    assert cli.main([name]) == 0


def _run_package(args, tmp_path, package_dir=PACKAGE_DIR):
    env = dict(os.environ)
    env.pop("CLAUDE_PLUGIN_ROOT", None)
    env.pop("PYTHONDONTWRITEBYTECODE", None)
    env["HOME"] = str(tmp_path / "home")
    env["CLAUDE_PLUGIN_DATA"] = str(tmp_path / "data")
    return subprocess.run(
        [sys.executable, str(package_dir)] + args,
        env=env,
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_directory_entry_point_start_is_dormant(tmp_path):
    result = _run_package(["start"], tmp_path)
    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")


def test_directory_entry_point_unknown_subcommand_exits_2(tmp_path):
    result = _run_package(["bogus"], tmp_path)
    assert result.returncode == 2 and "invalid choice" in result.stderr


def test_directory_entry_point_writes_no_module_bytecode_under_plugin_root(tmp_path):
    copy = tmp_path / "plugin" / "bin" / "cpp_telemetry"
    shutil.copytree(str(PACKAGE_DIR), str(copy), ignore=shutil.ignore_patterns("__pycache__"))
    result = _run_package(["start"], tmp_path, package_dir=copy)
    assert result.returncode == 0
    # The interpreter caches __main__ itself before any package code runs;
    # only a caller passing -B avoids that. No package module may be cached.
    cached = [p.name for p in (tmp_path / "plugin").rglob("*.pyc")]
    assert all(name.startswith("__main__.") for name in cached)
