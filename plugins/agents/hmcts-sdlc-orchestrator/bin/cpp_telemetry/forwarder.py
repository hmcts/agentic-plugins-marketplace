"""The detached forwarder process: lock, reaper, receiver thread and the 5-second loop.

``run`` takes ``<data>/forwarder.lock`` first (another live forwarder means exit 0),
then reaps orphaned open batches, writes ``<data>/token`` when absent, binds the receiver (the port in ``<data>/port``
when it is one of the configured candidates, else ``lifecycle.choose_port``) and
calls ``tick(now)`` every ``LOOP_INTERVAL_S``. There is no idle exit. The loop
ends on SIGTERM, on ``POST /shutdown``, or once ``<data>/opt-out`` exists and the
spool holds no batch; every open batch is then closed and the lock released.

``_default_tick`` builds the upload step: one ``uploader.Uploader`` per run, with
this run's ``Spool``, ``ForwarderState`` and a ``TokenCache`` on ``<data>``.
``_default_on_hook`` builds the hook handler: ``snapshot.from_hook`` with this
run's ``IdentityProvider``; a SessionStart's engine version is stamped on the spool.
"""
from __future__ import annotations

import logging
import signal
import threading
import time
from pathlib import Path
from typing import Callable, List, Optional

from . import lifecycle, log, snapshot
from .auth import TokenCache
from .config import Config
from .receiver import ForwarderState, IdentityProvider, Receiver, read_trusted_email
from .spool import Spool
from .uploader import REJECTED_UNTIL_FILE, Uploader

__all__ = ["ForwarderState", "run", "LOOP_INTERVAL_S", "REJECTED_UNTIL_FILE"]

LOOP_INTERVAL_S = 5.0

Tick = Callable[[float], None]
OnHook = Callable[[dict], List[dict]]


def _default_tick(cfg: Config, data_dir: Path, spool: Spool, state: ForwarderState) -> Tick:
    """The upload step: one uploader for this run, called with ``now`` every ``LOOP_INTERVAL_S``."""
    return Uploader(cfg, spool, TokenCache(data_dir), state, log.get_logger(data_dir), data_dir=data_dir).tick


def _default_on_hook(version: str, state: ForwarderState, identity: Optional[IdentityProvider] = None,
                     spool: Optional[Spool] = None) -> OnHook:
    """The hook handler: ``snapshot.from_hook`` with this run's identity; stamps the engine version on the spool."""

    def on_hook(hook: dict) -> List[dict]:
        ident = identity(None, None) if identity is not None else None
        envelopes = snapshot.from_hook(hook, version, state, ident=ident)
        if spool is not None and state.engine_version is not None:
            spool.set_engine_version(state.engine_version)
        return envelopes

    return on_hook


def _read_rejected_until(data_dir: Path) -> float:
    try:
        return float((data_dir / REJECTED_UNTIL_FILE).read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return 0.0


def _bind(cfg: Config, data_dir: Path, make: Callable[[int], Receiver], logger: logging.Logger) -> Optional[Receiver]:
    recorded = lifecycle.read_port(data_dir)
    if recorded is not None and recorded in lifecycle.candidates(cfg):
        try:
            return make(recorded)
        except OSError:
            pass
    try:
        port = lifecycle.choose_port(cfg, data_dir)
        receiver = make(port)
    except (OSError, lifecycle.NotStarted) as exc:
        logger.error("forwarder not started: no port could be bound (%s)", type(exc).__name__)
        return None
    return receiver


def _install_sigterm(stop: threading.Event, reasons: List[str]) -> Callable[[], None]:
    """Route SIGTERM to the stop event (main thread only); returns the restore step."""
    if threading.current_thread() is not threading.main_thread():
        return lambda: None

    def on_term(signum, frame) -> None:
        reasons.append("sigterm")
        stop.set()

    previous = signal.signal(signal.SIGTERM, on_term)
    return lambda: signal.signal(signal.SIGTERM, previous)


def run(cfg: Config, data_dir: Path, plugin_root: Path, version: str, tick: Optional[Tick] = None, *,
        on_hook: Optional[OnHook] = None, clock: Callable[[], float] = time.time) -> int:
    """Run the forwarder until SIGTERM, ``/shutdown`` or opt-out with an empty spool; returns the exit code."""
    data_dir = Path(data_dir)
    logger = log.get_logger(data_dir)
    lock = lifecycle.acquire_lock(data_dir)
    if lock is None:
        logger.info("forwarder not started: another forwarder holds the lock")
        return 0
    try:
        return _serve(cfg, data_dir, version, tick, on_hook, clock, logger)
    finally:
        lock.release()


def _serve(cfg: Config, data_dir: Path, version: str, tick: Optional[Tick], on_hook: Optional[OnHook],
           clock: Callable[[], float], logger: logging.Logger) -> int:
    spool = Spool(data_dir, cfg, clock=clock)
    spool.reap_orphans()
    state = ForwarderState(rejected_until=_read_rejected_until(data_dir))
    token = lifecycle.ensure_token(data_dir)
    identity = IdentityProvider(trusted_email=read_trusted_email())
    stop = threading.Event()
    reasons: List[str] = []
    start_ts = clock()

    def on_shutdown() -> None:
        reasons.append("shutdown")
        stop.set()

    def make(port: int) -> Receiver:
        return Receiver(cfg, spool, identity, version,
                        on_hook or _default_on_hook(version, state, identity, spool), lambda event: None, state,
                        port=port, start_ts=start_ts, on_shutdown=on_shutdown, clock=clock, token=token)

    receiver = _bind(cfg, data_dir, make, logger)
    if receiver is None:
        return 1
    step = tick or _default_tick(cfg, data_dir, spool, state)
    server = threading.Thread(target=receiver.serve_forever, name="cpp-telemetry-receiver", daemon=True)
    server.start()
    restore = _install_sigterm(stop, reasons)
    logger.info("forwarder %s started on port %d", version, receiver.port)
    try:
        while not stop.wait(LOOP_INTERVAL_S):
            try:
                step(clock())
            except Exception as exc:  # noqa: BLE001 - the loop outlives any one failed step
                logger.error("upload step failed: %s", type(exc).__name__)
            if (data_dir / lifecycle.OPT_OUT_FILE).exists() and spool.is_empty():
                reasons.append("opt-out")
                break
    finally:
        restore()
        receiver.close()
        server.join(5)
        try:
            closed = len(spool.close_all())
        except Exception as exc:  # noqa: BLE001
            logger.error("drain failed: %s", type(exc).__name__)
            closed = 0
        logger.info("forwarder stopped (%s); %d batch(es) closed on drain", reasons[0] if reasons else "error", closed)
    return 0
