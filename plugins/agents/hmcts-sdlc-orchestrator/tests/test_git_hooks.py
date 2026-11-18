"""Git attribution: the chaining shims, install_shims, git_event.collect/post and the git-event command.

The shell tests run real git in temp repositories whose origin is invented; HOME,
GIT_CONFIG_GLOBAL and CPP_HARNESS_HOME point at temp paths (conftest), so no real
git config or shims directory is touched. The forwarder is an in-process receiver
that passes the healthz proof; the fixture closes it.
"""
import json
import os
import shutil
import stat
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest

from cpp_telemetry import PLUGIN_VERSION, cli, config, git_event, lifecycle, receiver, spool
from tests.helpers_net import free_port_run

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
SHIM_NAMES = ("post-commit", "post-rewrite", "pre-push")
SHIMS = [PLUGIN_ROOT / "git-hooks" / name for name in SHIM_NAMES]
BASH = shutil.which("bash") or "/bin/bash"
GIT = shutil.which("git")
ORIGIN = "https://example.invalid/org/repo.git"
CONFIGURED = {
    "ingest_url": "http://127.0.0.1:18080",
    "tenant_id": "00000000-0000-0000-0000-000000000001",
    "client_id": "00000000-0000-0000-0000-000000000002",
    "api_app_id": "00000000-0000-0000-0000-000000000003",
}
IDENTITY = {
    "GIT_AUTHOR_NAME": "devuser",
    "GIT_AUTHOR_EMAIL": "devuser@example.invalid",
    "GIT_COMMITTER_NAME": "devuser",
    "GIT_COMMITTER_EMAIL": "devuser@example.invalid",
}
ZERO = "0" * 40
needs_git = pytest.mark.skipif(GIT is None, reason="git not installed")

STUB_PYTHON = """#!/bin/sh
printf '%s\\n' "$*" >> "$STUB_LOG"
pwd -P >> "$STUB_CWD"
printf '%s\\n' "${CPP_TELEMETRY_GIT_CWD:-}" >> "$STUB_CWD"
echo $$ > "$STUB_PID"
exec "$REAL_PYTHON" -c "import time; time.sleep(5)"
"""


def _git(world, *args, cwd=None):
    return subprocess.run([GIT] + [str(a) for a in args], cwd=str(cwd or world.repo), env=world.env,
                          capture_output=True, text=True, timeout=30)


def _head(world):
    return _git(world, "rev-parse", "HEAD").stdout.strip()


