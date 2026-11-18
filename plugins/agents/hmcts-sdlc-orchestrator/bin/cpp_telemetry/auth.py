"""Device-code sign-in and the cached tokens.

Plain ``urllib`` against ``{auth_base_url}/oauth2/v2.0/devicecode`` and
``{auth_base_url}/oauth2/v2.0/token`` (form-encoded POSTs, public client, no
secret). The scope asked for is ``<cfg.scope> offline_access openid``.

``<data>/auth/token.json`` (directory 0700, file 0600) holds ``access_token``,
``refresh_token`` and ``expires_at`` (epoch seconds). ``TokenCache`` reads the
file on every access: ``login`` writes it from another process while the
forwarder runs. ``get_access_token`` refreshes when the access token has 300 s
or less left.

No request follows a redirect, so a bearer token never reaches another host.
Log lines carry error words, status codes and exception class names only:
never a token, a device code, a user code or a URL.
"""
from __future__ import annotations

import http.client
import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable, Dict, NamedTuple, Optional, Tuple

from . import log, paths
from .config import Config

AUTH_DIR = "auth"
TOKEN_FILE = "token.json"
NOTICE_FILE = "notice-login-at"
NOTICE_EVERY_S = 86_400
REFRESH_MARGIN_S = 300
SLOW_DOWN_S = 5
AUTH_TIMEOUT_S = 30.0
MAX_REPLY_BYTES = 1_048_576
DEVICE_CODE_GRANT = "urn:ietf:params:oauth:grant-type:device_code"
# Refresh answers that mean the refresh token is no longer any use.
_DEAD_REFRESH = frozenset(("invalid_grant", "interaction_required", "consent_required", "login_required"))
_WORD_RE = re.compile(r"[a-z0-9_]{1,64}")

# No answer at all: URLError, socket timeouts and resets are OSError; a broken reply is HTTPException.
TRANSPORT_ERRORS = (OSError, http.client.HTTPException)


class AuthError(Exception):
    """Sign-in could not start; ``word`` is the error word or the exception class name."""

    def __init__(self, word: str) -> None:
        super().__init__(word)
        self.word = word


class DeviceFlow(NamedTuple):
    user_code: str
    verification_uri: str
    message: str
    device_code: str
    interval: int
    expires_at: float


def error_word(body: Any) -> str:
    """The reply's ``error`` value when it is a plain lower-case word, else ``other``."""
    value = body.get("error") if isinstance(body, dict) else None
    return value if isinstance(value, str) and _WORD_RE.fullmatch(value) else "other"


def scope(cfg: Config) -> str:
    return "{} offline_access openid".format(cfg.scope)


def _endpoint(cfg: Config, name: str) -> str:
    return cfg.auth_base_url.rstrip("/") + "/oauth2/v2.0/" + name


# ---------------------------------------------------------------------- HTTP


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401 - urllib hook
        return None  # the 3xx then surfaces as an HTTPError with its own status


_OPENER = urllib.request.build_opener(_NoRedirect)


def _parse(raw: bytes) -> Any:
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError):
        return None


def http_call(method: str, url: str, body: Optional[bytes] = None, headers: Optional[Dict[str, str]] = None,
              timeout: float = AUTH_TIMEOUT_S) -> Tuple[int, Any]:
    """``(status, parsed JSON reply or None)``; raises a ``TRANSPORT_ERRORS`` member when nothing answers."""
    request = urllib.request.Request(url, data=body, headers=headers or {}, method=method)
    try:
        response = _OPENER.open(request, timeout=timeout)
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, _parse(exc.read(MAX_REPLY_BYTES))
        finally:
            exc.close()
    with response:
        return response.status, _parse(response.read(MAX_REPLY_BYTES))


def _form_post(url: str, fields: Dict[str, str]) -> Tuple[int, Any]:
    body = urllib.parse.urlencode(fields).encode("ascii")
    headers = {"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"}
    return http_call("POST", url, body, headers, timeout=AUTH_TIMEOUT_S)


# ---------------------------------------------------------------------- files


