"""The two hook scripts, hooks.json and the /telemetry command, run with bash, a stub python3 and a stub server."""
import json
import os
import shutil
import signal
import stat
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
START = PLUGIN_ROOT / "hooks" / "telemetry-start.sh"
NUDGE = PLUGIN_ROOT / "hooks" / "telemetry-nudge.sh"
HOOKS_JSON = PLUGIN_ROOT / "hooks" / "hooks.json"
COMMAND = PLUGIN_ROOT / "commands" / "telemetry.md"
BASH = shutil.which("bash") or "/bin/bash"
HOOK = json.dumps({"hook_event_name": "Stop", "session_id": "sess-1", "stop_hook_active": False})

STUB_PYTHON = r"""#!/bin/bash
printf '%s\n' "$*" >> "$STUB_LOG"
printf '%s\n' "$PWD" >> "$STUB_CWD"
case " $* " in
  *" ensure-running "*)
    if [ -n "${STUB_PIDFILE:-}" ]; then echo $$ > "$STUB_PIDFILE"; exec "$REAL_PYTHON" -c "import time; time.sleep(8)"; fi
    if [ -n "${STUB_TOKEN:-}" ] && [ ! -e "$STUB_DATA/token" ]; then printf '%s\n' "$STUB_TOKEN" > "$STUB_DATA/token"; fi
    if [ -n "${STUB_PORT:-}" ]; then printf '%s\n' "$STUB_PORT"; fi
    exit 0 ;;
  *" start"*)
    "$REAL_PYTHON" -c "import shutil, sys; shutil.copyfileobj(sys.stdin, open(sys.argv[1], 'w'))" "$STUB_STDIN"
    exit 0 ;;
esac
exec "$REAL_PYTHON" "$@"
"""

# The guard section of hooks.json before this task, byte for byte.
GUARDS = """{
  "description": "CPP security guardrails: block dangerous bash commands, guard sensitive file paths, and prevent PII and secrets from appearing in prompts or written files.",
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          { "type": "command", "command": "${CLAUDE_PLUGIN_ROOT}/hooks/block-pii.sh" },
          { "type": "command", "command": "${CLAUDE_PLUGIN_ROOT}/hooks/block-secrets.sh" }
        ]
      }
    ],
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          { "type": "command", "command": "${CLAUDE_PLUGIN_ROOT}/hooks/guard-bash.sh" }
        ]
      },
      {
        "matcher": "Read|Write|Edit",
        "hooks": [
          { "type": "command", "command": "${CLAUDE_PLUGIN_ROOT}/hooks/guard-paths.sh" }
        ]
      },
      {
        "matcher": "Write|Edit",
        "hooks": [
          { "type": "command", "command": "${CLAUDE_PLUGIN_ROOT}/hooks/block-pii.sh" },
          { "type": "command", "command": "${CLAUDE_PLUGIN_ROOT}/hooks/block-secrets.sh" }
        ]
      }
    ]"""


def _token():
    return "".join("%x" % (i % 16) for i in range(32))  # 32 hex characters, built at run time


class _Recorder(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        self.server.calls.append((self.path, {k.lower(): v for k, v in self.headers.items()}, body))
        self.send_response(200)
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"{}")

    def log_message(self, *args):
        pass


@pytest.fixture
def server():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Recorder)
    srv.calls = []
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    yield srv
    srv.shutdown()
    srv.server_close()
    thread.join(5)


@pytest.fixture
def env(tmp_path):
    stub = tmp_path / "stub-bin"
    stub.mkdir()
    (stub / "python3").write_text(STUB_PYTHON)
    (stub / "python3").chmod(0o755)
    data = tmp_path / "data"
    data.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    return {
        "PATH": "%s:/usr/bin:/bin" % stub,
        "HOME": str(home),
        "CLAUDE_PLUGIN_ROOT": str(PLUGIN_ROOT),
        "CLAUDE_PLUGIN_DATA": str(data),
        "REAL_PYTHON": sys.executable,
        "STUB_LOG": str(tmp_path / "stub.log"),
        "STUB_CWD": str(tmp_path / "stub.cwd"),
        "STUB_STDIN": str(tmp_path / "stub.stdin"),
        "STUB_DATA": str(data),
        "http_proxy": "http://127.0.0.1:9",  # a proxy that would swallow the token: it must be bypassed
        "HTTP_PROXY": "http://127.0.0.1:9",
    }


