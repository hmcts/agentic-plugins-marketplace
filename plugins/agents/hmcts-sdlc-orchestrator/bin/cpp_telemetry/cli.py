"""Command line: python3 -I -B "$CLAUDE_PLUGIN_ROOT/bin/cpp_telemetry" <command>.

- ``start`` (SessionStart hook): dormant check; silent when ``<data>/opt-out`` exists;
  ``lifecycle.ensure_running`` first, then ``settings.apply`` with the port it
  returns; one line naming the competing keys ``apply`` moved aside (names only,
  no chaining: D-49); the git shims (``git_event.install_shims``); the daily sign-in notice; one line when
  the plugin is behind the marketplace and autoUpdate could not be set; then the
  hook JSON on stdin, when it names a ``hook_event_name``, goes to ``/hook``.
- ``forwarder``: run the forwarder in this process (the detached child).
- ``status``: forwarder, spool, last ack, sign-in, roster, opt-out and moved-aside keys.
- ``login``: device-code sign-in (exit 1 when not configured or not signed in).
- ``optout``: restore the settings, write ``<data>/opt-out``, post an ``opt_out``
  event and flush. Signed in, the forwarder uploads the rest and exits once the
  spool is empty; signed out, no forwarder is started and the spool is deleted
  (by the running forwarder, or here when none runs).
- ``on``: remove ``<data>/opt-out``, then the ``start`` steps (stdin is not read).
- ``off`` (the SessionStart hook when ``CPP_HARNESS_TELEMETRY=off``): restore the settings
  when a record exists, then stop a running forwarder (``lifecycle.stop``: healthz proof,
  verified pid). Never writes ``<data>/opt-out`` and never deletes the spool, so the next
  normal start applies the keys again. Silent, always exit 0, creates no data directory.
- ``uninstall``: ``optout``; signed in, wait up to ``DRAIN_WAIT_S`` for the forwarder
  to drain and exit, else (and when signed out) stop it; delete what is left in the
  spool; point ``core.hooksPath`` back at ``cpp.previousHooksPath``, then remove the git
  shims directory (kept when git could not restore the hooks path).
- ``ensure-running`` (the nudge script): print the proof-checked forwarder port.
- ``git-event <kind> [hook args]`` (the git shims): never starts a forwarder. Dormant,
  opted out, or no forwarder answering the healthz proof on ``<data>/port``: nothing
  happens. Otherwise the ``git`` event of ``git_event.collect`` goes to ``/event``.
  Always exit 0 (2 for an unknown kind).

Every control POST goes to the port ``ensure_running`` returned in the same
invocation, with the token from ``<data>/token`` (ruling 23). Errors go to the
log by exception type; ``start`` and ``ensure-running`` always exit 0.
Exit codes: 0 on success (including every dormant run), 1 when ``login`` cannot
sign in, 2 on a usage error.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from . import PLUGIN_VERSION, config, log, paths

PREFIX = "cpp telemetry: "
HOOK_STDIN_MAX = 1024 * 1024
GIT_KINDS = ("commit", "rewrite", "push")  # git_event.KINDS, kept here so parsing imports nothing more


def _say(text: str) -> None:
    print(PREFIX + text, flush=True)


def _read_hook() -> Optional[dict]:
    """The hook JSON on stdin, or None (no stdin, a terminal, unreadable, not a JSON object)."""
    stream = sys.stdin
    try:
        if stream is None or stream.isatty():
            return None
        raw = stream.read(HOOK_STDIN_MAX)
    except (OSError, ValueError, AttributeError):
        return None
    try:
        data = json.loads(raw)
    except (TypeError, ValueError, RecursionError):
        return None
    return data if isinstance(data, dict) else None


def _version_key(version: str) -> Optional[Tuple[int, ...]]:
    try:
        return tuple(int(part) for part in version.split("."))
    except ValueError:
        return None


def _behind(installed: str, listed: str) -> bool:
    ours, theirs = _version_key(installed), _version_key(listed)
    return ours is not None and theirs is not None and ours < theirs


def _install_shims(root: Path) -> None:
    from . import git_event

    git_event.install_shims(root, PLUGIN_VERSION)


def _start_session(cfg: config.Config, data: Path, hook: Optional[dict]) -> None:
    from . import auth, lifecycle, settings

    logger = log.get_logger(data)
    root = paths.plugin_root()
    port = lifecycle.ensure_running(cfg, data, root, PLUGIN_VERSION)
    result = None
    try:
        result = settings.apply(port, data, PLUGIN_VERSION)
    except (OSError, settings.SettingsError) as exc:
        logger.warning("start: settings not applied (%s)", type(exc).__name__)
    if result is not None and result.removed:
        _say("moved your own collector settings aside (restored by /telemetry optout): " + ", ".join(result.removed))
    try:
        _install_shims(root)
    except Exception as exc:  # noqa: BLE001 - the shims never stop a session start
        logger.warning("start: git shims not installed (%s)", type(exc).__name__)
    if auth.login_notice_due(data):
        _say("not signed in, so nothing is uploaded yet; run /telemetry login")
    versions = settings.check_marketplace_version(root)
    if versions is not None and _behind(*versions) and result is not None and not result.autoupdate_set:
        _say("plugin {} is behind the marketplace ({}); update it with /plugin".format(*versions))
    if hook is not None and hook.get("hook_event_name"):
        lifecycle.post_json(port, "/hook", data, hook)


def _configured_data() -> Tuple[Optional[config.Config], Optional[Path]]:
    cfg = config.load()
    if not cfg.is_configured():
        return None, None
    try:
        return cfg, paths.data_dir()
    except OSError:
        return None, None


def _start(args: argparse.Namespace) -> int:
    cfg, data = _configured_data()
    if cfg is None or data is None:
        # Dormant: no settings key, no output, no process, no spool.
        return 0
    from . import lifecycle

    if (data / lifecycle.OPT_OUT_FILE).exists():
        return 0  # opted out: settings stay restored, nothing starts, nothing is recorded
    hook = _read_hook()
    try:
        _start_session(cfg, data, hook)
    except Exception as exc:  # noqa: BLE001 - a hook must never fail on telemetry
        log.get_logger(data).warning("start: %s", type(exc).__name__)
    return 0


def _forwarder(args: argparse.Namespace) -> int:
    """Run the forwarder in this process (the detached child ``ensure-running`` starts)."""
    cfg = config.load()
    if not cfg.is_configured():
        return 0  # dormant: no process
    from . import forwarder

    return forwarder.run(cfg, paths.data_dir(), paths.plugin_root(), PLUGIN_VERSION)


def _ensure(cfg: config.Config, data: Path) -> Optional[int]:
    """The proof-checked forwarder port, or None (the reason goes to the log by type)."""
    from . import lifecycle

    try:
        return lifecycle.ensure_running(cfg, data, paths.plugin_root(), PLUGIN_VERSION)
    except Exception as exc:  # noqa: BLE001
        log.get_logger(data).warning("ensure-running: %s", type(exc).__name__)
        return None


def _ensure_running(args: argparse.Namespace) -> int:
    """Find or start the forwarder and print its port; always exit 0."""
    cfg, data = _configured_data()
    if cfg is None or data is None:
        return 0
    port = _ensure(cfg, data)
    if port is not None:
        print(port, flush=True)
    return 0


# ---------------------------------------------------------------------- status


def _age(seconds: float) -> str:
    seconds = max(0, int(seconds))
    if seconds < 120:
        return "%d s" % seconds
    if seconds < 7200:
        return "%d min" % (seconds // 60)
    if seconds < 172800:
        return "%d h" % (seconds // 3600)
    return "%d days" % (seconds // 86400)


def _read_float(path: Path) -> Optional[float]:
    try:
        return float(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def _removed_keys(data: Path) -> List[str]:
    from . import settings

    try:
        record = json.loads(settings.managed_keys_path(data).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    removed = record.get("removed") if isinstance(record, dict) else None
    return sorted(k for k in removed if isinstance(k, str)) if isinstance(removed, dict) else []


def _status_lines(cfg: config.Config, data: Path, now: float) -> List[str]:
    from . import auth, lifecycle, uploader
    from .spool import Spool

    lines = []
    port = lifecycle.read_port(data)
    body = lifecycle.healthz(port, data) if port is not None else None
    if body is not None:
        lines.append("forwarder: version {} on port {}".format(body["version"], port))
    else:
        lines.append("forwarder: not running")
    sp = Spool(data, cfg)
    batches = sp.closed_batches_oldest_first()
    lines.append("spool: {} bytes, {} closed batch(es)".format(sp.total_bytes(), len(batches)))
    oldest = None
    if batches:
        try:
            oldest = batches[0].stat().st_mtime
        except OSError:
            oldest = None
    lines.append("oldest batch: " + ("none" if oldest is None else _age(now - oldest) + " old"))
    acked = _read_float(data / uploader.LAST_ACK_FILE)
    lines.append("last ack: " + ("never" if acked is None else _age(now - acked) + " ago"))
    cache = auth.TokenCache(data)
    signed_in = cache.signed_in()
    lines.append("auth: " + ("signed in" if signed_in else "needs sign-in (run /telemetry login)"))
    me = uploader.probe_me(cfg, cache) if signed_in else None
    if me is None:
        lines.append("roster: unknown (offline)" if signed_in else "roster: unknown (not signed in)")
    elif me.get("on_roster") is True:
        team = me.get("team")
        lines.append("roster: on roster" + (", team {}".format(team) if isinstance(team, str) and team else ""))
    else:
        lines.append("roster: not on roster")
    lines.append("opt-out: " + ("yes (/telemetry on resumes)" if (data / lifecycle.OPT_OUT_FILE).exists() else "no"))
    removed = _removed_keys(data)
    lines.append("moved-aside keys: " + (", ".join(removed) if removed else "none"))
    return lines


def _status(args: argparse.Namespace) -> int:
    cfg = config.load()
    if not cfg.is_configured():
        _say("not configured (dormant)")
        return 0
    data = paths.data_dir(create=False)
    for line in _status_lines(cfg, data, time.time()):
        print(line)
    return 0


# ---------------------------------------------------------------------- sign-in


def _login(args: argparse.Namespace) -> int:
    cfg = config.load()
    if not cfg.is_configured():
        _say("not configured, so there is nothing to sign in to")
        return 1
    from . import auth

    data = paths.data_dir()
    try:
        flow = auth.start_device_flow(cfg)
    except auth.AuthError as exc:
        _say("sign-in could not start ({})".format(exc.word))
        return 1
    print(flow.message, flush=True)
    if auth.poll_device_flow(cfg, flow, cache=auth.TokenCache(data)):
        _say("signed in")
        return 0
    _say("sign-in did not complete; run /telemetry login again")
    return 1


# ---------------------------------------------------------------------- opt-out


DRAIN_WAIT_S = 30.0
DRAIN_POLL_S = 0.25


def _running_port(data: Path) -> Optional[int]:
    """The recorded port when our forwarder answers the healthz proof there; never starts one."""
    from . import lifecycle

    port = lifecycle.read_port(data)
    return port if port is not None and lifecycle.healthz(port, data) is not None else None


def _delete_spool_when_idle(cfg: config.Config, data: Path) -> None:
    """Signed out, nothing can upload: with no forwarder holding the lock, delete the spool here (R-04)."""
    from . import lifecycle
    from .spool import SPOOL_DIR, Spool

    if (data / SPOOL_DIR).exists() and not lifecycle.lock_held(data):
        Spool(data, cfg).clear()


def _opt_out(cfg: config.Config) -> Optional[Tuple[int, bool]]:
    """Restore the settings, write ``<data>/opt-out`` and tell the forwarder.

    Signed in: ``ensure_running`` first (before the opt-out file, which with an empty
    spool would stop it starting), then ``opt_out`` and ``/flush``; the forwarder
    uploads what is left and exits. Signed out: no forwarder is started; a running one
    (healthz proof on the recorded port) gets the event and deletes its spool itself;
    with none running the spool is deleted here. Returns (restored key count, signed
    in), or None when the data directory cannot be made.
    """
    from . import auth, lifecycle, settings
    from .spool import iso_ms

    try:
        data = paths.data_dir()
    except OSError:
        return None
    logger = log.get_logger(data)
    try:
        restored = settings.restore(data)
    except (OSError, settings.SettingsError) as exc:
        logger.warning("optout: settings not restored (%s)", type(exc).__name__)
        restored = []
    configured = cfg.is_configured()
    signed_in = configured and auth.TokenCache(data).signed_in()
    if signed_in:
        port = _ensure(cfg, data)
    else:
        port = _running_port(data) if configured else None
    (data / lifecycle.OPT_OUT_FILE).write_text("", encoding="utf-8")
    if port is not None:
        event = {"name": "opt_out", "plugin_version": PLUGIN_VERSION, "ts": iso_ms(time.time())}
        lifecycle.post_json(port, "/event", data, {"signal": "event", "payload": event})
        lifecycle.post_json(port, "/flush", data, {})
    elif not signed_in:
        _delete_spool_when_idle(cfg, data)
    return len(restored), signed_in


def _optout(args: argparse.Namespace) -> int:
    outcome = _opt_out(config.load())
    if outcome is None:
        _say("opt-out not recorded: the data directory cannot be created")
        return 1
    restored, signed_in = outcome
    after = "data already captured is uploaded, then the forwarder stops" if signed_in \
        else "data not yet uploaded is deleted"
    _say("opted out; {} setting(s) restored; {}; /telemetry on resumes".format(restored, after))
    return 0


def _on(args: argparse.Namespace) -> int:
    from . import lifecycle

    data = paths.data_dir(create=False)
    try:
        (data / lifecycle.OPT_OUT_FILE).unlink()
    except OSError:  # absent, or no data directory at all
        pass
    cfg, data = _configured_data()
    if cfg is None or data is None:
        _say("on, but not configured (dormant)")
        return 0
    try:
        _start_session(cfg, data, None)
    except Exception as exc:  # noqa: BLE001
        log.get_logger(data).warning("on: %s", type(exc).__name__)
        _say("on; the forwarder did not start (see forwarder.log)")
        return 0
    _say("on")
    return 0


def _off(args: argparse.Namespace) -> int:
    """Per-session off switch: put the user's settings back and stop the forwarder, silently."""
    from . import lifecycle, settings

    data = paths.data_dir(create=False)
    if not data.is_dir():
        return 0
    try:
        settings.restore(data)
    except Exception as exc:  # noqa: BLE001 - telemetry never fails a session
        log.get_logger(data).warning("off: settings not restored (%s)", type(exc).__name__)
    try:
        lifecycle.stop(data)
    except Exception as exc:  # noqa: BLE001
        log.get_logger(data).warning("off: stop failed (%s)", type(exc).__name__)
    return 0


