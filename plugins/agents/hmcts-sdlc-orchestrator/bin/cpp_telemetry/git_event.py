"""Git attribution: the chaining hook shims and the ``git`` events they record.

- ``install_shims(plugin_root, version)`` copies the one script ``git-hooks/hook`` to
  ``~/.cpp-harness/git-hooks/`` under every name of ``SHIM_NAMES`` (``CPP_HARNESS_HOME``
  replaces ``~/.cpp-harness``), mode 0755, and writes ``plugin-root`` and ``version`` beside
  them. The shims are copied again only when ``version`` differs (or a shim is missing);
  ``plugin-root`` follows the plugin when it moves. Each file is replaced atomically.
- The developer points git at that directory once (the README onboarding line keeps the
  previous ``core.hooksPath`` in ``cpp.previousHooksPath``). Each shim runs the hook it
  replaces, then the repository's own hook; post-commit, post-rewrite and pre-push then run
  ``git-event`` within a 1 s budget.
- ``collect(kind, argv, stdin, cwd)`` builds ``{"name": "git", "kind", "repo", "branch",
  "sha", "ts"}`` plus ``remote`` for a push. ``repo`` is the basename of the origin URL
  without ``.git`` (fallback: the directory basename), never the URL; ``remote`` is the
  remote's name, never its URL; no path, author or email. ``repo``, ``branch`` and
  ``remote`` pass through ``scrub.scrub_text``.
- ``forwarder_port(data_dir)`` and ``post(data_dir, payload)`` never start a forwarder: the
  event goes to ``/event`` only when the port in ``<data>/port`` answers the healthz proof;
  otherwise it is dropped.
- ``uninstall_shims()`` points ``core.hooksPath`` back at ``cpp.previousHooksPath`` (when it
  still names our directory) before it deletes the directory.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Callable, List, Optional, Sequence

from . import scrub
from .snapshot import repo_basename
from .spool import iso_ms

KINDS = ("commit", "rewrite", "push")
SHIM_SOURCE = "hook"
# Every standard hook name (githooks(5)). The global core.hooksPath replaces the repository's
# hooks directory for all of them, so each must exist and chain; only three record an event.
SHIM_NAMES = (
    "applypatch-msg", "pre-applypatch", "post-applypatch", "pre-commit", "pre-merge-commit",
    "prepare-commit-msg", "commit-msg", "post-commit", "pre-rebase", "post-checkout", "post-merge", "pre-push",
    "pre-receive", "update", "proc-receive", "post-receive", "post-update", "reference-transaction",
    "push-to-checkout", "pre-auto-gc", "post-rewrite", "sendemail-validate", "fsmonitor-watchman",
    "p4-changelist", "p4-prepare-changelist", "p4-post-changelist", "p4-pre-submit", "post-index-change",
)
SHIMS_DIR = "git-hooks"
PLUGIN_ROOT_FILE = "plugin-root"
VERSION_FILE = "version"
CWD_ENV = "CPP_TELEMETRY_GIT_CWD"  # the hook's working directory (the shim runs Python from the data dir)
GIT_TIMEOUT_S = 0.5
CONFIG_TIMEOUT_S = 5.0
HEALTHZ_TIMEOUT_S = 0.5
POST_TIMEOUT_S = 1.0
MAX_SHAS = 1000
_SHA_RE = re.compile(r"[0-9a-f]{40}(?:[0-9a-f]{24})?")
_REMOTE_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}")


class RestoreError(RuntimeError):
    """``git config --global`` could not restore ``core.hooksPath`` (no value in the message)."""


def harness_home() -> Path:
    env = os.environ.get("CPP_HARNESS_HOME")
    return Path(env) if env else Path.home() / ".cpp-harness"


def shims_dir() -> Path:
    return harness_home() / SHIMS_DIR


# ---------------------------------------------------------------------- install


def _read(path: Path) -> Optional[str]:
    try:
        return path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError):
        return None


def _write_atomic(path: Path, data: bytes, mode: int) -> None:
    """Replace ``path`` in one step: a shim git is running keeps reading its old file."""
    tmp = path.with_name(".%s.%d.tmp" % (path.name, os.getpid()))
    try:
        with open(str(tmp), "wb") as fh:
            fh.write(data)
        os.chmod(str(tmp), mode)
        os.replace(str(tmp), str(path))
    finally:
        try:
            os.remove(str(tmp))
        except FileNotFoundError:
            pass


def install_shims(plugin_root: Path, version: str) -> Path:
    """Copy the shims to ``shims_dir()`` when the version differs; returns that directory."""
    target = shims_dir()
    target.mkdir(parents=True, exist_ok=True)
    current = _read(target / VERSION_FILE) == version and all((target / n).is_file() for n in SHIM_NAMES)
    if not current:
        script = (Path(plugin_root) / SHIMS_DIR / SHIM_SOURCE).read_bytes()
        for name in SHIM_NAMES:
            _write_atomic(target / name, script, 0o755)
    root = str(Path(plugin_root).resolve())
    if _read(target / PLUGIN_ROOT_FILE) != root:
        _write_atomic(target / PLUGIN_ROOT_FILE, (root + "\n").encode("utf-8"), 0o644)
    if not current:
        _write_atomic(target / VERSION_FILE, (version + "\n").encode("utf-8"), 0o644)  # last: a partial copy is redone
    return target


# ---------------------------------------------------------------------- collect


def _git(cwd: Optional[str], *args: str) -> str:
    """One line of ``git [-C cwd] <args>`` output, or ``""`` on any failure."""
    command = ["git"] + (["-C", cwd] if cwd else []) + list(args)
    try:
        done = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                              timeout=GIT_TIMEOUT_S, check=False,
                              env=dict(os.environ, GIT_TERMINAL_PROMPT="0", GIT_OPTIONAL_LOCKS="0"))
    except (OSError, ValueError, subprocess.SubprocessError):
        return ""
    return done.stdout.decode("utf-8", "replace").strip() if done.returncode == 0 else ""


def repo_name(url: str, fallback: str) -> str:
    """The repository basename of an origin URL, or ``fallback`` when the URL names none."""
    path = url.strip().split("#", 1)[0].split("?", 1)[0].rstrip("/\\")
    if "://" in path and "/" not in path.split("://", 1)[1]:
        return fallback  # scheme://host with no path: a host is not a repository name
    name = repo_basename(path)
    return name if name and "@" not in name else fallback


def new_shas(kind: str, stdin: str) -> List[str]:
    """The new object names on stdin: ``<old> <new> [extra]`` lines (rewrite) or
    ``<local ref> <local sha> <remote ref> <remote sha>`` lines (push); a deleted ref has none."""
    shas: List[str] = []
    for line in stdin.splitlines():
        fields = line.split()
        if kind == "rewrite" and len(fields) >= 2:
            candidate = fields[1]
        elif kind == "push" and len(fields) >= 4:
            candidate = fields[1]
        else:
            continue
        if _SHA_RE.fullmatch(candidate) and candidate.strip("0") and candidate not in shas:
            shas.append(candidate)
            if len(shas) >= MAX_SHAS:
                break
    return shas


def _remote(argv: Sequence[str]) -> Optional[str]:
    """pre-push's first argument when it is a remote name; ``git push <url>`` passes the URL there too."""
    if not argv:
        return None
    name = argv[0]
    if len(argv) > 1 and name == argv[1]:
        return None
    return name if _REMOTE_RE.fullmatch(name) else None