def _run(script, env, stdin=HOOK, timeout=10, cwd=None):
    started = time.monotonic()
    done = subprocess.run([BASH, str(script)], input=stdin, env=env, capture_output=True, text=True,
                          timeout=timeout, cwd=cwd)
    return done, time.monotonic() - started


def _stub_cwds(env):
    path = Path(env["STUB_CWD"])
    return set(path.read_text().splitlines()) if path.exists() else set()


@pytest.fixture
def hostile_cwd(tmp_path):
    """A session cwd holding a planted ``urllib`` package that leaves a marker when imported."""
    cwd = tmp_path / "repo-with-plant"
    (cwd / "urllib").mkdir(parents=True)
    marker = tmp_path / "planted-import-ran"
    (cwd / "urllib" / "__init__.py").write_text("open(%r, 'w').write('imported')\n" % str(marker))
    return cwd, marker


def _stub_calls(env):
    path = Path(env["STUB_LOG"])
    return path.read_text().splitlines() if path.exists() else []


# ---------------------------------------------------------------- start script


def test_start_script_exits_0_when_off(env):
    env["CPP_HARNESS_TELEMETRY"] = "off"
    done, _ = _run(START, env)
    assert (done.returncode, done.stdout, done.stderr) == (0, "", "")
    assert _stub_calls(env) == []


def test_start_script_prints_one_line_without_python(env, tmp_path):
    empty = tmp_path / "empty-bin"
    empty.mkdir()
    env["PATH"] = str(empty)
    done, _ = _run(START, env)
    assert done.returncode == 0
    assert done.stdout == "cpp telemetry: python3 3.9+ not found; telemetry off for this session\n"


def test_start_script_runs_start_isolated_from_the_session_cwd_and_passes_stdin(env, hostile_cwd):
    cwd, _ = hostile_cwd
    done, _ = _run(START, env, cwd=str(cwd))
    assert (done.returncode, done.stderr) == (0, "")
    calls = _stub_calls(env)
    assert all(call.startswith("-I -B ") for call in calls)
    assert calls[-1] == "-I -B %s/bin/cpp_telemetry start" % PLUGIN_ROOT
    assert Path(env["STUB_STDIN"]).read_text() == HOOK
    assert _stub_cwds(env) == {env["CLAUDE_PLUGIN_DATA"]}


def test_scripts_fall_back_to_root_when_the_data_dir_is_missing(env, server, hostile_cwd):
    cwd, _ = hostile_cwd
    env["CLAUDE_PLUGIN_DATA"] = str(Path(env["STUB_DATA"]) / "absent")
    _run(START, env, cwd=str(cwd))
    _run(NUDGE, env, cwd=str(cwd))
    assert _stub_cwds(env) == {"/"}


# ---------------------------------------------------------------- nudge script


def test_nudge_script_posts_stdin_to_hook_endpoint(env, server):
    Path(env["STUB_DATA"], "token").write_text(_token() + "\n")
    env["STUB_PORT"] = str(server.server_address[1])
    done, elapsed = _run(NUDGE, env)
    assert (done.returncode, done.stdout, done.stderr) == (0, "", "")
    ((path, headers, body),) = server.calls
    assert path == "/hook" and body.decode() == HOOK
    assert headers["content-type"] == "application/json" and headers["x-cpp-telemetry-token"] == _token()
    assert _stub_calls(env) == ["-I -B %s/bin/cpp_telemetry ensure-running" % PLUGIN_ROOT]  # proof check first
    assert elapsed < 3


def test_nudge_without_curl_posts_through_isolated_python(env, server, hostile_cwd):
    cwd, marker = hostile_cwd
    env["PATH"] = str(Path(env["STUB_LOG"]).parent / "stub-bin")  # python3 stub only: no curl
    env["STUB_TOKEN"] = _token()  # the token appears only once ensure-running has run
    env["STUB_PORT"] = str(server.server_address[1])
    done, _ = _run(NUDGE, env, cwd=str(cwd))
    assert (done.returncode, done.stdout, done.stderr) == (0, "", "")
    ((path, headers, body),) = server.calls
    assert path == "/hook" and body.decode() == HOOK and headers["x-cpp-telemetry-token"] == _token()
    calls = _stub_calls(env)
    assert calls[0].endswith("ensure-running") and calls[1].startswith("-I -B - ")
    assert not marker.exists()  # the planted urllib in the session cwd was never imported
    assert _stub_cwds(env) == {env["CLAUDE_PLUGIN_DATA"]}


