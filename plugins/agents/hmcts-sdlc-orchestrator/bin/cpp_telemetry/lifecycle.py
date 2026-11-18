"""Start, find, replace and stop the detached forwarder.

- ``<data>/forwarder.lock`` holds the pid of the running forwarder. A lock whose
  pid is dead (or is this process's own) is stale and is taken over.
- ``<data>/port`` holds the port the forwarder listens on. The default port comes
  first, then the scan range; a port is usable when it refuses connections or
  answers ``/healthz`` as one of our forwarders (status ok, a version string and
  its own port number).
- ``ensure_running`` keeps a forwarder of the same or a newer version, replaces an
  older one through ``POST /shutdown``, and otherwise starts a detached process
  with ``python3 -B`` and waits up to 3 s for its ``/healthz``.

All loopback calls use ``http.client`` directly, so no proxy setting applies.
"""
from __future__ import annotations

import http.client
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from . import log
from .config import PORT_MAX, PORT_MIN, Config
from .spool import Spool

LOCK_FILE = "forwarder.lock"
PORT_FILE = "port"
OPT_OUT_FILE = "opt-out"
START_WAIT_S = 3.0
STOP_WAIT_S = 5.0
TERM_WAIT_S = 2.0
POLL_S = 0.05

FREE, OURS, FOREIGN = "free", "ours", "foreign"

# Started children stay referenced for the life of this process (no ResourceWarning on collection).
_CHILDREN: List[subprocess.Popen] = []


class NotStarted(RuntimeError):
    """No forwarder could be found or started (reason in the message, never identity values)."""


def lock_path(data_dir: Path) -> Path:
    return Path(data_dir) / LOCK_FILE


def port_path(data_dir: Path) -> Path:
    return Path(data_dir) / PORT_FILE


# ---------------------------------------------------------------------- lock


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def read_lock_pid(data_dir: Path) -> Optional[int]:
    try:
        text = lock_path(data_dir).read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError):
        return None
    return int(text) if text.isdigit() else None


def lock_held(data_dir: Path) -> bool:
    """True when the lock names a live process other than this one."""
    pid = read_lock_pid(data_dir)
    return pid is not None and pid != os.getpid() and _pid_alive(pid)


class Lock:
    """The forwarder lock this process holds."""

    def __init__(self, path: Path, pid: int) -> None:
        self.path = path
        self.pid = pid

    def release(self) -> None:
        """Remove the lock file when it still names this process."""
        if read_lock_pid(self.path.parent) == self.pid:
            try:
                os.remove(str(self.path))
            except FileNotFoundError:
                pass


def _create_lock(path: Path, pid: int) -> bool:
    """Create the lock file with its content in one step; False when it already exists."""
    tmp = path.with_name("%s.%d.tmp" % (path.name, pid))
    try:
        with open(str(tmp), "w", encoding="utf-8") as fh:
            fh.write("%d\n" % pid)
        os.chmod(str(tmp), 0o600)
        try:
            os.link(str(tmp), str(path))  # atomic and exclusive: the lock is never seen empty
            return True
        except FileExistsError:
            return False
        except OSError:  # no hard links on this file system
            try:
                fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError:
                return False
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write("%d\n" % pid)
            return True
    finally:
        try:
            os.remove(str(tmp))
        except FileNotFoundError:
            pass


def acquire_lock(data_dir: Path) -> Optional[Lock]:
    """Take ``<data>/forwarder.lock``; None when a live process other than this one holds it."""
    path = lock_path(data_dir)
    me = os.getpid()
    for _ in range(3):
        if _create_lock(path, me):
            return Lock(path, me)
        holder = read_lock_pid(data_dir)
        if holder is not None and holder != me and _pid_alive(holder):
            return None
        # Stale: a dead pid, this process's own pid, or unreadable content.
        if read_lock_pid(data_dir) == holder:
            try:
                os.remove(str(path))
            except FileNotFoundError:
                pass
    return None


# ---------------------------------------------------------------------- port


def candidates(cfg: Config) -> List[int]:
    """The default port, then the scan range, without repeats."""
    low, high = cfg.port_scan
    ports = [cfg.port] + list(range(low, high + 1))
    return list(dict.fromkeys(ports))


def read_port(data_dir: Path) -> Optional[int]:
    try:
        text = port_path(data_dir).read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError):
        return None
    if not text.isdigit():
        return None
    port = int(text)
    return port if PORT_MIN <= port <= PORT_MAX else None


def write_port(data_dir: Path, port: int) -> None:
    path = port_path(data_dir)
    tmp = path.with_name(path.name + ".%d.tmp" % os.getpid())
    tmp.write_text("%d\n" % port, encoding="utf-8")
    os.replace(str(tmp), str(path))


def _connection(port: int, timeout: float) -> http.client.HTTPConnection:
    return http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)


def _read_json(conn: http.client.HTTPConnection, method: str, path: str) -> Tuple[int, Optional[dict]]:
    conn.request(method, path, body=b"" if method == "POST" else None,
                 headers={"Content-Type": "application/json"} if method == "POST" else {})
    resp = conn.getresponse()
    raw = resp.read(65536)
    try:
        data = json.loads(raw.decode("utf-8")) if raw else None
    except (UnicodeDecodeError, ValueError):
        data = None
    return resp.status, data if isinstance(data, dict) else None


