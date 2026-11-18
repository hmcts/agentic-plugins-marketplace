"""Start, find, replace and stop the detached forwarder.

- ``<data>/forwarder.lock`` holds the pid of the running forwarder. The lock is held
  only while that pid is alive and is a forwarder: its command line names
  ``cpp_telemetry``, or a forwarder answers the healthz proof for this data
  directory. Anything else (a dead pid, this process's own, a pid reused by an
  unrelated process after a reboot) is stale: it is taken over and never signalled.
- ``<data>/token`` holds 32 random hex characters (mode 0600), written by the
  forwarder at start when absent. Control requests carry it in
  ``X-Cpp-Telemetry-Token``; ``read_token`` serves the nudge script, git shims and CLI.
- ``<data>/port`` holds the port the forwarder listens on. The default port comes
  first, then the scan range; a port is usable when it refuses connections or
  answers ``/healthz?nonce=<fresh hex>`` as one of our forwarders: status ok, a
  version string, its own port number and ``proof`` = HMAC-SHA256(token, nonce).
  A listener without a valid proof is foreign, whatever body it echoes.
- ``ensure_running`` keeps a forwarder of the same or a newer version, replaces an
  older one through ``POST /shutdown``, and otherwise starts a detached process
  with ``python3 -I -B`` (isolated: no cwd, no PYTHON* variables, no user site) and
  waits up to 3 s for its ``/healthz``.

All loopback calls use ``http.client`` directly, so no proxy setting applies.
"""
from __future__ import annotations

import hmac
import http.client
import json
import os
import re
import secrets
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from . import log
from .config import PORT_MAX, PORT_MIN, Config
from .receiver import OPT_OUT_FILE, TOKEN_HEADER, healthz_proof, valid_version
from .spool import Spool

LOCK_FILE = "forwarder.lock"
PORT_FILE = "port"
TOKEN_FILE = "token"
_TOKEN_RE = re.compile(r"[0-9a-f]{32}")
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


def read_token(data_dir: Path) -> Optional[str]:
    """The control token in ``<data>/token``, or None when absent or malformed."""
    try:
        text = (Path(data_dir) / TOKEN_FILE).read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError):
        return None
    return text if _TOKEN_RE.fullmatch(text) else None


def ensure_token(data_dir: Path) -> str:
    """Return the token, writing a fresh one (mode 0600) when it is absent or malformed."""
    existing = read_token(data_dir)
    if existing is not None:
        return existing
    token = secrets.token_hex(16)
    path = Path(data_dir) / TOKEN_FILE
    tmp = path.with_name("%s.%d.tmp" % (TOKEN_FILE, os.getpid()))
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(token + "\n")
        os.chmod(str(tmp), 0o600)
        os.replace(str(tmp), str(path))
    finally:
        try:
            os.remove(str(tmp))
        except FileNotFoundError:
            pass
    return token


def _forwarder_argv(argv: List[str]) -> bool:
    """An argv entry naming the package (``.../cpp_telemetry`` or ``cpp_telemetry``) followed by ``forwarder``."""
    for here, after in zip(argv, argv[1:]):
        if (here == "cpp_telemetry" or here.endswith("/cpp_telemetry")) and after == "forwarder":
            return True
    return False


def _names_forwarder(pid: int) -> bool:
    """True when the process's argv runs the forwarder (``/proc`` on Linux, ``ps -o args=`` elsewhere)."""
    if os.path.exists("/proc/self/cmdline"):
        try:
            with open("/proc/%d/cmdline" % pid, "rb") as fh:
                raw = fh.read()
        except OSError:
            return False
        argv = [part.decode("utf-8", "replace") for part in raw.split(b"\0") if part]
        return _forwarder_argv(argv)
    try:
        out = subprocess.run(["ps", "-o", "args=", "-p", str(pid)], stdin=subprocess.DEVNULL,
                             stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=2, check=False)
    except (OSError, subprocess.SubprocessError):
        return False
    return _forwarder_argv(out.stdout.decode("utf-8", "replace").split())


def _holder_is_forwarder(pid: int, data_dir: Path) -> bool:
    if pid == os.getpid() or not _pid_alive(pid):
        return False
    if _names_forwarder(pid):
        return True
    port = read_port(data_dir)
    return port is not None and healthz(port, data_dir) is not None


def read_lock_pid(data_dir: Path) -> Optional[int]:
    try:
        text = lock_path(data_dir).read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError):
        return None
    return int(text) if text.isdigit() else None


def lock_held(data_dir: Path) -> bool:
    """True when the lock names a live forwarder other than this process."""
    pid = read_lock_pid(data_dir)
    return pid is not None and _holder_is_forwarder(pid, data_dir)


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
        if holder is not None and _holder_is_forwarder(holder, data_dir):
            return None
        # Stale: a dead pid, this process's own pid, a pid that is not a forwarder, or unreadable content.
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


def _is_ours(body: Optional[dict], port: int, nonce: str, token: Optional[str]) -> bool:
    """Our forwarder: the healthz shape plus a proof made with this data directory's token.

    Never raises: a malformed body (a non-ASCII or non-string version, a port that is
    not an int, a proof that is not a string) is simply not ours.
    """
    if token is None or not isinstance(body, dict):
        return False
    version, reported, proof = body.get("version"), body.get("port"), body.get("proof")
    if body.get("status") != "ok" or not valid_version(version) or not isinstance(proof, str):
        return False
    if not isinstance(reported, int) or isinstance(reported, bool) or reported != port:
        return False
    try:
        expected = healthz_proof(token, nonce, port, version)
        return hmac.compare_digest(proof.encode("utf-8", "replace"), expected.encode("ascii"))
    except Exception:  # noqa: BLE001 - anything odd in the answer means the listener is not ours
        return False