def _hook(path, label, log, code=0):
    """A chained hook that appends ``label|args`` and its stdin to ``log``, then exits ``code``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('#!/bin/sh\nprintf "%%s|%%s\\n" "%s" "$*" >> "%s"\ncat >> "%s"\nexit %d\n'
                    % (label, log, log, code))
    path.chmod(0o755)


def _shim(world, name, args=(), stdin="", env=None):
    return subprocess.run([BASH, str(world.shims / name)] + list(args), input=stdin, cwd=str(world.repo),
                          env=env or world.env, capture_output=True, text=True, timeout=30)


def _events(events, kind):
    return [envelope["payload"] for envelope in events if envelope["payload"].get("kind") == kind]


@pytest.fixture
def world(tmp_path, monkeypatch):
    """A configured data dir, installed shims as the global core.hooksPath and a repo with an invented origin."""
    data = tmp_path / "data"
    data.mkdir(mode=0o700)
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(data))
    base = free_port_run()
    (data / "override.json").write_text(json.dumps(dict(CONFIGURED, port=base, port_scan=[base + 1, base + 9])))
    py_bin = tmp_path / "py-bin"
    py_bin.mkdir()
    (py_bin / "python3").write_text("#!/bin/sh\nexec '%s' \"$@\"\n" % sys.executable)
    (py_bin / "python3").chmod(0o755)
    env = dict(os.environ, CLAUDE_PLUGIN_DATA=str(data), GIT_TERMINAL_PROMPT="0", **IDENTITY)
    env["PATH"] = "%s:%s" % (py_bin, os.environ.get("PATH", "/usr/bin:/bin"))
    w = SimpleNamespace(tmp=tmp_path, data=data, base=base, env=env, repo=tmp_path / "work" / "checkout",
                        prev=tmp_path / "prev-hooks", log=tmp_path / "hooks.log")
    _git(w, "init", "-q", "-b", "main", w.repo, cwd=tmp_path)
    _git(w, "remote", "add", "origin", ORIGIN)
    w.shims = git_event.install_shims(PLUGIN_ROOT, PLUGIN_VERSION)
    _git(w, "config", "--global", "core.hooksPath", w.shims)
    _git(w, "config", "--global", "cpp.previousHooksPath", w.prev)
    return w


@pytest.fixture
def forwarder(world):
    """An in-process receiver on the recorded port that passes the healthz proof; yields the recorded events."""
    cfg = config.load(world.data)
    token = lifecycle.ensure_token(world.data)
    events = []
    rec = receiver.Receiver(cfg, spool.Spool(world.data, cfg), receiver.IdentityProvider(trusted_email=None),
                            PLUGIN_VERSION, lambda hook: [], events.append, receiver.ForwarderState(),
                            port=world.base, token=token)
    lifecycle.write_port(world.data, world.base)
    thread = threading.Thread(target=rec.serve_forever, daemon=True)
    thread.start()
    yield events
    rec.close()
    thread.join(5)


class _Recorder(BaseHTTPRequestHandler):
    """A listener that is not ours: answers healthz without a proof and records every POST."""

    def do_GET(self):  # noqa: N802
        self.send_response(200)
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"{}")

    def do_POST(self):  # noqa: N802
        self.server.posts.append(self.path)
        self.send_response(200)
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"{}")

    def log_message(self, *args):
        pass


@pytest.fixture
def foreign():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Recorder)
    srv.posts = []
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    yield srv
    srv.shutdown()
    srv.server_close()
    thread.join(5)


# ---------------------------------------------------------------- install


def test_install_shims_copies_and_refreshes_on_version_change(tmp_path):
    target = git_event.install_shims(PLUGIN_ROOT, "1.0.0")
    assert target == Path(os.environ["CPP_HARNESS_HOME"]) / "git-hooks"
    for name in SHIM_NAMES:
        assert (target / name).read_bytes() == (PLUGIN_ROOT / "git-hooks" / name).read_bytes()
        assert stat.S_IMODE((target / name).stat().st_mode) == 0o755
    assert (target / "plugin-root").read_text() == str(PLUGIN_ROOT) + "\n"
    assert (target / "version").read_text() == "1.0.0\n"
    (target / "post-commit").write_text("edited\n")
    moved = tmp_path / "moved-plugin"
    shutil.copytree(str(PLUGIN_ROOT / "git-hooks"), str(moved / "git-hooks"))
    assert git_event.install_shims(moved, "1.0.0") == target
    assert (target / "post-commit").read_text() == "edited\n"  # same version: not copied again
    assert (target / "plugin-root").read_text() == str(moved.resolve()) + "\n"  # but the root follows the plugin
    git_event.install_shims(PLUGIN_ROOT, "1.0.1")
    assert (target / "post-commit").read_bytes() == SHIMS[0].read_bytes()
    assert (target / "version").read_text() == "1.0.1\n" and list(target.glob("*.tmp")) == []


def test_install_shims_copies_again_when_a_shim_is_missing():
    target = git_event.install_shims(PLUGIN_ROOT, PLUGIN_VERSION)
    (target / "pre-push").unlink()
    git_event.install_shims(PLUGIN_ROOT, PLUGIN_VERSION)
    assert (target / "pre-push").read_bytes() == SHIMS[2].read_bytes()


def test_shim_sources_are_one_executable_body():
    assert len({path.read_bytes() for path in SHIMS}) == 1
    assert all(path.stat().st_mode & stat.S_IXUSR for path in SHIMS)


def test_cli_and_git_event_agree_on_the_kinds():
    assert cli.GIT_KINDS == git_event.KINDS == ("commit", "rewrite", "push")


# ---------------------------------------------------------------- shims through real git


@needs_git
def test_post_commit_chains_previous_and_repo_hook_then_posts(world, forwarder):
    _hook(world.prev / "post-commit", "prev", world.log)
    _hook(world.repo / ".git" / "hooks" / "post-commit", "repo", world.log)
    marker = world.tmp / "planted-import-ran"
    (world.repo / "urllib").mkdir()
    (world.repo / "urllib" / "__init__.py").write_text("open(%r, 'w').write('imported')\n" % str(marker))
    done = _git(world, "commit", "--allow-empty", "-q", "-m", "first")
    assert (done.returncode, done.stdout, done.stderr) == (0, "", "")
    assert world.log.read_text() == "prev|\nrepo|\n"  # previous global hook first, then the repo's own
    (payload,) = [envelope["payload"] for envelope in forwarder]
    assert isinstance(payload.pop("ts"), str)
    assert payload == {"name": "git", "kind": "commit", "repo": "repo", "branch": "main", "sha": _head(world)}
    assert not marker.exists()  # git-event ran isolated from the repository


@needs_git
def test_post_rewrite_replays_stdin_to_each_hook_and_posts_the_new_shas(world, forwarder):
    _git(world, "commit", "--allow-empty", "-q", "-m", "first")
    old = _head(world)
    _hook(world.prev / "post-rewrite", "prev", world.log)
    _hook(world.repo / ".git" / "hooks" / "post-rewrite", "repo", world.log)
    done = _git(world, "commit", "--amend", "--allow-empty", "-q", "-m", "second")
    assert (done.returncode, done.stderr) == (0, "")
    new = _head(world)
    line = "%s %s\n" % (old, new)
    assert world.log.read_text() == "prev|amend\n" + line + "repo|amend\n" + line
    (payload,) = _events(forwarder, "rewrite")
    assert (payload["sha"], payload["repo"], payload["branch"]) == ([new], "repo", "main")


@needs_git
@pytest.mark.parametrize("failing", [None, "prev", "repo"])
def test_pre_push_honours_chained_exit_code(world, forwarder, failing):
    bare = world.tmp / "remote.git"
    _git(world, "init", "-q", "--bare", bare, cwd=world.tmp)
    _git(world, "remote", "set-url", "--push", "origin", bare)
    _git(world, "commit", "--allow-empty", "-q", "-m", "first")
    head = _head(world)
    _hook(world.prev / "pre-push", "prev", world.log, code=3 if failing == "prev" else 0)
    _hook(world.repo / ".git" / "hooks" / "pre-push", "repo", world.log, code=3 if failing == "repo" else 0)
    done = _git(world, "push", "-q", "origin", "main")
    pushed = _git(world, "--git-dir", bare, "rev-parse", "-q", "--verify", "refs/heads/main").stdout.strip()
    line = "refs/heads/main %s refs/heads/main %s\n" % (head, ZERO)
    call = "|origin %s\n%s" % (bare, line)
    if failing is None:
        assert (done.returncode, pushed) == (0, head)
        assert world.log.read_text() == "prev" + call + "repo" + call  # one stdin, replayed to each hook
        (payload,) = _events(forwarder, "push")
        assert (payload["remote"], payload["sha"], payload["repo"]) == ("origin", [head], "repo")
        assert str(world.tmp) not in json.dumps(forwarder)  # the push URL (a path here) is never recorded
        return
    assert done.returncode != 0 and pushed == ""
    assert world.log.read_text() == "prev" + call + ("" if failing == "prev" else "repo" + call)
    assert _events(forwarder, "push") == []  # a refused push is not recorded
    shim = _shim(world, "pre-push", ["origin", str(bare)], stdin=line)
    assert shim.returncode == 3  # the chained hook's own code


@needs_git
def test_shim_exits_zero_when_forwarder_down(world):
    lifecycle.ensure_token(world.data)
    (world.data / "port").write_text("%d\n" % world.base)  # recorded, but nothing listens there
    _hook(world.prev / "post-commit", "prev", world.log, code=7)
    _hook(world.prev / "post-rewrite", "prev", world.log, code=7)
    started = time.monotonic()
    done = _git(world, "commit", "--allow-empty", "-q", "-m", "first")
    assert (done.returncode, done.stderr) == (0, "")
    commit = _shim(world, "post-commit")
    rewrite = _shim(world, "post-rewrite", ["amend"], stdin="%s %s\n" % ("a" * 40, "b" * 40))
    for result in (commit, rewrite):
        assert (result.returncode, result.stdout, result.stderr) == (0, "", "")
    assert time.monotonic() - started < 6
    assert world.log.read_text().count("prev|") == 3  # the failing chained hook ran every time


def _stub_env(world, with_timeout):
    tools = world.tmp / "tools"
    tools.mkdir()
    (tools / "python3").write_text(STUB_PYTHON)
    (tools / "python3").chmod(0o755)
    for tool in ("git", "sleep", "cat") + (("timeout",) if with_timeout else ()):  # cat: the chained test hooks
        (tools / tool).symlink_to(shutil.which(tool))
    return dict(world.env, PATH=str(tools), REAL_PYTHON=sys.executable, STUB_LOG=str(world.tmp / "stub.log"),
                STUB_CWD=str(world.tmp / "stub.cwd"), STUB_PID=str(world.tmp / "stub.pid"))


def _lines(path):
    return path.read_text().splitlines() if path.exists() else []


@needs_git
@pytest.mark.parametrize("with_timeout", [pytest.param(True, marks=pytest.mark.skipif(shutil.which("timeout") is None, reason="no timeout(1)")), False])
def test_shim_runs_git_event_isolated_from_the_data_dir_within_one_second(world, with_timeout):
    (world.data / "port").write_text("%d\n" % world.base)
    env = _stub_env(world, with_timeout)
    started = time.monotonic()
    done = _shim(world, "post-commit", env=env)
    elapsed = time.monotonic() - started
    assert (done.returncode, done.stdout, done.stderr) == (0, "", "")
    assert 0.9 < elapsed < 2.5  # the hung git-event is cut at 1 s, with or without timeout(1)
    assert _lines(world.tmp / "stub.log") == ["-I -B %s/bin/cpp_telemetry git-event commit" % PLUGIN_ROOT]
    cwd, repo = _lines(world.tmp / "stub.cwd")
    assert (cwd, os.path.realpath(repo)) == (os.path.realpath(str(world.data)), os.path.realpath(str(world.repo)))
    pid = int((world.tmp / "stub.pid").read_text())
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.05)
    else:
        os.kill(pid, 9)
        pytest.fail("the timed-out git-event was left running")


@needs_git
@pytest.mark.parametrize("how", ["off", "opt-out", "no-data-dir", "no-port"])
def test_shim_skips_python_when_off_opted_out_or_without_a_forwarder(world, how):
    if how != "no-port":
        (world.data / "port").write_text("%d\n" % world.base)
    env = _stub_env(world, False)  # Python never runs here: timeout(1) does not matter
    if how == "off":
        env["CPP_HARNESS_TELEMETRY"] = "off"
    elif how == "opt-out":
        (world.data / "opt-out").write_text("")
    elif how == "no-data-dir":
        env["CLAUDE_PLUGIN_DATA"] = str(world.data / "absent")
    _hook(world.prev / "post-commit", "prev", world.log)
    done = _shim(world, "post-commit", env=env)
    assert (done.returncode, done.stdout, done.stderr) == (0, "", "")
    assert world.log.read_text() == "prev|\n" and _lines(world.tmp / "stub.log") == []


@needs_git
def test_shim_never_chains_itself_when_the_previous_path_is_ours(world, forwarder):
    _git(world, "config", "--global", "cpp.previousHooksPath", world.shims)  # onboarding line run twice
    (world.repo / ".git" / "hooks" / "post-commit").symlink_to(world.shims / "post-commit")
    done = _git(world, "commit", "--allow-empty", "-q", "-m", "first")
    assert (done.returncode, done.stderr) == (0, "")
    assert len(_events(forwarder, "commit")) == 1


# ---------------------------------------------------------------- collect, post, git-event


@needs_git
def test_collect_commit_has_no_url_or_path(world):
    _git(world, "commit", "--allow-empty", "-q", "-m", "first")
    payload = git_event.collect("commit", [], "", str(world.repo))
    assert isinstance(payload.pop("ts"), str)
    assert payload == {"name": "git", "kind": "commit", "repo": "repo", "branch": "main", "sha": _head(world)}
    text = json.dumps(payload)
    for forbidden in ("example.invalid", "https", "org/", str(world.tmp), "devuser"):
        assert forbidden not in text


@needs_git
@pytest.mark.parametrize("argv, remote", [
    (["origin", ORIGIN], "origin"),
    ([ORIGIN, ORIGIN], None),  # git push <url>: git passes the URL as the remote name too
    (["git@example.invalid:org/repo.git", "git@example.invalid:org/repo.git"], None),
    (["../elsewhere", "../elsewhere"], None),
    ([], None),
])
def test_collect_push_names_the_remote_never_its_url(world, argv, remote):
    stdin = "refs/heads/main %s refs/heads/main %s\nrefs/heads/gone %s refs/heads/gone %s\n" % (
        "a" * 40, ZERO, ZERO, "b" * 40)
    payload = git_event.collect("push", argv, stdin, str(world.repo))
    assert payload["remote"] == remote and payload["sha"] == ["a" * 40]  # a deleted ref has no new sha
    assert "example.invalid" not in json.dumps(payload) and "elsewhere" not in json.dumps(payload)


def test_collect_rewrite_keeps_only_valid_new_shas():
    stdin = "%s %s extra\n%s not-a-sha\n\n%s %s\n" % ("a" * 40, "b" * 40, "a" * 40, "c" * 40, "b" * 40)
    assert git_event.new_shas("rewrite", stdin) == ["b" * 40]


@pytest.mark.parametrize("url, name", [
    (ORIGIN, "repo"),
    ("git@example.invalid:org/repo.git", "repo"),
    ("https://example.invalid/org/repo/", "repo"),
    ("https://example.invalid/org/repo.git?ref=x#y", "repo"),
    ("https://example.invalid", "fallback"),  # a host is not a repository name
    ("https://devuser@example.invalid", "fallback"),
    ("", "fallback"),
])
def test_repo_name_is_a_basename_or_the_fallback(url, name):
    assert git_event.repo_name(url, "fallback") == name


@needs_git
def test_git_event_posts_the_collected_event(world, forwarder, monkeypatch):
    _git(world, "commit", "--allow-empty", "-q", "-m", "first")
    forwarder.clear()
    monkeypatch.setenv(git_event.CWD_ENV, str(world.repo))
    assert cli.main(["git-event", "commit"]) == 0
    (payload,) = _events(forwarder, "commit")
    assert payload["sha"] == _head(world)


@needs_git
@pytest.mark.parametrize("state", ["foreign", "no-port", "opt-out"])
def test_git_event_never_starts_a_forwarder_and_drops_the_event(world, foreign, monkeypatch, capsys, state):
    def refuse(*args, **kwargs):
        raise AssertionError("git-event must never start a forwarder")

    monkeypatch.setattr(lifecycle, "ensure_running", refuse)
    monkeypatch.setattr(lifecycle, "_spawn", refuse)
    collected = []
    monkeypatch.setattr(git_event, "collect", lambda *args, **kwargs: collected.append(args) or {})
    lifecycle.ensure_token(world.data)
    if state != "no-port":
        (world.data / "port").write_text("%d\n" % foreign.server_address[1])  # a listener without the proof
    if state == "opt-out":
        (world.data / "opt-out").write_text("")
    monkeypatch.setenv(git_event.CWD_ENV, str(world.repo))
    assert cli.main(["git-event", "commit"]) == 0
    assert foreign.posts == [] and collected == []  # no token sent, no git run
    assert capsys.readouterr() == ("", "")


def test_git_event_without_a_kind_is_a_usage_error(data_dir):
    assert cli.main(["git-event"]) == 2
    assert cli.main(["git-event", "merge"]) == 2


# ---------------------------------------------------------------- lint


def test_shellcheck_clean_shims():
    shellcheck = Path(sys.executable).parent / "shellcheck"
    tool = str(shellcheck) if shellcheck.exists() else shutil.which("shellcheck")
    if tool is None:
        pytest.skip("shellcheck not installed")
    done = subprocess.run([tool, "--shell=bash"] + [str(path) for path in SHIMS], capture_output=True, text=True,
                          timeout=60)
    assert done.returncode == 0, done.stdout + done.stderr