def _wait_for_release(data: Path) -> bool:
    """True once no forwarder holds the lock, polling up to ``DRAIN_WAIT_S``."""
    from . import lifecycle

    deadline = time.monotonic() + DRAIN_WAIT_S
    while lifecycle.lock_held(data):
        if time.monotonic() >= deadline:
            return False
        time.sleep(DRAIN_POLL_S)
    return True


def _uninstall(args: argparse.Namespace) -> int:
    from . import lifecycle

    cfg = config.load()
    outcome = _opt_out(cfg)
    if outcome is None:
        _say("uninstall stopped: the data directory cannot be created")
        return 1
    restored, signed_in = outcome
    data = paths.data_dir()
    from . import git_event

    try:
        # Signed in, the forwarder uploads the rest (the opt_out event too) and exits by itself.
        if not (signed_in and _wait_for_release(data)):
            lifecycle.stop(data)
        # Nothing stays on the laptop: what the drain did not upload in time is deleted (R-04).
        _delete_spool_when_idle(cfg, data)
    except Exception as exc:  # noqa: BLE001
        log.get_logger(data).warning("uninstall: stop failed (%s)", type(exc).__name__)
    if git_event.uninstall_shims():
        shims = "git shims removed"
    else:
        shims = "git shims kept because git could not restore core.hooksPath"
    _say("uninstalled: opted out, {} setting(s) restored, forwarder stopped, {}".format(restored, shims))
    return 0


