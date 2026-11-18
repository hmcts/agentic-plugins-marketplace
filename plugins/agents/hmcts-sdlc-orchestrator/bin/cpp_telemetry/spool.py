"""Per-session batches on disk between the receiver and the uploader.

Layout under ``<data>/spool/<session_id>/``:

- ``<batch_seq>.open.jsonl`` -- the session's open batch, one envelope per line:
  ``{"signal": "metrics"|"logs"|"traces"|"hook"|"event", "received_at": "<ISO-8601 UTC, ms>", "payload": {...}}``.
- ``<batch_seq>.json.gz`` -- a closed batch, gzip of ``{"plugin_version", "engine_version",
  "session_id", "batch_seq", "content_sha256", "events"}``.
- ``manifest.json`` -- ``{"open_seq": int|null, "last_seq": int}``.

``batch_seq`` is the milliseconds since the epoch when the batch opens, forced to
``max(previous + 1, now_ms)`` per session so a number is never reused. A batch closes
once it holds ``batch_max_bytes`` of JSON lines or ``batch_max_age_s`` after its first
record; a record that would take a non-empty batch past the size limit closes it first.
A closed batch older than ``dwell_days`` is deleted and a ``gap`` envelope takes its
place in the session's open batch.

Files are only ever removed from Python. Log lines carry counts and kinds, never
record content and never a refused session id.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
import re
import threading
import time
import zlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from . import PLUGIN_VERSION, log
from .config import Config

SPOOL_DIR = "spool"
MANIFEST = "manifest.json"
OPEN_SUFFIX = ".open.jsonl"
CLOSED_SUFFIX = ".json.gz"
TMP_SUFFIX = ".tmp"
SIGNALS = frozenset(("metrics", "logs", "traces", "hook", "event"))

_SESSION_RE = re.compile(r"[A-Za-z0-9._:-]{1,128}")
_OPEN_RE = re.compile(r"([0-9]{1,19})\.open\.jsonl")
_CLOSED_RE = re.compile(r"([0-9]{1,19})\.json\.gz")
_MS_PER_DAY = 86_400_000
_UNREADABLE = (OSError, EOFError, ValueError, TypeError, KeyError, RecursionError, zlib.error)


def content_sha256(events: List[dict]) -> str:
    """The batch hash: SHA-256 of the canonical JSON of the events in file order."""
    return hashlib.sha256(json.dumps(events, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def iso_ms(ts: float) -> str:
    """ISO-8601 UTC with milliseconds, e.g. ``2027-01-15T08:00:00.000Z``."""
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def valid_session_id(session_id: Any) -> bool:
    """True for an id that is safe as a directory name under the spool."""
    return (
        isinstance(session_id, str)
        and session_id != "."
        and ".." not in session_id
        and _SESSION_RE.fullmatch(session_id) is not None
    )


def _is_envelope(item: Any) -> bool:
    if not isinstance(item, dict):
        return False
    signal = item.get("signal")
    return isinstance(signal, str) and signal in SIGNALS and isinstance(item.get("payload"), dict)


def _reject_constant(name: str) -> Any:
    raise ValueError("non-finite number")


def _size(path: Path) -> int:
    try:
        return path.stat().st_size
    except FileNotFoundError:
        return 0


def _remove(path: Path) -> None:
    try:
        os.remove(str(path))
    except FileNotFoundError:
        pass


def _atomic_write(path: Path, data: bytes) -> None:
    tmp = path.with_name(path.name + TMP_SUFFIX)
    try:
        with open(str(tmp), "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(str(tmp), str(path))
    except BaseException:
        _remove(tmp)
        raise


def _numbered(directory: Path, pattern: "re.Pattern[str]") -> List[Tuple[int, Path]]:
    try:
        with os.scandir(str(directory)) as entries:
            found = [(int(m.group(1)), Path(e.path)) for e in entries for m in [pattern.fullmatch(e.name)] if m]
    except (FileNotFoundError, NotADirectoryError):
        return []
    return sorted(found)


def _read_events(path: Path) -> Tuple[List[dict], int]:
    """Envelopes of an open batch in file order, and the count of lines dropped as corrupt."""
    with open(str(path), "rb") as fh:
        raw = fh.read()
    events: List[dict] = []
    dropped = 0
    for chunk in raw.split(b"\n"):
        if not chunk.strip():
            continue
        try:
            item = json.loads(chunk.decode("utf-8"), parse_constant=_reject_constant)
        except (UnicodeDecodeError, ValueError, RecursionError):
            dropped += 1
            continue
        if not _is_envelope(item) or not isinstance(item.get("received_at"), str):
            dropped += 1
            continue
        events.append(item)
    return events, dropped


def _read_batch(path: Path) -> dict:
    with gzip.open(str(path), "rb") as fh:
        batch = json.loads(fh.read().decode("utf-8"))
    if not isinstance(batch, dict) or not isinstance(batch.get("events"), list):
        raise ValueError("not a batch")
    return batch


class Spool:
    """The on-disk spool. All public methods are safe to call from several threads."""

    def __init__(self, data_dir: Path, cfg: Config, clock: Callable[[], float] = time.time) -> None:
        self._data_dir = Path(data_dir)
        self._root = self._data_dir / SPOOL_DIR
        self._cfg = cfg
        self._clock = clock
        self._lock = threading.RLock()
        self._engine_version: Optional[str] = None
        # session id -> (batch_seq, time of the first record) of the batch this process opened.
        self._open: Dict[str, Tuple[int, float]] = {}

    @property
    def root(self) -> Path:
        return self._root

    def set_engine_version(self, version: Optional[str]) -> None:
        """Record the engine version stamped on batches closed from now on."""
        if version is None or isinstance(version, str):
            with self._lock:
                self._engine_version = version or None

    # ------------------------------------------------------------------ writing

    def append(self, session_id: str, envelope: dict) -> None:
        """Write one envelope line to the session's open batch, opening one when none is.

        A refused session id or an envelope that is not ``{signal, payload: object}`` with
        finite JSON values is logged by kind and ignored. A disk error propagates.
        """
        self._append_record(session_id, envelope)

    def _append_record(self, session_id: str, envelope: Any) -> Optional[dict]:
        logger = log.get_logger(self._data_dir)
        if not valid_session_id(session_id):
            length = len(session_id) if isinstance(session_id, str) else -1
            logger.warning("record ignored: session id refused (length %d)", length)
            return None
        built = self._record(envelope)
        if built is None:
            logger.warning("record ignored: envelope is not a valid record")
            return None
        record, line = built
        data = (line + "\n").encode("utf-8")
        with self._lock:
            path = self._current_path(session_id)
            if path is not None:
                size = _size(path)
                if size > 0 and size + len(data) > self._cfg.batch_max_bytes:
                    self._close(session_id, self._open[session_id][0])
                    path = None
            if path is None:
                path = self._open_batch(session_id)
            with open(str(path), "ab") as fh:
                fh.write(data)
        return record

    def _record(self, envelope: Any) -> Optional[Tuple[dict, str]]:
        if not _is_envelope(envelope):
            return None
        received_at = envelope.get("received_at")
        if not isinstance(received_at, str) or not received_at:
            received_at = iso_ms(self._clock())
        record = {"signal": envelope["signal"], "received_at": received_at, "payload": envelope["payload"]}
        try:
            return record, json.dumps(record, separators=(",", ":"), allow_nan=False)
        except (TypeError, ValueError, RecursionError):
            return None

    def _current_path(self, session_id: str) -> Optional[Path]:
        current = self._open.get(session_id)
        if current is None:
            return None
        path = self._root / session_id / (str(current[0]) + OPEN_SUFFIX)
        if not path.exists():  # removed from outside: start a fresh batch
            del self._open[session_id]
            return None
        return path

    def _open_batch(self, session_id: str) -> Path:
        seq = self.next_seq(session_id)
        self._root.mkdir(mode=0o700, parents=True, exist_ok=True)
        directory = self._root / session_id
        directory.mkdir(mode=0o700, exist_ok=True)
        self._write_manifest(session_id, seq, seq)
        self._open[session_id] = (seq, self._clock())
        return directory / (str(seq) + OPEN_SUFFIX)

    def next_seq(self, session_id: str) -> int:
        """``max(previous + 1, now_ms)``; previous is the highest number the session has used."""
        if not valid_session_id(session_id):
            raise ValueError("invalid session id")
        with self._lock:
            return max(self._previous_seq(session_id) + 1, int(self._clock() * 1000))

    def _previous_seq(self, session_id: str) -> int:
        directory = self._root / session_id
        open_seq, last_seq = self._read_manifest(session_id)
        seqs = [last_seq, -1 if open_seq is None else open_seq]
        seqs.extend(seq for seq, _ in _numbered(directory, _OPEN_RE))
        seqs.extend(seq for seq, _ in _numbered(directory, _CLOSED_RE))
        return max(seqs)

    # ------------------------------------------------------------------ manifest

    def _read_manifest(self, session_id: str) -> Tuple[Optional[int], int]:
        """``(open_seq, last_seq)``; ``(None, -1)`` when missing or unreadable."""
        try:
            data = json.loads((self._root / session_id / MANIFEST).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None, -1
        if not isinstance(data, dict):
            return None, -1

        def as_int(value: Any) -> Optional[int]:
            return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None

        last_seq = as_int(data.get("last_seq"))
        return as_int(data.get("open_seq")), -1 if last_seq is None else last_seq

    def _write_manifest(self, session_id: str, open_seq: Optional[int], last_seq: int) -> None:
        body = json.dumps({"open_seq": open_seq, "last_seq": last_seq}).encode("utf-8")
        _atomic_write(self._root / session_id / MANIFEST, body)

    def _settle_manifest(self, session_id: str, seen_seq: int) -> None:
        """Point ``open_seq`` at this process's open batch (or null) and keep ``last_seq`` maximal."""
        current = self._open.get(session_id)
        last_seq = max(self._previous_seq(session_id), seen_seq)
        self._write_manifest(session_id, None if current is None else current[0], last_seq)

    # ------------------------------------------------------------------ closing

    def _close(self, session_id: str, seq: int) -> Optional[Path]:
        """Close one open batch; returns the new ``.json.gz`` or None when nothing was written."""
        directory = self._root / session_id
        open_path = directory / (str(seq) + OPEN_SUFFIX)
        closed_path = directory / (str(seq) + CLOSED_SUFFIX)
        result: Optional[Path] = None
        try:
            if not closed_path.exists():  # else an earlier close finished before removing its open file
                try:
                    events, dropped = _read_events(open_path)
                except FileNotFoundError:
                    events, dropped = [], 0
                if dropped:
                    log.get_logger(self._data_dir).warning("closing a batch dropped %d corrupt line(s)", dropped)
                if events:
                    self._write_batch(closed_path, session_id, seq, events, self._engine_version)
                    result = closed_path
            _remove(open_path)
        finally:
            if self._open.get(session_id, (None,))[0] == seq:
                del self._open[session_id]
            self._settle_manifest(session_id, seq)
        return result

    def _write_batch(self, path: Path, session_id: str, seq: int, events: List[dict], engine: Optional[str],
                     plugin_version: str = PLUGIN_VERSION) -> None:
        batch = {
            "plugin_version": plugin_version,
            "engine_version": engine,
            "session_id": session_id,
            "batch_seq": seq,
            "content_sha256": content_sha256(events),
            "events": events,
        }
        _atomic_write(path, gzip.compress(json.dumps(batch, separators=(",", ":")).encode("utf-8")))

    def _open_files(self) -> List[Tuple[int, str, Path]]:
        found = []
        for session_id, directory in self._session_dirs():
            found.extend((seq, session_id, path) for seq, path in _numbered(directory, _OPEN_RE))
        return sorted(found)

    def _session_dirs(self) -> List[Tuple[str, Path]]:
        try:
            with os.scandir(str(self._root)) as entries:
                found = [(e.name, Path(e.path)) for e in entries
                         if e.is_dir(follow_symlinks=False) and valid_session_id(e.name)]
        except (FileNotFoundError, NotADirectoryError):
            return []
        return sorted(found)

    def close_due(self, now: Optional[float] = None) -> List[Path]:
        """Close every open batch at the size limit or at the age limit since its first record."""
        now = self._clock() if now is None else now
        closed = []
        with self._lock:
            for seq, session_id, path in self._open_files():
                current = self._open.get(session_id)
                opened_at = current[1] if current is not None and current[0] == seq else seq / 1000.0
                if _size(path) >= self._cfg.batch_max_bytes or now - opened_at >= self._cfg.batch_max_age_s:
                    self._close_logged(session_id, seq, closed)
        return closed

    def _close_logged(self, session_id: str, seq: int, closed: List[Path]) -> None:
        try:
            done = self._close(session_id, seq)
        except Exception as exc:  # noqa: BLE001 - one bad batch must not stop the others closing
            log.get_logger(self._data_dir).error("closing a batch failed: %s", type(exc).__name__)
            return
        if done is not None:
            closed.append(done)

    def close_all(self) -> List[Path]:
        """Close every open batch now (flush and shutdown)."""
        closed: List[Path] = []
        with self._lock:
            for seq, session_id, _ in self._open_files():
                self._close_logged(session_id, seq, closed)
        return closed

    def reap_orphans(self) -> List[Path]:
        """At start: close every ``*.open.jsonl`` left by an earlier run; never raises on a bad file."""
        logger = log.get_logger(self._data_dir)
        closed: List[Path] = []
        failed = 0
        with self._lock:
            for session_id, directory in self._session_dirs():
                try:
                    with os.scandir(str(directory)) as entries:
                        leftovers = [Path(e.path) for e in entries if e.name.endswith(TMP_SUFFIX)]
                    for leftover in leftovers:
                        _remove(leftover)
                    for seq, _ in _numbered(directory, _OPEN_RE):
                        done = self._close(session_id, seq)
                        if done is not None:
                            closed.append(done)
                    self._settle_manifest(session_id, -1)
                except _UNREADABLE:
                    failed += 1
        if closed or failed:
            logger.info("reaper closed %d orphan batch(es); %d session(s) failed", len(closed), failed)
        return closed

    # ------------------------------------------------------------------ closed batches

    def closed_batches_oldest_first(self) -> List[Path]:
        found = []
        with self._lock:
            for session_id, directory in self._session_dirs():
                found.extend((seq, session_id, path) for seq, path in _numbered(directory, _CLOSED_RE))
        return [path for _, _, path in sorted(found)]

    def _closed_path(self, path: Path) -> Tuple[str, int]:
        """``(session_id, batch_seq)`` of a closed batch file inside this spool, else ValueError."""
        path = Path(path)
        match = _CLOSED_RE.fullmatch(path.name)
        session_id = path.parent.name
        inside = Path(os.path.abspath(str(path.parent.parent))) == Path(os.path.abspath(str(self._root)))
        if not (match and inside and valid_session_id(session_id)):
            raise ValueError("not a closed batch of this spool")
        return session_id, int(match.group(1))

    def delete(self, path: Path) -> None:
        """Remove one closed batch (uploaded, or dropped by the uploader)."""
        self._closed_path(path)
        with self._lock:
            _remove(Path(path))

    def resequence(self, path: Path) -> Path:
        """Give a closed batch a new ``batch_seq``; same events, sha recomputed (events-only, so equal)."""
        session_id, _ = self._closed_path(path)
        path = Path(path)
        with self._lock:
            batch = _read_batch(path)
            seq = self.next_seq(session_id)
            new_path = path.with_name(str(seq) + CLOSED_SUFFIX)
            engine = batch.get("engine_version")
            plugin_version = batch.get("plugin_version")
            self._write_batch(new_path, session_id, seq, batch["events"],
                              engine if isinstance(engine, str) else None,
                              plugin_version if isinstance(plugin_version, str) else PLUGIN_VERSION)
            _remove(path)
            self._settle_manifest(session_id, seq)
        return new_path

    def drop_with_gap(self, path: Path, reason: str) -> Optional[dict]:
        """Delete a closed batch, recording a ``gap`` envelope in the session's open batch first.

        Returns the gap envelope as written. Used for the dwell limit here and by the
        uploader for batches the ingest refuses for good.
        """
        if not isinstance(reason, str) or not reason:
            raise ValueError("gap reason must be a non-empty string")
        session_id, seq = self._closed_path(path)
        path = Path(path)
        with self._lock:
            try:
                events = _read_batch(path)["events"]
                first, last = events[0].get("received_at"), events[-1].get("received_at")
                from_ts = first if isinstance(first, str) else None
                to_ts = last if isinstance(last, str) else None
            except _UNREADABLE + (IndexError, AttributeError):
                from_ts, to_ts = iso_ms(seq / 1000.0), None
            gap = {
                "signal": "event",
                "payload": {
                    "name": "gap",
                    "reason": reason,
                    "session_id": session_id,
                    "batch_seq": seq,
                    "from_ts": from_ts,
                    "to_ts": to_ts,
                },
            }
            written = self._append_record(session_id, gap)
            if written is None:  # never lose a batch without its gap record
                return None
            _remove(path)
        log.get_logger(self._data_dir).warning("batch dropped (%s); gap recorded", reason)
        return written

    def expire(self, now: Optional[float] = None) -> List[dict]:
        """Delete closed batches older than ``dwell_days``; return the gap envelopes written."""
        now = self._clock() if now is None else now
        now_ms = int(now * 1000)
        dwell_ms = self._cfg.dwell_days * _MS_PER_DAY
        gaps = []
        with self._lock:
            for path in self.closed_batches_oldest_first():
                if now_ms - self._closed_path(path)[1] > dwell_ms:
                    gap = self.drop_with_gap(path, "dwell")
                    if gap is not None:
                        gaps.append(gap)
            self._prune(now_ms - dwell_ms)
        return gaps

    def _prune(self, before_ms: int) -> None:
        """Remove session directories holding only a manifest whose last number is older than the dwell."""
        for session_id, directory in self._session_dirs():
            if session_id in self._open:
                continue
            try:
                with os.scandir(str(directory)) as entries:
                    names = [e.name for e in entries]
            except FileNotFoundError:
                continue
            if names not in ([], [MANIFEST]):
                continue
            open_seq, last_seq = self._read_manifest(session_id)
            if open_seq is None and last_seq < before_ms:
                _remove(directory / MANIFEST)
                try:
                    os.rmdir(str(directory))
                except OSError:
                    pass

    def clear(self) -> int:
        """Delete every batch, open file and manifest (the ingest refused this developer).

        Returns the number of batches (open and closed) removed. Session directories
        go too; the next append starts a fresh batch.
        """
        removed = 0
        with self._lock:
            for _, directory in self._session_dirs():
                try:
                    with os.scandir(str(directory)) as entries:
                        files = [(e.name, Path(e.path)) for e in entries if not e.is_dir(follow_symlinks=False)]
                except FileNotFoundError:
                    continue
                for name, path in files:
                    if _OPEN_RE.fullmatch(name) or _CLOSED_RE.fullmatch(name):
                        removed += 1
                    _remove(path)
                try:
                    os.rmdir(str(directory))
                except OSError:
                    pass
            self._open.clear()
        log.get_logger(self._data_dir).warning("spool cleared: %d batch(es) removed", removed)
        return removed

    # ------------------------------------------------------------------ size guard

    def total_bytes(self) -> int:
        total = 0
        for _, directory in self._session_dirs():
            try:
                with os.scandir(str(directory)) as entries:
                    files = [e.path for e in entries if e.is_file(follow_symlinks=False)]
            except (FileNotFoundError, NotADirectoryError):
                continue
            for path in files:
                try:
                    total += os.lstat(path).st_size
                except OSError:  # removed between the listing and the stat: skip only this file
                    continue
        return total

    def is_empty(self) -> bool:
        """True when the spool holds no open and no closed batch."""
        with self._lock:
            return not self._open_files() and not self.closed_batches_oldest_first()

    def is_full(self) -> bool:
        return self.total_bytes() > self._cfg.spool_max_bytes
