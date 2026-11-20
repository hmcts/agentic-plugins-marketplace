"""Command line: python3 -I -B "$CLAUDE_PLUGIN_ROOT/bin/cpp_telemetry" [--data-dir DIR] <command>.

``--data-dir`` names the plugin data directory and wins over ``CLAUDE_PLUGIN_DATA``.
Claude Code exports ``CLAUDE_PLUGIN_DATA`` to hook processes but not to the Bash tool,
so the ``/telemetry`` command passes the directory with this option (its text gets
``${CLAUDE_PLUGIN_DATA}`` substituted). An empty value is ignored. The command's
allowed-tools prefix lets the option through without a prompt and ``uninstall`` removes
the directory, so any other value must resolve (symlinks followed) to this plugin's own
folder directly under ``<config dir>/plugins/data`` (``~/.claude``, or
``CLAUDE_CONFIG_DIR``): its name is ``hmcts-sdlc-orchestrator`` or starts with
``hmcts-sdlc-orchestrator-``. Anything else, or the option given twice, is a usage
error. The value is exported before any command runs, so the forwarder this run may
spawn inherits it.

- ``start`` (SessionStart hook): dormant check (dormant with a ``managed-keys.json`` left
  from before, the ``off`` steps run: the keys are taken back and the forwarder stopped,
  silently; a plain dormant start touches nothing); silent when ``<data>/opt-out`` exists,
  where batches left in the spool get a drain-only forwarder (signed in) or are deleted
  (signed out), so they never stay for good; otherwise ``lifecycle.ensure_running`` first, then ``settings.apply`` with the port it
  returns; one line naming the competing keys ``apply`` moved aside (names only,
  no chaining: D-49); the git shims (``git_event.install_shims``); the daily sign-in notice; one line when
  the plugin is behind the marketplace and autoUpdate could not be set; then the
  hook JSON on stdin, when it names a ``hook_event_name``, goes to ``/hook``.
- ``forwarder``: run the forwarder in this process (the detached child).
- ``status``: forwarder, spool, last ack, sign-in, roster, opt-out and moved-aside keys.
- ``login``: device-code sign-in (exit 1 when not configured or not signed in).
- ``optout``: restore the settings, write ``<data>/opt-out``, post an ``opt_out``
  event and flush. Signed in, the forwarder refuses every new export and hook, uploads
  what was spooled before and exits once the spool is empty; signed out, no forwarder is started and the spool is deleted
  (by the running forwarder, or here when none runs).
- ``on``: remove ``<data>/opt-out``, then the ``start`` steps (stdin is not read).
- ``off`` (the SessionStart hook when ``CPP_HARNESS_TELEMETRY=off``): restore the settings
  when a record exists, then stop a running forwarder (``lifecycle.stop``: healthz proof,
  verified pid). Never writes ``<data>/opt-out`` and never deletes the spool, so the next
  normal start applies the keys again. Silent, always exit 0, creates no data directory.
- ``uninstall``: ``optout``; signed in, wait up to ``DRAIN_WAIT_S`` for the forwarder
  to drain and exit, else (and when signed out) stop it; point ``core.hooksPath`` back at
  ``cpp.previousHooksPath``, then remove the git shims directory (kept when git could not
  restore the hooks path); clear the token cache and remove the whole data directory
  (kept, and said so, while a forwarder still holds the lock). One line names the real
  outcome of each step: settings restored or the key names it could not restore, no
  forwarder running or its pid, hooks path restored or left as is, data removed or kept.
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
import shutil
import sys
import time
from pathlib import Path
from typing import Callable, Dict, List, NamedTuple, Optional, Tuple

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


def _install_shims(root: Path, data: Path) -> None:
    from . import git_event

    git_event.install_shims(root, PLUGIN_VERSION, data)


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
        _install_shims(root, data)
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


def _drain_after_opt_out(cfg: config.Config, data: Path) -> None:
    """Opted out with batches left: never leave them on the laptop for good (R-04).

    Signed in, a drain-only forwarder starts (``ensure_running`` starts one only while
    the spool holds a batch); its receiver refuses every export and hook, it uploads or
    expires what is left and exits once the spool is empty. Signed out, nothing can
    upload, so the spool is deleted (by a running forwarder itself, else here). Silent;
    stdin is not read and the settings stay restored.
    """
    from . import auth
    from .spool import SPOOL_DIR, Spool

    try:
        if not (data / SPOOL_DIR).exists() or Spool(data, cfg).is_empty():
            return
        if auth.TokenCache(data).signed_in():
            _ensure(cfg, data)
        else:
            _delete_spool_when_idle(cfg, data)
    except Exception as exc:  # noqa: BLE001 - a hook must never fail on telemetry
        log.get_logger(data).warning("start: drain after opt-out: %s", type(exc).__name__)


def _start(args: argparse.Namespace) -> int:
    cfg, data = _configured_data()
    if cfg is None or data is None:
        # Dormant: no settings key, no output, no process, no spool; keys left from before are taken back.
        _off_when_keys_left()
        return 0
    from . import lifecycle

    if (data / lifecycle.OPT_OUT_FILE).exists():
        _drain_after_opt_out(cfg, data)  # settings stay restored and nothing new is recorded
        return 0
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


class _OptedOut(NamedTuple):
    restored: int  # settings keys this opt-out put back
    signed_in: bool
    unrestored: Optional[List[str]]  # None when the settings were restored; else the recorded key names


def _recorded_keys(data: Path) -> List[str]:
    """The key names in ``managed-keys.json`` (written and moved aside), names only; [] when unreadable."""
    from . import settings

    try:
        record = json.loads(settings.managed_keys_path(data).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    names = set()
    for part in ("written", "removed"):
        entries = record.get(part) if isinstance(record, dict) else None
        if isinstance(entries, dict):
            names.update(k for k in entries if isinstance(k, str))
    return sorted(names)


def _opt_out(cfg: config.Config) -> Optional[_OptedOut]:
    """Restore the settings, write ``<data>/opt-out`` and tell the forwarder.

    Signed in: ``ensure_running`` first (before the opt-out file, which with an empty
    spool would stop it starting), then ``opt_out`` and ``/flush``; the forwarder
    uploads what is left and exits. Signed out: no forwarder is started; a running one
    (healthz proof on the recorded port) gets the event and deletes its spool itself;
    with none running the spool is deleted here. Returns the outcome, or None when the
    data directory cannot be made.
    """
    from . import auth, lifecycle, settings
    from .spool import iso_ms

    try:
        data = paths.data_dir()
    except OSError:
        return None
    logger = log.get_logger(data)
    unrestored: Optional[List[str]] = None
    try:
        restored = settings.restore(data)
    except (OSError, settings.SettingsError) as exc:
        logger.warning("optout: settings not restored (%s)", type(exc).__name__)
        restored = []
        unrestored = _recorded_keys(data)
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
    return _OptedOut(len(restored), signed_in, unrestored)


def _optout(args: argparse.Namespace) -> int:
    outcome = _opt_out(config.load())
    if outcome is None:
        _say("opt-out not recorded: the data directory cannot be created")
        return 1
    restored, signed_in = outcome.restored, outcome.signed_in
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


def _switch_off(data: Path, step: str) -> None:
    """Put the user's settings back and stop the forwarder, silently (errors go to the log by type)."""
    from . import lifecycle, settings

    try:
        settings.restore(data)
    except Exception as exc:  # noqa: BLE001 - telemetry never fails a session
        log.get_logger(data).warning("%s: settings not restored (%s)", step, type(exc).__name__)
    try:
        lifecycle.stop(data)
    except Exception as exc:  # noqa: BLE001
        log.get_logger(data).warning("%s: stop failed (%s)", step, type(exc).__name__)