# ---------------------------------------------------------------------- git events


def _read_stdin_text() -> str:
    stream = sys.stdin
    try:
        if stream is None or stream.isatty():
            return ""
        text = stream.read(HOOK_STDIN_MAX)
    except (OSError, ValueError, AttributeError):
        return ""
    return text if isinstance(text, str) else ""


def _git_event(args: argparse.Namespace) -> int:
    """Record one git event when a forwarder already runs; drop it otherwise (never starts one)."""
    cfg = config.load()
    if not cfg.is_configured():
        return 0
    from . import lifecycle

    data = paths.data_dir(create=False)
    if not data.is_dir() or (data / lifecycle.OPT_OUT_FILE).exists():
        return 0
    from . import git_event

    try:
        port = git_event.forwarder_port(data)  # proof first: no git is run for an event nobody takes
        if port is None:
            return 0
        stdin = _read_stdin_text() if args.kind != "commit" else ""
        payload = git_event.collect(args.kind, list(args.hook_args), stdin, os.environ.get(git_event.CWD_ENV) or None)
        git_event.post(data, payload, port)
    except Exception as exc:  # noqa: BLE001 - a git command never fails on telemetry
        log.get_logger(data).warning("git-event: %s", type(exc).__name__)
    return 0


COMMANDS: Dict[str, Callable[[argparse.Namespace], int]] = {
    "start": _start,
    "forwarder": _forwarder,
    "status": _status,
    "login": _login,
    "optout": _optout,
    "on": _on,
    "off": _off,
    "git-event": _git_event,
    "uninstall": _uninstall,
    "ensure-running": _ensure_running,
}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cpp_telemetry")
    subcommands = parser.add_subparsers(dest="command", metavar="command")
    subcommands.required = True
    for name in COMMANDS:
        sub = subcommands.add_parser(name)
        if name == "git-event":
            sub.add_argument("kind", choices=GIT_KINDS)
            sub.add_argument("hook_args", nargs=argparse.REMAINDER)
    return parser


def main(argv: List[str]) -> int:
    try:
        args = _parser().parse_args(argv)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 2
    return COMMANDS[args.command](args)