def collect(kind: str, argv: Sequence[str], stdin: str = "", cwd: Optional[str] = None,
            clock: Callable[[], float] = time.time) -> dict:
    """The ``git`` event payload for one hook run (see the module docstring)."""
    if kind not in KINDS:
        raise ValueError("unknown git event kind")
    ident = scrub.identity_from_environment(None)
    url = _git(cwd, "remote", "get-url", "origin")
    repo = repo_name(url, "") if url else ""
    if not repo:
        top = _git(cwd, "rev-parse", "--show-toplevel") or cwd or os.getcwd()
        repo = os.path.basename(os.path.normpath(top))
    payload = {"name": "git", "kind": kind, "repo": scrub.scrub_text(repo, ident),
               "branch": scrub.scrub_text(_git(cwd, "rev-parse", "--abbrev-ref", "HEAD"), ident)}
    if kind == "commit":
        head = _git(cwd, "rev-parse", "HEAD")
        payload["sha"] = head if _SHA_RE.fullmatch(head) else None
    else:
        payload["sha"] = new_shas(kind, stdin)
    if kind == "push":
        payload["remote"] = scrub.scrub_text(_remote(argv), ident)
    payload["ts"] = iso_ms(clock())
    return payload


# ---------------------------------------------------------------------- post


def forwarder_port(data_dir: Path) -> Optional[int]:
    """The recorded port when our forwarder answers the healthz proof there; never starts one."""
    from . import lifecycle

    port = lifecycle.read_port(data_dir)
    if port is None or lifecycle.healthz(port, data_dir, timeout=HEALTHZ_TIMEOUT_S) is None:
        return None
    return port