def write_private(path: Path, text: str) -> None:
    """Write ``text`` to ``path`` with mode 0600, by temp file and ``os.replace``."""
    path = Path(path)
    tmp = path.with_name("%s.%d.%d.tmp" % (path.name, os.getpid(), threading.get_ident()))
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.chmod(str(tmp), 0o600)
        os.replace(str(tmp), str(path))
    except BaseException:
        try:
            os.remove(str(tmp))
        except FileNotFoundError:
            pass
        raise


class TokenCache:
    """``<data>/auth/token.json``, read from disk on every access."""

    def __init__(self, data_dir: Path) -> None:
        self._data_dir = Path(data_dir)
        self._lock = threading.RLock()

    @property
    def data_dir(self) -> Path:
        return self._data_dir

    @property
    def path(self) -> Path:
        return self._data_dir / AUTH_DIR / TOKEN_FILE

    def load(self) -> Dict[str, Any]:
        """``{access_token, refresh_token, expires_at}`` (missing tokens are None); ``{}`` when absent."""
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, ValueError):
            return {}
        if not isinstance(data, dict):
            return {}

        def text(key: str) -> Optional[str]:
            value = data.get(key)
            return value if isinstance(value, str) and value else None

        expires_at = data.get("expires_at")
        if not isinstance(expires_at, (int, float)) or isinstance(expires_at, bool):
            expires_at = 0
        return {"access_token": text("access_token"), "refresh_token": text("refresh_token"),
                "expires_at": expires_at}

    def save(self, access_token: Optional[str], refresh_token: Optional[str], expires_at: float) -> None:
        directory = self.path.parent
        with self._lock:
            directory.mkdir(mode=0o700, parents=True, exist_ok=True)
            os.chmod(str(directory), 0o700)
            body = {"access_token": access_token, "refresh_token": refresh_token, "expires_at": expires_at}
            write_private(self.path, json.dumps(body))

    def signed_in(self) -> bool:
        """True while a refresh token is cached."""
        return self.load().get("refresh_token") is not None

    def drop_access_token(self, sent: str) -> bool:
        """Forget the access token if it is still ``sent``; False when the cache has moved on."""
        with self._lock:
            data = self.load()
            if not data or data["access_token"] is None or data["access_token"] != sent:
                return False
            self.save(None, data["refresh_token"], 0)
        return True

    def drop_refresh_token(self, sent: str) -> bool:
        """Forget every token if the refresh token is still ``sent`` (the developer must sign in again)."""
        with self._lock:
            if self.load().get("refresh_token") != sent:
                return False
            self.clear()
        return True

    def clear(self) -> None:
        with self._lock:
            try:
                os.remove(str(self.path))
            except FileNotFoundError:
                pass


def _store(cache: TokenCache, body: Any, now: float, keep_refresh: Optional[str] = None) -> Optional[str]:
    """Cache a 200 token answer; returns the access token, or None for a reply without one."""
    if not isinstance(body, dict):
        return None
    access = body.get("access_token")
    expires_in = body.get("expires_in")
    if isinstance(expires_in, str) and expires_in.isdigit():
        expires_in = int(expires_in)
    if not isinstance(access, str) or not access or not isinstance(expires_in, (int, float)) \
            or isinstance(expires_in, bool):
        return None
    refresh = body.get("refresh_token")
    if not isinstance(refresh, str) or not refresh:
        refresh = keep_refresh
    cache.save(access, refresh, now + expires_in)
    return access


# ---------------------------------------------------------------------- device code


def start_device_flow(cfg: Config, *, clock: Callable[[], float] = time.time) -> DeviceFlow:
    """Ask for a device code; raises ``AuthError`` when the identity platform says no."""
    try:
        status, body = _form_post(_endpoint(cfg, "devicecode"), {"client_id": cfg.client_id, "scope": scope(cfg)})
    except TRANSPORT_ERRORS as exc:
        raise AuthError(type(exc).__name__) from None
    if status != 200:
        raise AuthError(error_word(body))
    if not isinstance(body, dict):
        raise AuthError("bad_reply")
    fields = [body.get(k) for k in ("user_code", "verification_uri", "device_code")]
    expires_in, interval = body.get("expires_in"), body.get("interval", 5)
    if not all(isinstance(v, str) and v for v in fields) or not isinstance(expires_in, int) \
            or not isinstance(interval, int):
        raise AuthError("bad_reply")
    user_code, verification_uri, device_code = fields
    message = body.get("message")
    if not isinstance(message, str) or not message:
        message = "To sign in, open {} and enter the code {}.".format(verification_uri, user_code)
    return DeviceFlow(user_code, verification_uri, message, device_code, max(1, interval), clock() + expires_in)


