"""Hook snapshots: fixed-key ``hook`` envelopes built from Claude Code hook JSON.

``from_hook`` never copies the hook JSON. Each envelope is built from fixed keys;
the string values read from the developer's machine (the repo basename and the
branch) pass through ``scrub.scrub_text``; ``session_id`` is passed through
untouched; ``entrypoint``, ``source`` and ``reason`` are kept only when they are
one short word. No prompt, reply, tool input, transcript text or path ever goes
into an envelope.

- ``SessionStart`` -> ``session_start`` {session_id, ts, repo, branch, plugin_version,
  engine_version, entrypoint, source}. ``repo`` is the basename of
  ``git -C <cwd> remote get-url origin`` without ``.git`` (fallback: the directory
  basename); ``branch`` is ``git rev-parse --abbrev-ref HEAD`` (fallback ``""``);
  ``engine_version`` is the ``version`` field of the first line of
  ``transcript_path`` when readable and valid, else null. A valid engine version is
  also kept in ``state.engine_version``.
- ``Stop`` -> ``turn`` {session_id, ts, seq}: ``seq`` counts from 1 per session in
  this process's memory (``state.turn_seq``).
- ``SubagentStop`` -> ``subagent_stop`` {session_id, ts}.
- ``SessionEnd`` -> ``session_end`` {session_id, ts, reason}.
- Any other event -> no envelope.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import threading
import time
from typing import Any, Callable, List, Optional

from . import scrub
from .receiver import valid_version
from .spool import iso_ms

GIT_TIMEOUT_S = 2.0
TRANSCRIPT_LINE_MAX = 65536
_WORD_RE = re.compile(r"[A-Za-z0-9_.:-]{1,64}")
_SEQ_LOCK = threading.Lock()


def _word(value: Any, default: Optional[str]) -> Optional[str]:
    return value if isinstance(value, str) and _WORD_RE.fullmatch(value) else default


def _git(cwd: str, *args: str) -> str:
    """One line of ``git -C <cwd> <args>`` output, or ``""`` on any failure."""
    try:
        done = subprocess.run(
            ["git", "-C", cwd] + list(args),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=GIT_TIMEOUT_S,
            env=dict(os.environ, GIT_TERMINAL_PROMPT="0", GIT_OPTIONAL_LOCKS="0"),
        )
    except (OSError, ValueError, subprocess.SubprocessError):
        return ""
    if done.returncode != 0:
        return ""
    return done.stdout.decode("utf-8", "replace").strip()


def repo_basename(url: str) -> str:
    """``repo`` from ``https://host/org/repo.git``, ``git@host:org/repo.git`` or ``/srv/repo/``."""
    tail = re.split(r"[/:\\]", url.strip().rstrip("/\\"))[-1]
    return tail[:-4] if tail.endswith(".git") else tail


def _repo_and_branch(cwd: Any) -> "tuple[str, str]":
    if not isinstance(cwd, str) or not cwd or not os.path.isdir(cwd):
        return "", ""
    repo = repo_basename(_git(cwd, "remote", "get-url", "origin"))
    if not repo:
        repo = os.path.basename(os.path.normpath(cwd))
    return repo, _git(cwd, "rev-parse", "--abbrev-ref", "HEAD")


def engine_version(transcript_path: Any) -> Optional[str]:
    """The ``version`` field of the transcript's first line, when it is a valid version string."""
    if not isinstance(transcript_path, str) or not transcript_path:
        return None
    try:
        with open(transcript_path, "rb") as fh:
            line = fh.readline(TRANSCRIPT_LINE_MAX)
        record = json.loads(line.decode("utf-8"))
    except (OSError, ValueError, RecursionError):
        return None
    version = record.get("version") if isinstance(record, dict) else None
    return version if valid_version(version) else None


def _next_seq(state: Any, session_id: Any) -> int:
    with _SEQ_LOCK:
        counts = getattr(state, "turn_seq", None)
        if counts is None:
            counts = {}
            state.turn_seq = counts
        key = session_id if isinstance(session_id, str) else ""
        counts[key] = counts.get(key, 0) + 1
        return counts[key]


def from_hook(hook_json: dict, plugin_version: str, state: Any, *, ident: Optional[scrub.Identity] = None,
              clock: Callable[[], float] = time.time) -> List[dict]:
    """The ``hook`` envelopes for one Claude Code hook (see the module docstring)."""
    if not isinstance(hook_json, dict):
        return []
    event = hook_json.get("hook_event_name")
    session_id = hook_json.get("session_id")
    session_id = session_id if isinstance(session_id, str) else None
    base = {"session_id": session_id, "ts": iso_ms(clock())}
    if event == "SessionStart":
        ident = ident if ident is not None else scrub.identity_from_environment(None)
        repo, branch = _repo_and_branch(hook_json.get("cwd"))
        engine = engine_version(hook_json.get("transcript_path"))
        if engine is not None:
            state.engine_version = engine
        payload = dict(name="session_start", **base, repo=scrub.scrub_text(repo, ident),
                       branch=scrub.scrub_text(branch, ident), plugin_version=plugin_version,
                       engine_version=engine, entrypoint=_word(hook_json.get("entrypoint", "cli"), "cli"),
                       source=_word(hook_json.get("source"), None))
    elif event == "Stop":
        payload = dict(name="turn", **base, seq=_next_seq(state, session_id))
    elif event == "SubagentStop":
        payload = dict(name="subagent_stop", **base)
    elif event == "SessionEnd":
        payload = dict(name="session_end", **base, reason=_word(hook_json.get("reason"), None))
    else:
        return []
    return [{"signal": "hook", "payload": payload}]