def _is_ours(body: Optional[dict], port: int) -> bool:
    return (
        isinstance(body, dict)
        and body.get("status") == "ok"
        and isinstance(body.get("version"), str)
        and body.get("port") == port
    )


def healthz(port: int, timeout: float = 0.5) -> Optional[dict]:
    """The ``/healthz`` body of one of our forwarders on ``port``, else None."""
    conn = _connection(port, timeout)
    try:
        status, body = _read_json(conn, "GET", "/healthz")
    except (OSError, http.client.HTTPException):
        return None
    finally:
        conn.close()
    return body if status == 200 and _is_ours(body, port) else None


def _probe(port: int, timeout: float = 0.5) -> Tuple[str, Optional[dict]]:
    conn = _connection(port, timeout)
    try:
        conn.connect()
    except ConnectionRefusedError:
        conn.close()
        return FREE, None
    except OSError:
        conn.close()
        return FOREIGN, None
    try:
        status, body = _read_json(conn, "GET", "/healthz")
    except (OSError, http.client.HTTPException):
        return FOREIGN, None
    finally:
        conn.close()
    return (OURS, body) if status == 200 and _is_ours(body, port) else (FOREIGN, None)


def _post(port: int, path: str, timeout: float = 2.0) -> Optional[int]:
    conn = _connection(port, timeout)
    try:
        status, _ = _read_json(conn, "POST", path)
        return status
    except (OSError, http.client.HTTPException):
        return None
    finally:
        conn.close()


def choose_port(cfg: Config, data_dir: Path) -> int:
    """The first candidate that refuses or answers our healthz; written to ``<data>/port``."""
    for port in candidates(cfg):
        kind, _ = _probe(port)
        if kind in (FREE, OURS):
            write_port(data_dir, port)
            return port
    raise NotStarted("no usable port in the scan range")


# ---------------------------------------------------------------------- process


def _version_key(version: str) -> Optional[Tuple[int, ...]]:
    parts = version.split(".")
    return tuple(int(p) for p in parts) if all(p.isdigit() for p in parts) else None


def _is_older(running: str, ours: str) -> bool:
    a, b = _version_key(running), _version_key(ours)
    if a is None or b is None:
        return running != ours
    return a < b


def _wait_until(condition: Callable[[], bool], timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while True:
        if condition():
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(POLL_S)


def _spawn(plugin_root: Path, data_dir: Path) -> subprocess.Popen:
    env = dict(os.environ)
    env["CLAUDE_PLUGIN_DATA"] = str(data_dir)
    env["CLAUDE_PLUGIN_ROOT"] = str(plugin_root)
    return subprocess.Popen(
        [sys.executable, "-B", str(Path(plugin_root) / "bin" / "cpp_telemetry"), "forwarder"],
        start_new_session=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
        env=env,
        cwd=str(data_dir),
    )


def _stopped(port: int, data_dir: Path) -> bool:
    return healthz(port) is None and not lock_held(data_dir)


def _running(port: int, version: str, data_dir: Path) -> Optional[int]:
    """``port`` when our forwarder there is the same or newer; an older one is shut down first."""
    kind, body = _probe(port)
    if kind != OURS or body is None:
        return None
    if not _is_older(body["version"], version):
        return port
    _post(port, "/shutdown")
    if not _wait_until(lambda: _stopped(port, data_dir), STOP_WAIT_S):
        log.get_logger(data_dir).warning("older forwarder did not stop within %d s", int(STOP_WAIT_S))
    return None


def ensure_running(cfg: Config, data_dir: Path, plugin_root: Path, version: str) -> int:
    """Return the port of a running forwarder of this version (or newer), starting one when needed."""
    data_dir = Path(data_dir)
    recorded = read_port(data_dir)
    if recorded is not None:
        port = _running(recorded, version, data_dir)
        if port is not None:
            return port
    if (data_dir / OPT_OUT_FILE).exists() and Spool(data_dir, cfg).is_empty():
        raise NotStarted("opted out with an empty spool")
    port = choose_port(cfg, data_dir)
    if port != recorded:  # an older forwarder found here is shut down and its port reused
        running = _running(port, version, data_dir)
        if running is not None:
            return running
    _CHILDREN.append(_spawn(plugin_root, data_dir))
    deadline = time.monotonic() + START_WAIT_S
    while time.monotonic() < deadline:
        current = read_port(data_dir) or port
        body = healthz(current)
        if body is not None and body["version"] == version:
            return current
        time.sleep(POLL_S)
    raise NotStarted("forwarder did not answer within %d s" % int(START_WAIT_S))


def stop(data_dir: Path) -> bool:
    """Stop the running forwarder: ``POST /shutdown``, then SIGTERM to the lock's pid.

    Returns True when a forwarder was running and has stopped, False when none was.
    """
    data_dir = Path(data_dir)
    port = read_port(data_dir)
    answered = port is not None and healthz(port) is not None
    if not answered and not lock_held(data_dir):
        return False
    if answered:
        _post(port, "/shutdown")  # type: ignore[arg-type]

    def gone() -> bool:
        return not lock_held(data_dir) and (port is None or healthz(port) is None)

    if _wait_until(gone, STOP_WAIT_S):
        return True
    pid = read_lock_pid(data_dir)
    if pid is not None and lock_held(data_dir):
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
    return _wait_until(gone, TERM_WAIT_S)