def poll_device_flow(cfg: Config, flow: DeviceFlow, cache: Optional[TokenCache] = None, *,
                     sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.time) -> bool:
    """Poll the token endpoint until the developer signs in (True) or the code is refused or expires (False)."""
    cache = cache if cache is not None else TokenCache(paths.data_dir())
    logger = log.get_logger(cache.data_dir)
    fields = {"grant_type": DEVICE_CODE_GRANT, "client_id": cfg.client_id, "device_code": flow.device_code}
    interval = flow.interval
    while clock() < flow.expires_at:
        sleep(interval)
        if clock() >= flow.expires_at:
            break
        try:
            status, body = _form_post(_endpoint(cfg, "token"), fields)
        except TRANSPORT_ERRORS as exc:
            logger.warning("sign-in poll got no answer (%s); still waiting", type(exc).__name__)
            continue
        if status == 200:
            if _store(cache, body, clock()) is not None:
                logger.info("sign-in complete")
                return True
            logger.warning("sign-in failed: the token answer had no usable token")
            return False
        word = error_word(body)
        if word == "authorization_pending":
            continue
        if word == "slow_down":
            interval += SLOW_DOWN_S
            continue
        if status >= 500:
            continue
        logger.warning("sign-in failed: %d %s", status, word)
        return False
    logger.warning("sign-in failed: the code expired")
    return False


# ---------------------------------------------------------------------- access token


def get_access_token(cfg: Config, cache: TokenCache, now: Optional[float] = None) -> Optional[str]:
    """A usable access token, refreshed when 300 s or less are left; None when signed out."""
    now = time.time() if now is None else now
    data = cache.load()
    access, refresh, expires_at = data.get("access_token"), data.get("refresh_token"), data.get("expires_at", 0)
    if access is not None and expires_at - now > REFRESH_MARGIN_S:
        return access
    still_valid = access if access is not None and expires_at > now else None
    if refresh is None or not cfg.auth_base_url or not cfg.client_id:
        return still_valid
    logger = log.get_logger(cache.data_dir)
    fields = {"grant_type": "refresh_token", "client_id": cfg.client_id, "refresh_token": refresh,
              "scope": scope(cfg)}
    try:
        status, body = _form_post(_endpoint(cfg, "token"), fields)
    except TRANSPORT_ERRORS as exc:
        logger.warning("token refresh got no answer (%s)", type(exc).__name__)
        return still_valid
    if status == 200:
        fresh = _store(cache, body, now, keep_refresh=refresh)
        if fresh is None:
            logger.warning("token refresh failed: the answer had no usable token")
            return still_valid
        return fresh
    word = error_word(body)
    if status in (400, 401) and word in _DEAD_REFRESH:
        cache.drop_refresh_token(refresh)
        logger.warning("token refresh refused (%s); sign in again", word)
        return None
    logger.warning("token refresh failed: %d %s", status, word)
    return still_valid


def login_notice_due(data_dir: Path, now: Optional[float] = None) -> bool:
    """True at most once per 86,400 s while signed out; records the time in ``<data>/notice-login-at``."""
    now = time.time() if now is None else now
    if TokenCache(data_dir).signed_in():
        return False
    path = Path(data_dir) / NOTICE_FILE
    try:
        last: Optional[float] = float(path.read_text(encoding="utf-8").strip())
    except (OSError, UnicodeDecodeError, ValueError):
        last = None
    if last is not None and 0 <= now - last < NOTICE_EVERY_S:
        return False
    try:
        write_private(path, "{}\n".format(now))
    except OSError:
        pass
    return True
