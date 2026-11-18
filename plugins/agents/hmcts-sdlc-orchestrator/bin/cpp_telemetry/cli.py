"""Command line: python3 "$CLAUDE_PLUGIN_ROOT/bin/cpp_telemetry" <command>.

Exit codes: 0 on success (including every dormant run), 2 on a usage error.
"""
from __future__ import annotations

import argparse
from typing import Callable, Dict, List

from . import PLUGIN_VERSION, config, log, paths


def _start(args: argparse.Namespace) -> int:
    cfg = config.load()
    if not cfg.is_configured():
        # Dormant: no settings key, no output, no process, no spool.
        return 0
    # The configured path (settings merge, forwarder start) is added by later tasks.
    return 0


def _forwarder(args: argparse.Namespace) -> int:
    """Run the forwarder in this process (the detached child ``ensure-running`` starts)."""
    cfg = config.load()
    if not cfg.is_configured():
        return 0  # dormant: no process
    from . import forwarder

    return forwarder.run(cfg, paths.data_dir(), paths.plugin_root(), PLUGIN_VERSION)


def _ensure_running(args: argparse.Namespace) -> int:
    """Find or start the forwarder; always exit 0 (errors go to the log by type)."""
    cfg = config.load()
    if not cfg.is_configured():
        return 0
    try:
        data = paths.data_dir()
    except OSError:
        return 0
    from . import lifecycle

    try:
        lifecycle.ensure_running(cfg, data, paths.plugin_root(), PLUGIN_VERSION)
    except Exception as exc:  # noqa: BLE001 - a hook must never fail on telemetry
        log.get_logger(data).warning("ensure-running: %s", type(exc).__name__)
    return 0


def _not_wired(args: argparse.Namespace) -> int:
    """Placeholder for a subcommand whose body a later task adds."""
    return 0


COMMANDS: Dict[str, Callable[[argparse.Namespace], int]] = {
    "start": _start,
    "forwarder": _forwarder,
    "status": _not_wired,
    "login": _not_wired,
    "optout": _not_wired,
    "on": _not_wired,
    "git-event": _not_wired,
    "uninstall": _not_wired,
    "ensure-running": _ensure_running,
}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cpp_telemetry")
    subcommands = parser.add_subparsers(dest="command", metavar="command")
    subcommands.required = True
    for name in COMMANDS:
        subcommands.add_parser(name)
    return parser


def main(argv: List[str]) -> int:
    try:
        args = _parser().parse_args(argv)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 2
    return COMMANDS[args.command](args)
