"""The upload step: closed batches, oldest first, to ``POST {ingest_url}/v1/batches``.

``Uploader.tick(now)`` runs on the forwarder's 5-second loop. It closes due
batches and expires old ones, then, unless the developer is refused
(``state.rejected_until > now``), in back-off, or signed out, sends closed batches
oldest first (at most ``MAX_BATCHES_PER_TICK``). The body is the ``.json.gz``
file as it is on disk (one plain gzip member) with ``Authorization: Bearer``,
``Content-Type: application/json`` and ``Content-Encoding: gzip``, timeout 30 s.

Replies:

- 200: delete the batch, ``state.last_ack = now``; the back-off and the 401 count reset.
- 401: drop the cached access token and stop until the next tick; after 3 in a
  row the refresh token goes too (the developer must sign in again).
- 403 ``not_on_roster``: ``state.rejected_until = now + 86,400``, the whole spool
  is cleared and ``<data>/rejected-until`` written. Any other 403 backs off.
- 409 ``sha_conflict``: resequence the batch and send it again (at most
  ``MAX_RESEQUENCE`` times a tick, then back off). Any other 409 (``session_not_owned``,
  ``session_owned_by_other_dev``) drops the batch with a gap ``rejected_409``.
- 413: drop with a gap ``too_large``; 400: drop with a gap ``rejected_400``. A batch
  over ``cfg.upload_max_bytes`` (on disk or inflated) is dropped the same way before
  any attempt.
- 429, 5xx, any other status, or no answer: back off 5 s doubling to 300 s,
  ``state.last_error`` set. A token refresh that fails while a refresh token is
  still cached backs off the same way (``token_refresh``).

A refused batch that holds only ``gap`` records is deleted without a new gap, so
a session the ingest refuses for good does not regress gap after gap.

Log lines carry status codes, error words, counts and exception class names:
never a token, a URL or batch content.
"""
from __future__ import annotations

import gzip
import json
import logging
import zlib
from pathlib import Path
from typing import Any, Optional

from . import auth
from .config import Config
from .spool import Spool

UPLOAD_TIMEOUT_S = 30.0
ME_TIMEOUT_S = 10.0
BACKOFF_MIN_S = 5
BACKOFF_MAX_S = 300
REJECT_FOR_S = 86_400
MAX_BATCHES_PER_TICK = 20
MAX_RESEQUENCE = 3
MAX_UNAUTHORIZED = 3
REJECTED_UNTIL_FILE = "rejected-until"

_NEXT, _STOP, _RESEQUENCED = "next", "stop", "resequenced"


def _inflated_size(body: bytes) -> int:
    """The gzip trailer's ISIZE (inflated length mod 2**32); 0 for a body too short to hold one."""
    return int.from_bytes(body[-4:], "little") if len(body) >= 18 else 0


def _only_gaps(body: bytes) -> bool:
    """True when the gzip batch holds events and every one is a ``gap`` record."""
    try:
        batch = json.loads(gzip.decompress(body).decode("utf-8"))
    except (OSError, EOFError, ValueError, zlib.error, RecursionError):
        return False
    events = batch.get("events") if isinstance(batch, dict) else None
    if not isinstance(events, list) or not events:
        return False
    return all(isinstance(e, dict) and e.get("signal") == "event" and isinstance(e.get("payload"), dict)
               and e["payload"].get("name") == "gap" for e in events)


