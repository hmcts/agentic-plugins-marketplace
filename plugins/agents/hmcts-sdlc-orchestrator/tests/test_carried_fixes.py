"""Carried fixes from the Task 6 review: unlisted 4xx, https endpoints, token-file durability, 429 on sign-in."""
import json
import os
import stat
import subprocess
import sys
import time

import pytest

from cpp_telemetry import auth, config, log, uploader
from cpp_telemetry.config import Config
from cpp_telemetry.receiver import ForwarderState
from cpp_telemetry.spool import Spool
from tests.fakes import (BATCHES_PATH, DEVICECODE_PATH, TOKEN_PATH, closed_port, fake_auth,  # noqa: F401 - fixtures
                         fake_ingest, make_token, token_reply)

TENANT = "00000000-0000-0000-0000-000000000001"
CLIENT = "00000000-0000-0000-0000-000000000002"
API_APP = "00000000-0000-0000-0000-000000000003"
CONFIGURED = {"ingest_url": "http://127.0.0.1:18080", "tenant_id": TENANT, "client_id": CLIENT, "api_app_id": API_APP}
NOW = 1_800_000_000.0


class Clock:
    def __init__(self, now=NOW):
        self.now = now
        self.sleeps = []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


# ---------------------------------------------------------------- uploader


def _uploader(data_dir, ingest_url):
    cfg = Config(ingest_url=ingest_url, tenant_id=TENANT, client_id=CLIENT, api_app_id=API_APP,
                 auth_base_url="http://127.0.0.1:%d" % closed_port())
    clock = Clock()
    sp = Spool(data_dir, cfg, clock=clock)
    cache = auth.TokenCache(data_dir)
    cache.save(make_token("acc"), make_token("ref"), NOW + 3600)
    state = ForwarderState()
    return uploader.Uploader(cfg, sp, cache, state, log.get_logger(data_dir)), sp, state, clock


def _batch(sp, clock):
    clock.now += 1
    sp.append("sess-a", {"signal": "event", "payload": {"name": "x"}})
    (path,) = sp.close_all()
    return path


def _open_gaps(sp):
    gaps = []
    for path in sp.root.glob("*/*.open.jsonl"):
        for line in path.read_text().splitlines():
            record = json.loads(line)
            if record["payload"].get("name") == "gap":
                gaps.append(record["payload"])
    return gaps


@pytest.mark.parametrize("status", [404, 405, 410, 422])
def test_unlisted_4xx_drops_the_batch_with_a_rejected_code_gap(fake_ingest, data_dir, status):
    fake_ingest.default(BATCHES_PATH, (status, {"error": "nope"}))
    up, sp, state, clock = _uploader(data_dir, fake_ingest.url)
    path = _batch(sp, clock)
    up.tick(NOW + 5)
    assert not path.exists()
    (gap,) = _open_gaps(sp)
    assert gap["reason"] == "rejected_%d" % status
    assert up.backoff_s == 0  # dropped, not retried for ever


@pytest.mark.parametrize("status", [403, 429, 500, 302])
def test_listed_or_non_4xx_statuses_still_back_off(fake_ingest, data_dir, status):
    fake_ingest.default(BATCHES_PATH, (status, {"error": "busy"}))
    up, sp, state, clock = _uploader(data_dir, fake_ingest.url)
    path = _batch(sp, clock)
    up.tick(NOW + 5)
    assert path.exists() and up.backoff_s == 5 and state.last_error == "http_%d" % status


def test_an_ack_is_recorded_in_the_last_ack_file(fake_ingest, data_dir):
    fake_ingest.default(BATCHES_PATH, (200, {"accepted": []}))
    up, sp, state, clock = _uploader(data_dir, fake_ingest.url)
    path = data_dir / uploader.LAST_ACK_FILE
    up.tick(NOW + 5)  # nothing to send: no ack, no file
    assert not path.exists()
    _batch(sp, clock)
    up.tick(NOW + 7)
    assert float(path.read_text()) == NOW + 7 == state.last_ack
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


# ---------------------------------------------------------------- config


@pytest.mark.parametrize("key", ["ingest_url", "auth_base_url"])
@pytest.mark.parametrize("value", ["http://example.invalid", "ftp://example.invalid/x", "example.invalid",
                                   "http://127.0.0.1.example.invalid", "http://[::1"])