def _off(args: argparse.Namespace) -> int:
    """Per-session off switch: put the user's settings back and stop the forwarder, silently."""
    data = paths.data_dir(create=False)
    if not data.is_dir():
        return 0
    _switch_off(data, "off")
    return 0


def _off_when_keys_left() -> None:
    """Dormant now (the override was removed or is invalid) with keys applied earlier still in place.

    The keys would point at a port nothing binds after a reboot, so they are taken back
    and the forwarder is stopped, as ``off`` does. A plain dormant start (no record)
    touches nothing and creates nothing.
    """
    from . import settings

    try:
        data = paths.data_dir(create=False)
        if settings.managed_keys_path(data).is_file():
            _switch_off(data, "start")
    except Exception:  # noqa: BLE001 - a hook must never fail on telemetry
        pass


def _wait_for_release(data: Path) -> bool:
    """True once no forwarder holds the lock, polling up to ``DRAIN_WAIT_S``."""
    from . import lifecycle

    deadline = time.monotonic() + DRAIN_WAIT_S
    while lifecycle.lock_held(data):
        if time.monotonic() >= deadline:
            return False
        time.sleep(DRAIN_POLL_S)
    return True


def _remove_data_dir(data: Path) -> bool:
    """Delete the whole data directory (tokens first); True when nothing of it is left."""
    from . import auth

    try:
        auth.TokenCache(data).clear()
    except OSError:
        pass  # the tree removal below still tries
    shutil.rmtree(str(data), ignore_errors=True)
    return not data.exists()


