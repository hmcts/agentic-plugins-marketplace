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


DORMANT_EXIT = {"status": 0, "login": 1, "optout": 0, "on": 0, "uninstall": 0}


def test_every_subcommand_is_known():
    from cpp_telemetry import cli
    assert set(DORMANT_EXIT) | {"start", "forwarder", "ensure-running", "git-event"} == set(SUBCOMMANDS) \
        == set(cli.COMMANDS)


@pytest.mark.parametrize("kind", ["commit", "rewrite", "push"])
def test_dormant_git_event_is_silent_and_writes_no_files(kind, data_dir, capsys):
    from cpp_telemetry import cli
    assert cli.main(["git-event", kind, "origin"]) == 0
    assert capsys.readouterr() == ("", "")
    assert list(data_dir.iterdir()) == []


@pytest.mark.parametrize("name", sorted(DORMANT_EXIT))
def test_user_commands_say_one_line_when_dormant(name, data_dir, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("CPP_HARNESS_HOME", str(tmp_path / "harness"))
    from cpp_telemetry import cli
    assert cli.main([name]) == DORMANT_EXIT[name]
    out = capsys.readouterr().out
    assert out.count("\n") == 1 and out.startswith("cpp telemetry: ")
    assert not (data_dir / "spool").exists() and not (data_dir / "forwarder.lock").exists()


@pytest.mark.parametrize("name", ["forwarder", "ensure-running"])
def test_forwarder_and_ensure_running_are_dormant_without_override(name, data_dir, capsys):
    from cpp_telemetry import cli
    assert cli.main([name]) == 0
    captured = capsys.readouterr()
    assert (captured.out, captured.err) == ("", "")
    assert list(data_dir.iterdir()) == []


def test_dormant_start_does_not_create_the_data_dir(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(tmp_path / "absent" / "data"))
    from cpp_telemetry import cli
    assert cli.main(["start"]) == 0
    assert not (tmp_path / "absent").exists()
    assert capsys.readouterr().out == ""


def test_dormant_start_exits_0_when_the_data_dir_cannot_be_created(tmp_path, monkeypatch, capsys):
    (tmp_path / "file").write_text("x")
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(tmp_path / "file" / "data"))
    from cpp_telemetry import cli
    assert cli.main(["start"]) == 0
    captured = capsys.readouterr()
    assert (captured.out, captured.err) == ("", "")


def _run_package(args, tmp_path, package_dir=PACKAGE_DIR):
    env = dict(os.environ)
    env.pop("CLAUDE_PLUGIN_ROOT", None)
    env.pop("PYTHONDONTWRITEBYTECODE", None)
    env["HOME"] = str(tmp_path / "home")
    env["CLAUDE_PLUGIN_DATA"] = str(tmp_path / "data")
    return subprocess.run(
        [sys.executable, "-B", str(package_dir)] + args,
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


def test_directory_entry_point_with_dash_b_writes_no_bytecode_under_plugin_root(tmp_path):
    copy = tmp_path / "plugin" / "bin" / "cpp_telemetry"
    shutil.copytree(str(PACKAGE_DIR), str(copy), ignore=shutil.ignore_patterns("__pycache__"))
    result = _run_package(["start"], tmp_path, package_dir=copy)
    assert result.returncode == 0
    # Every call site runs the package with -B, so nothing at all is cached under the plugin root.
    assert [p.name for p in (tmp_path / "plugin").rglob("*.pyc")] == []
    assert "dont_write_bytecode" not in (PACKAGE_DIR / "__main__.py").read_text()


def test_package_directory_does_not_shadow_the_standard_library(tmp_path):
    copy = tmp_path / "plugin" / "bin" / "cpp_telemetry"
    shutil.copytree(str(PACKAGE_DIR), str(copy), ignore=shutil.ignore_patterns("__pycache__"))
    (copy / "json.py").write_text("raise SystemExit(7)\n")
    result = _run_package(["start"], tmp_path, package_dir=copy)
    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")
