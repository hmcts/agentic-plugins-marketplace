import json
import stat

import pytest

from cpp_telemetry import auth
from cpp_telemetry.config import Config
from tests.fakes import (DEVICECODE_PATH, TOKEN_PATH, closed_port, fake_auth,  # noqa: F401 - fixtures
                         make_token, oauth_error, token_reply)

TENANT = "00000000-0000-0000-0000-000000000001"
CLIENT = "00000000-0000-0000-0000-000000000002"
API_APP = "00000000-0000-0000-0000-000000000003"
NOW = 1_800_000_000.0


def _cfg(auth_url):
    return Config(ingest_url="http://127.0.0.1:18080", tenant_id=TENANT, client_id=CLIENT,
                  api_app_id=API_APP, auth_base_url=auth_url)


def _mode(path):
    return stat.S_IMODE(path.stat().st_mode)


class Clock:
    def __init__(self, now=NOW):
        self.now = now
        self.sleeps = []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


def _device_reply(interval=5, expires_in=900):
    return 200, {
        "device_code": make_token("dev"),
        "user_code": "ABCD-EFGH",
        "verification_uri": "https://example.invalid/devicelogin",
        "expires_in": expires_in,
        "interval": interval,
        "message": "Open https://example.invalid/devicelogin and enter ABCD-EFGH.",
    }


def test_device_flow_posts_form_and_returns_user_code(fake_auth):
    fake_auth.script(DEVICECODE_PATH, _device_reply())
    flow = auth.start_device_flow(_cfg(fake_auth.url), clock=lambda: NOW)
    assert flow.user_code == "ABCD-EFGH"
    assert flow.verification_uri == "https://example.invalid/devicelogin"
    assert flow.message.startswith("Open ")
    assert flow.interval == 5
    assert flow.expires_at == NOW + 900
    (call,) = fake_auth.calls(DEVICECODE_PATH)
    assert call.method == "POST"
    assert call.headers["Content-Type"] == "application/x-www-form-urlencoded"
    assert call.form() == {"client_id": CLIENT,
                           "scope": "api://{}/.default offline_access openid".format(API_APP)}


def test_device_flow_error_raises_auth_error_with_the_word(fake_auth):
    fake_auth.script(DEVICECODE_PATH, oauth_error("invalid_client"))
    with pytest.raises(auth.AuthError) as info:
        auth.start_device_flow(_cfg(fake_auth.url))
    assert info.value.word == "invalid_client"