def test_insecure_endpoint_override_is_ignored_and_keeps_the_plugin_dormant(tmp_path, key, value):
    (tmp_path / "override.json").write_text(json.dumps(dict(CONFIGURED, **{key: value})))
    cfg = config.load(tmp_path)
    assert getattr(cfg, key) != value
    assert not cfg.is_configured()
    lines = (tmp_path / "forwarder.log").read_text().splitlines()
    assert len(lines) == 1 and key in lines[0] and "example" not in lines[0]


@pytest.mark.parametrize("value", ["https://example.invalid", "http://127.0.0.1:18081", "http://localhost:18081",
                                   "https://localhost"])
def test_https_or_loopback_endpoints_are_accepted(tmp_path, value):
    (tmp_path / "override.json").write_text(json.dumps(dict(CONFIGURED, ingest_url=value, auth_base_url=value)))
    cfg = config.load(tmp_path)
    assert cfg.ingest_url == value == cfg.auth_base_url and cfg.is_configured()
    assert not (tmp_path / "forwarder.log").exists()


def test_direct_config_with_a_plain_http_remote_endpoint_is_not_configured():
    assert Config(**CONFIGURED).is_configured()
    assert not Config(**dict(CONFIGURED, ingest_url="http://example.invalid")).is_configured()
    assert not Config(**dict(CONFIGURED, auth_base_url="http://example.invalid")).is_configured()


# ---------------------------------------------------------------- auth


def test_write_private_fsyncs_before_replace(tmp_path, monkeypatch):
    order = []
    real_fsync, real_replace = os.fsync, os.replace

    def fsync(fd):
        order.append("fsync")
        real_fsync(fd)

    def replace(src, dst):
        order.append("replace")
        real_replace(src, dst)

    monkeypatch.setattr(auth.os, "fsync", fsync)
    monkeypatch.setattr(auth.os, "replace", replace)
    auth.write_private(tmp_path / "f.json", "{}")
    assert order == ["fsync", "replace"] and (tmp_path / "f.json").read_text() == "{}"


def _dead_pid():
    proc = subprocess.Popen([sys.executable, "-B", "-c", "pass"])
    proc.wait()
    return proc.pid


def test_token_cache_init_removes_only_stale_tmp_files(data_dir):
    auth_dir = data_dir / "auth"
    auth_dir.mkdir(mode=0o700)
    dead = auth_dir / ("token.json.%d.1.tmp" % _dead_pid())
    live_fresh = auth_dir / ("token.json.%d.2.tmp" % os.getpid())
    live_old = auth_dir / ("token.json.%d.3.tmp" % os.getpid())
    odd = auth_dir / "token.json.x.tmp"
    keep = auth_dir / "token.json"
    for path in (dead, live_fresh, live_old, odd, keep):
        path.write_text("{}")
    old = time.time() - auth.STALE_TMP_S - 60
    os.utime(str(live_old), (old, old))
    auth.TokenCache(data_dir)
    assert sorted(p.name for p in auth_dir.iterdir()) == sorted([live_fresh.name, keep.name])


def test_token_cache_init_never_creates_the_auth_dir(data_dir):
    auth.TokenCache(data_dir)
    assert not (data_dir / "auth").exists()


def test_poll_429_from_the_token_endpoint_slows_down(fake_auth, data_dir):
    access, refresh = make_token("acc"), make_token("ref")
    fake_auth.script(DEVICECODE_PATH, (200, {
        "device_code": make_token("dev"), "user_code": "ABCD-EFGH",
        "verification_uri": "https://example.invalid/devicelogin", "expires_in": 900, "interval": 2}))
    fake_auth.script(TOKEN_PATH, (429, {}), token_reply(access, refresh, expires_in=3600))
    clock = Clock()
    cfg = Config(ingest_url="http://127.0.0.1:18080", tenant_id=TENANT, client_id=CLIENT, api_app_id=API_APP,
                 auth_base_url=fake_auth.url)
    flow = auth.start_device_flow(cfg, clock=clock)
    assert auth.poll_device_flow(cfg, flow, cache=auth.TokenCache(data_dir), sleep=clock.sleep, clock=clock) is True
    assert clock.sleeps == [2, 7]  # the 429 adds 5 s, like slow_down