def post(data_dir: Path, payload: dict, port: Optional[int] = None) -> bool:
    """POST the event to ``/event`` of the proof-checked forwarder; False (event dropped) on any failure."""
    from . import lifecycle

    port = forwarder_port(data_dir) if port is None else port
    if port is None:
        return False
    status = lifecycle.post_json(port, "/event", data_dir, {"signal": "event", "payload": payload},
                                 timeout=POST_TIMEOUT_S)
    return status == 200


# ---------------------------------------------------------------------- uninstall


def _config(*args: str) -> subprocess.CompletedProcess:
    """``git config <args>`` in this process's cwd (the session's project for ``--local``)."""
    return subprocess.run(["git", "config"] + list(args), stdin=subprocess.DEVNULL,
                          stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=CONFIG_TIMEOUT_S, check=False)


def _get(key: str, path: bool = False, scope: str = "--global") -> Optional[str]:
    """The value of ``key`` in ``scope`` (``~`` expanded when ``path``), or None when it is not set.

    git before 2.18 rejects ``--type=path``: the raw value is then read and ``~`` expanded
    here. A ``--local`` read outside a repository counts as not set.
    """
    if path:
        done = _config(scope, "--type=path", "--get", key)
        if done.returncode == 0:
            return done.stdout.decode("utf-8", "surrogateescape").rstrip("\n")
        if done.returncode == 1:
            return None
    done = _config(scope, "--get", key)
    if done.returncode == 1 or (done.returncode != 0 and scope == "--local"):
        return None
    if done.returncode != 0:
        raise RestoreError("git config --get failed")
    value = done.stdout.decode("utf-8", "surrogateescape").rstrip("\n")
    return os.path.expanduser(value) if path else value


def _set(key: str, value: str) -> None:
    if _config("--global", key, value).returncode != 0:
        raise RestoreError("git config set failed")


def _unset(key: str, scope: str = "--global") -> None:
    if _config(scope, "--unset-all", key).returncode not in (0, 5):  # 5: the key was not set
        raise RestoreError("git config --unset failed")


def _is_shims_dir(value: Optional[str]) -> bool:
    if not value:
        return False
    try:
        return os.path.realpath(value) == os.path.realpath(str(shims_dir()))
    except (OSError, ValueError):
        return False


def restore_hooks_path() -> None:
    """Point ``core.hooksPath`` back at ``cpp.previousHooksPath`` when it names our shims directory.

    An empty or absent previous value (or one naming our own directory) unsets
    ``core.hooksPath``; a ``core.hooksPath`` the developer has since pointed elsewhere is
    left alone. ``cpp.previousHooksPath`` is then removed. A ``--local`` ``core.hooksPath``
    of the repository uninstall runs in is unset when it names our directory (any other
    local value is left alone). Raises ``RestoreError`` or ``OSError`` /
    ``subprocess.SubprocessError`` when git cannot do it.
    """
    previous = _get("cpp.previousHooksPath")
    if _is_shims_dir(_get("core.hooksPath", path=True)):
        if previous and not _is_shims_dir(_get("cpp.previousHooksPath", path=True)):
            _set("core.hooksPath", previous)
        else:
            _unset("core.hooksPath")
    if previous is not None:
        _unset("cpp.previousHooksPath")
    if _is_shims_dir(_get("core.hooksPath", path=True, scope="--local")):
        _unset("core.hooksPath", scope="--local")


def uninstall_shims() -> bool:
    """Restore ``core.hooksPath``, then delete the shims directory.

    False when the restore failed: the directory is kept, because a ``core.hooksPath``
    naming a missing directory would silently stop the developer's own hooks.
    """
    try:
        restore_hooks_path()
    except FileNotFoundError:
        pass  # no git at all: there is no hooks path to restore
    except (OSError, subprocess.SubprocessError, RestoreError):
        return False
    shutil.rmtree(str(shims_dir()), ignore_errors=True)
    return True