def healthz(port: int, data_dir: Path, timeout: float = 0.5) -> Optional[dict]:
    """The ``/healthz`` body of our forwarder on ``port`` (proof checked with ``data_dir``'s token), else None."""
    kind, body = _probe(port, data_dir, timeout)
    return body if kind == OURS else None


def _probe(port: int, data_dir: Path, timeout: float = 0.5) -> Tuple[str, Optional[dict]]:
    token = read_token(data_dir)
    nonce = secrets.token_hex(16)
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
        status, body = _read_json(conn, "GET", "/healthz?nonce=" + nonce)
    except (OSError, http.client.HTTPException):
        return FOREIGN, None
    finally:
        conn.close()
    return (OURS, body) if status == 200 and _is_ours(body, port, nonce, token) else (FOREIGN, None)


def _post(port: int, path: str, data_dir: Path, timeout: float = 2.0) -> Optional[int]:
    """POST an empty JSON object with the control token; the status, or None on no answer."""
    return post_json(port, path, data_dir, {}, timeout)


def post_json(port: int, path: str, data_dir: Path, body: dict, timeout: float = 2.0) -> Optional[int]:
    """POST ``body`` as JSON with the control token; the status, or None on no answer.

    ``port`` must come from ``ensure_running`` in the same invocation (ruling 23):
    never post the token to a port read from ``<data>/port`` without the proof check.
    """
    headers = {"Content-Type": "application/json"}
    token = read_token(data_dir)
    if token is not None:
        headers[TOKEN_HEADER] = token
    conn = _connection(port, timeout)
    try:
        conn.request("POST", path, body=json.dumps(body).encode("utf-8"), headers=headers)
        resp = conn.getresponse()
        resp.read(65536)
        return resp.status
    except (OSError, http.client.HTTPException):
        return None
    finally:
        conn.close()


def choose_port(cfg: Config, data_dir: Path) -> int:
    """The first candidate that refuses or answers our healthz; written to ``<data>/port``."""
    for port in candidates(cfg):
        kind, _ = _probe(port, data_dir)
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
        [sys.executable, "-I", "-B", str(Path(plugin_root) / "bin" / "cpp_telemetry"), "forwarder"],
        start_new_session=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
        env=env,
        cwd=str(data_dir),
    )


def _stopped(port: int, data_dir: Path) -> bool:
    return healthz(port, data_dir) is None and not lock_held(data_dir)


def _running(port: int, version: str, data_dir: Path) -> Optional[int]:
    """``port`` when our forwarder there is the same or newer; an older one is shut down first."""
    kind, body = _probe(port, data_dir)
    if kind != OURS or body is None:
        return None
    if not _is_older(body["version"], version):  # compared only after the proof passed
        return port
    _post(port, "/shutdown", data_dir)
    if not _wait_until(lambda: _stopped(port, data_dir), STOP_WAIT_S):
        log.get_logger(data_dir).warning("older forwarder did not stop within %d s", int(STOP_WAIT_S))
    return None


def _find_locked(cfg: Config, data_dir: Path, version: str) -> Optional[int]:
    """The port of the forwarder holding the lock, searched over every candidate for up to 3 s.

    None when that forwarder was older and has been shut down (the caller starts a new one).
    """
    deadline = time.monotonic() + START_WAIT_S
    while True:
        for port in candidates(cfg):
            kind, _ = _probe(port, data_dir)
            if kind == OURS:
                write_port(data_dir, port)
                return _running(port, version, data_dir)
        if time.monotonic() >= deadline or not lock_held(data_dir):
            raise NotStarted("the lock holder answers on no candidate port")
        time.sleep(POLL_S)


def ensure_running(cfg: Config, data_dir: Path, plugin_root: Path, version: str) -> int:
    """Return the port of a running forwarder of this version (or newer), starting one when needed."""
    data_dir = Path(data_dir)
    recorded = read_port(data_dir)
    if recorded is not None:
        port = _running(recorded, version, data_dir)
        if port is not None:
            return port
    if lock_held(data_dir):
        # A live forwarder holds the lock but not the recorded port: find it, never spawn a second one.
        found = _find_locked(cfg, data_dir, version)
        if found is not None:
            return found
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
        body = healthz(current, data_dir)
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
    answered = port is not None and healthz(port, data_dir) is not None
    if not answered and not lock_held(data_dir):
        return False  # nothing of ours runs: a stale or unrelated pid is never signalled
    if answered:
        _post(port, "/shutdown", data_dir)  # type: ignore[arg-type]

    def gone() -> bool:
        return not lock_held(data_dir) and (port is None or healthz(port, data_dir) is None)

    if _wait_until(gone, STOP_WAIT_S):
        return True
    pid = read_lock_pid(data_dir)
    if pid is not None and _pid_alive(pid) and _names_forwarder(pid):  # never signal a pid that is not a forwarder
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
    return _wait_until(gone, TERM_WAIT_S)