def test_nudge_never_posts_to_an_unverified_port(env, server):
    data = Path(env["STUB_DATA"])
    (data / "token").write_text(_token())
    (data / "port").write_text(str(server.server_address[1]))  # recorded, but ensure-running vouches for nothing
    done, _ = _run(NUDGE, env)
    assert (done.returncode, done.stdout, done.stderr) == (0, "", "")
    assert server.calls == []


@pytest.mark.parametrize("how", ["off", "opt-out"])
def test_nudge_does_nothing_when_off_or_opted_out(env, server, how):
    Path(env["STUB_DATA"], "token").write_text(_token())
    env["STUB_PORT"] = str(server.server_address[1])
    if how == "off":
        env["CPP_HARNESS_TELEMETRY"] = "off"
    else:
        Path(env["STUB_DATA"], "opt-out").write_text("")
    done, _ = _run(NUDGE, env)
    assert (done.returncode, done.stdout, done.stderr) == (0, "", "")
    assert server.calls == [] and _stub_calls(env) == []


@pytest.mark.parametrize("event, low, high", [("Stop", 1.5, 2.6), ("SubagentStop", 1.5, 2.6),
                                              ("SessionEnd", 3.5, 4.6)])
def test_nudge_is_silent_and_bounded_when_python_hangs(env, tmp_path, event, low, high):
    env["STUB_PIDFILE"] = str(tmp_path / "stub.pid")
    try:
        done, elapsed = _run(NUDGE, env, stdin=json.dumps({"hook_event_name": event, "session_id": "s"}))
        assert (done.returncode, done.stdout, done.stderr) == (0, "", "")
        assert low < elapsed < high  # 2 s watchdog under the 3 s hook timeouts, 4 s under SessionEnd's 5 s
    finally:
        pid_file = tmp_path / "stub.pid"
        if pid_file.exists():
            try:
                os.kill(int(pid_file.read_text()), signal.SIGKILL)
            except (OSError, ValueError):
                pass


# ---------------------------------------------------------------- hooks.json, command, lint


def test_hooks_json_has_timeouts_and_guards_unchanged():
    text = HOOKS_JSON.read_text()
    assert text.startswith(GUARDS + ",\n")
    hooks = json.loads(text)["hooks"]
    expected = {"SessionStart": ("telemetry-start.sh", 15), "Stop": ("telemetry-nudge.sh", 3),
                "SubagentStop": ("telemetry-nudge.sh", 3), "SessionEnd": ("telemetry-nudge.sh", 5)}
    for event, (script, timeout) in expected.items():
        (entry,) = hooks[event]
        assert entry == {"hooks": [{"type": "command", "command": "${CLAUDE_PLUGIN_ROOT}/hooks/" + script,
                                    "timeout": timeout}]}
    assert set(hooks) == {"UserPromptSubmit", "PreToolUse"} | set(expected)


def test_scripts_are_executable():
    for script in (START, NUDGE):
        assert script.stat().st_mode & stat.S_IXUSR


def test_telemetry_command_front_matter_and_body():
    text = COMMAND.read_text()
    head = text.split("---\n")[1].splitlines()
    assert head == ["description: Telemetry status, sign-in, opt-out",
                    "allowed-tools: Bash(python3 -I -B ${CLAUDE_PLUGIN_ROOT}/bin/cpp_telemetry:*)",
                    "argument-hint: status|login|optout|on|uninstall"]
    assert "python3 -I -B ${CLAUDE_PLUGIN_ROOT}/bin/cpp_telemetry $ARGUMENTS" in text
    assert "gate" not in text.lower()


def test_telemetry_command_body_matches_the_allowed_tools_prefix():
    text = COMMAND.read_text()
    allowed = text.split("allowed-tools: Bash(", 1)[1].split(":*)", 1)[0]
    commands = [line for line in text.splitlines() if line.startswith("python3")]
    assert commands and all(line.startswith(allowed + " ") for line in commands)


def test_shellcheck_clean():
    shellcheck = Path(sys.executable).parent / "shellcheck"
    tool = str(shellcheck) if shellcheck.exists() else shutil.which("shellcheck")
    if tool is None:
        pytest.skip("shellcheck not installed")
    done = subprocess.run([tool, str(START), str(NUDGE)], capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stdout + done.stderr