def _uninstall(args: argparse.Namespace) -> int:
    """Opt out, drain or stop, restore the git hooks path, remove the data directory; one line per outcome."""
    from . import git_event, lifecycle, settings

    cfg = config.load()
    outcome = _opt_out(cfg)
    if outcome is None:
        _say("uninstall stopped: the data directory cannot be created")
        return 1
    data = paths.data_dir()
    try:
        # Signed in, the forwarder uploads the rest (the opt_out event too) and exits by itself.
        if not (outcome.signed_in and _wait_for_release(data)):
            lifecycle.stop(data)
    except Exception as exc:  # noqa: BLE001
        log.get_logger(data).warning("uninstall: stop failed (%s)", type(exc).__name__)
    parts = ["opted out"]
    if outcome.unrestored is None:
        parts.append("{} setting(s) restored".format(outcome.restored))
    else:
        names = ", ".join(outcome.unrestored) or "the keys it applied"
        parts.append("could not restore {} in {}; reset them by hand".format(names, settings.user_settings_path()))
    pid = lifecycle.read_lock_pid(data) if lifecycle.lock_held(data) else None
    if pid is None:
        parts.append("no forwarder running")
    else:
        parts.append("forwarder still running (pid {})".format(pid))
    if git_event.uninstall_shims():
        parts.append("git hooks path restored, git shims removed")
    else:
        parts.append("git hooks path left as is (git could not restore core.hooksPath), git shims kept")
    # Nothing stays on the laptop (R-04). Last filesystem step: nothing below may log or recreate the directory.
    if pid is not None:
        parts.append("data directory kept while the forwarder runs ({}); run /telemetry uninstall again".format(data))
    elif _remove_data_dir(data):
        parts.append("data removed")
    else:
        parts.append("data directory not fully removed ({})".format(data))
    _say("uninstalled: " + "; ".join(parts))
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


class _Once(argparse.Action):
    """Refuse a second ``--data-dir``: arguments after the command's own cannot replace it."""

    def __call__(self, parser, namespace, values, option_string=None):
        if getattr(namespace, self.dest, None) is not None:
            parser.error("{} given twice".format(option_string))
        setattr(namespace, self.dest, values)


def _plugin_data_roots() -> List[Path]:
    """The real paths of ``<config dir>/plugins/data``: ``~/.claude`` and ``CLAUDE_CONFIG_DIR``."""
    bases = [Path.home() / ".claude"]
    config_dir = os.environ.get("CLAUDE_CONFIG_DIR")
    if config_dir:
        bases.append(Path(config_dir))
    return [Path(os.path.realpath(str(base / "plugins" / "data"))) for base in bases]


def _is_own_data_dir(value: str) -> bool:
    """True when ``value`` is absolute and resolves to this plugin's folder in a plugins data root."""
    if not os.path.isabs(value):
        return False
    real = Path(os.path.realpath(value))
    named = real.name == paths.PLUGIN_NAME or real.name.startswith(paths.PLUGIN_NAME + "-")
    return named and real.parent in _plugin_data_roots()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cpp_telemetry")
    parser.add_argument("--data-dir", default=None, metavar="DIR", action=_Once)
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
    if args.data_dir:
        if not _is_own_data_dir(args.data_dir):
            _say("--data-dir must name this plugin's folder in the plugins data directory")
            return 2
        os.environ["CLAUDE_PLUGIN_DATA"] = os.path.realpath(args.data_dir)
    return COMMANDS[args.command](args)