def test_poll_pending_then_token_cached_0600(fake_auth, data_dir):
    access, refresh = make_token("acc"), make_token("ref")
    fake_auth.script(DEVICECODE_PATH, _device_reply(interval=2))
    fake_auth.script(TOKEN_PATH, oauth_error("authorization_pending"), oauth_error("slow_down"),
                     token_reply(access, refresh, expires_in=3600))
    clock = Clock()
    cfg = _cfg(fake_auth.url)
    flow = auth.start_device_flow(cfg, clock=clock)
    cache = auth.TokenCache(data_dir)
    assert auth.poll_device_flow(cfg, flow, cache=cache, sleep=clock.sleep, clock=clock) is True
    assert clock.sleeps == [2, 2, 7]  # slow_down adds 5 s
    calls = fake_auth.calls(TOKEN_PATH)
    assert len(calls) == 3
    assert calls[0].form() == {"grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                               "client_id": CLIENT, "device_code": flow.device_code}
    path = data_dir / "auth" / "token.json"
    assert _mode(path.parent) == 0o700 and _mode(path) == 0o600
    stored = json.loads(path.read_text())
    assert stored == {"access_token": access, "refresh_token": refresh, "expires_at": clock.now + 3600}
    log_file = data_dir / "forwarder.log"
    text = log_file.read_text() if log_file.exists() else ""
    assert access not in text and refresh not in text and flow.device_code not in text


def test_poll_expired_token_returns_false_and_caches_nothing(fake_auth, data_dir):
    fake_auth.script(DEVICECODE_PATH, _device_reply(interval=1))
    fake_auth.script(TOKEN_PATH, oauth_error("authorization_pending"), oauth_error("expired_token"))
    clock = Clock()
    cfg = _cfg(fake_auth.url)
    flow = auth.start_device_flow(cfg, clock=clock)
    cache = auth.TokenCache(data_dir)
    assert auth.poll_device_flow(cfg, flow, cache=cache, sleep=clock.sleep, clock=clock) is False
    assert not (data_dir / "auth" / "token.json").exists()


def test_poll_stops_at_the_flow_deadline(fake_auth, data_dir):
    fake_auth.script(DEVICECODE_PATH, _device_reply(interval=5, expires_in=12))
    fake_auth.default(TOKEN_PATH, oauth_error("authorization_pending"))
    clock = Clock()
    cfg = _cfg(fake_auth.url)
    flow = auth.start_device_flow(cfg, clock=clock)
    assert auth.poll_device_flow(cfg, flow, cache=auth.TokenCache(data_dir), sleep=clock.sleep, clock=clock) is False
    assert len(fake_auth.calls(TOKEN_PATH)) <= 3


def test_refresh_when_near_expiry(fake_auth, data_dir):
    cfg = _cfg(fake_auth.url)
    cache = auth.TokenCache(data_dir)
    old_access, old_refresh = make_token("old"), make_token("ref")
    new_access, new_refresh = make_token("new"), make_token("nrf")

    cache.save(old_access, old_refresh, NOW + 301)
    assert auth.get_access_token(cfg, cache, now=NOW) == old_access
    assert fake_auth.calls(TOKEN_PATH) == []

    fake_auth.script(TOKEN_PATH, token_reply(new_access, new_refresh, expires_in=3600))
    assert auth.get_access_token(cfg, cache, now=NOW + 2) == new_access  # 299 s left: refresh
    (call,) = fake_auth.calls(TOKEN_PATH)
    assert call.form() == {"grant_type": "refresh_token", "client_id": CLIENT, "refresh_token": old_refresh,
                           "scope": "api://{}/.default offline_access openid".format(API_APP)}
    assert cache.load() == {"access_token": new_access, "refresh_token": new_refresh, "expires_at": NOW + 2 + 3600}


def test_no_refresh_token_means_no_access_token(fake_auth, data_dir):
    cfg = _cfg(fake_auth.url)
    cache = auth.TokenCache(data_dir)
    assert auth.get_access_token(cfg, cache, now=NOW) is None
    cache.save(make_token("acc"), None, NOW - 10)
    assert auth.get_access_token(cfg, cache, now=NOW) is None
    assert fake_auth.requests == []


def test_refused_refresh_drops_the_refresh_token(fake_auth, data_dir):
    cfg = _cfg(fake_auth.url)
    cache = auth.TokenCache(data_dir)
    cache.save(make_token("acc"), make_token("ref"), NOW - 10)
    fake_auth.script(TOKEN_PATH, oauth_error("invalid_grant"))
    assert auth.get_access_token(cfg, cache, now=NOW) is None
    assert cache.load().get("refresh_token") is None


def test_refresh_unreachable_keeps_a_still_valid_access_token(data_dir):
    cfg = _cfg("http://127.0.0.1:%d" % closed_port())
    cache = auth.TokenCache(data_dir)
    access, refresh = make_token("acc"), make_token("ref")
    cache.save(access, refresh, NOW + 100)
    assert auth.get_access_token(cfg, cache, now=NOW) == access
    cache.save(access, refresh, NOW - 1)
    assert auth.get_access_token(cfg, cache, now=NOW) is None
    assert cache.load()["refresh_token"] == refresh


def test_login_notice_once_a_day(data_dir):
    assert auth.login_notice_due(data_dir, now=NOW) is True
    assert (data_dir / "notice-login-at").exists()
    assert auth.login_notice_due(data_dir, now=NOW + 60) is False
    assert auth.login_notice_due(data_dir, now=NOW + 86_399) is False
    assert auth.login_notice_due(data_dir, now=NOW + 86_400) is True
    assert auth.login_notice_due(data_dir, now=NOW + 86_401) is False


def test_login_notice_not_due_when_signed_in(data_dir):
    auth.TokenCache(data_dir).save(make_token("acc"), make_token("ref"), NOW + 3600)
    assert auth.login_notice_due(data_dir, now=NOW) is False
    assert not (data_dir / "notice-login-at").exists()


def test_cache_drop_access_keeps_refresh_and_clear_removes_file(data_dir):
    cache = auth.TokenCache(data_dir)
    access, refresh = make_token("acc"), make_token("ref")
    cache.save(access, refresh, NOW + 3600)
    assert cache.drop_access_token(access) is True
    assert cache.load() == {"access_token": None, "refresh_token": refresh, "expires_at": 0}
    assert cache.drop_access_token(make_token("zzz")) is False  # only the token that was sent
    cache.clear()
    assert cache.load() == {}
    assert not (data_dir / "auth" / "token.json").exists()