class Uploader:
    """Sends closed batches; built once per forwarder run."""

    def __init__(self, cfg: Config, spool: Spool, cache: auth.TokenCache, state: Any, logger: logging.Logger,
                 *, data_dir: Optional[Path] = None) -> None:
        self._cfg = cfg
        self._spool = spool
        self._cache = cache
        self._state = state
        self._logger = logger
        self._data_dir = Path(data_dir) if data_dir is not None else cache.data_dir
        self.backoff_s = 0
        self.next_attempt_at = 0.0
        self._unauthorized = 0
        self._paused_logged = False

    @property
    def _url(self) -> str:
        return self._cfg.ingest_url.rstrip("/") + "/v1/batches"

    def tick(self, now: float) -> None:
        self._spool.close_due(now)
        self._spool.expire(now)
        if not self._cfg.ingest_url or self._state.rejected_until > now or now < self.next_attempt_at:
            return
        if not self._spool.closed_batches_oldest_first():
            return
        token = auth.get_access_token(self._cfg, self._cache, now=now)
        if token is None:
            if self._cache.signed_in():  # a refresh token is held: the refresh failed for now
                self._back_off(now, "token_refresh")
                return
            if not self._paused_logged:
                self._logger.info("upload paused: not signed in")
                self._paused_logged = True
            return
        self._paused_logged = False
        resequenced = 0
        for _ in range(MAX_BATCHES_PER_TICK):
            batches = self._spool.closed_batches_oldest_first()
            if not batches:
                return
            outcome = self._upload(batches[0], token, now)
            if outcome == _RESEQUENCED:
                resequenced += 1
                if resequenced > MAX_RESEQUENCE:
                    self._back_off(now, "sha_conflict")
                    return
            elif outcome == _STOP:
                return

    def _upload(self, path: Path, token: str, now: float) -> str:
        try:
            body = path.read_bytes()
        except FileNotFoundError:
            return _NEXT
        limit = self._cfg.upload_max_bytes
        if len(body) > limit or _inflated_size(body) > limit:
            self._logger.warning("batch over the upload limit (%d bytes on disk)", len(body))
            return self._drop(path, body, "too_large")
        headers = {"Authorization": "Bearer " + token, "Content-Type": "application/json",
                   "Content-Encoding": "gzip", "Accept": "application/json"}
        try:
            status, reply = auth.http_call("POST", self._url, body, headers, timeout=UPLOAD_TIMEOUT_S)
        except auth.TRANSPORT_ERRORS as exc:
            self._back_off(now, type(exc).__name__)
            return _STOP
        if status == 200:
            self._spool.delete(path)
            self._state.last_ack = now
            self._state.last_error = None
            self.backoff_s = 0
            self._unauthorized = 0
            return _NEXT
        word = auth.error_word(reply)
        if status == 401:
            self._on_unauthorized(token)
            return _STOP
        if status == 403 and word == "not_on_roster":
            self._on_not_on_roster(now)
            return _STOP
        if status == 409 and word == "sha_conflict":
            self._spool.resequence(path)
            return _RESEQUENCED
        reason = {409: "rejected_409", 413: "too_large", 400: "rejected_400"}.get(status)
        if reason is not None:
            self._logger.warning("upload refused: %d %s", status, word)
            return self._drop(path, body, reason)
        self._back_off(now, "http_%d" % status)
        return _STOP

    def _drop(self, path: Path, body: bytes, reason: str) -> str:
        if _only_gaps(body):
            self._spool.delete(path)
            self._logger.warning("gap-only batch dropped (%s); no new gap recorded", reason)
            return _NEXT
        if self._spool.drop_with_gap(path, reason) is None:
            return _STOP  # the batch stays: never lose one without its gap record
        return _NEXT

    def _on_unauthorized(self, token: str) -> None:
        self._unauthorized += 1
        self._state.last_error = "http_401"
        refresh = self._cache.load().get("refresh_token")
        ours = self._cache.drop_access_token(token)
        if self._unauthorized < MAX_UNAUTHORIZED:
            self._logger.warning("upload refused as unauthorized (%d in a row); access token dropped",
                                 self._unauthorized)
            return
        self._unauthorized = 0
        if ours and refresh is not None:
            self._cache.drop_refresh_token(refresh)
        self._logger.warning("upload refused as unauthorized %d times in a row; signed out", MAX_UNAUTHORIZED)

    def _on_not_on_roster(self, now: float) -> None:
        until = now + REJECT_FOR_S
        self._state.rejected_until = until  # first, so the receiver answers 503 before the spool goes
        self._state.last_error = "not_on_roster"
        removed = self._spool.clear()
        try:
            auth.write_private(self._data_dir / REJECTED_UNTIL_FILE, "{}\n".format(until))
        except OSError as exc:
            self._logger.error("rejected-until not written: %s", type(exc).__name__)
        self._logger.warning("not on the roster: %d batch(es) deleted; uploads paused for %d s",
                             removed, REJECT_FOR_S)

    def _back_off(self, now: float, error: str) -> None:
        self.backoff_s = BACKOFF_MIN_S if self.backoff_s == 0 else min(self.backoff_s * 2, BACKOFF_MAX_S)
        self.next_attempt_at = now + self.backoff_s
        self._state.last_error = error
        self._logger.warning("upload failed (%s); next attempt in %d s", error, self.backoff_s)


def probe_me(cfg: Config, cache: auth.TokenCache) -> Optional[dict]:
    """``GET {ingest_url}/v1/me`` with the cached token (10 s); None when signed out or on any failure."""
    if not cfg.ingest_url:
        return None
    token = auth.get_access_token(cfg, cache)
    if token is None:
        return None
    headers = {"Authorization": "Bearer " + token, "Accept": "application/json"}
    try:
        status, body = auth.http_call("GET", cfg.ingest_url.rstrip("/") + "/v1/me", None, headers,
                                      timeout=ME_TIMEOUT_S)
    except auth.TRANSPORT_ERRORS:
        return None
    return body if status == 200 and isinstance(body, dict) else None
