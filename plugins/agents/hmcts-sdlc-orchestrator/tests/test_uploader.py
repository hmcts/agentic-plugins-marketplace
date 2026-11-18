import gzip
import json

from cpp_telemetry import auth, forwarder, log, uploader
from cpp_telemetry.config import Config
from cpp_telemetry.receiver import ForwarderState
from cpp_telemetry.spool import Spool
from tests.fakes import (BATCHES_PATH, ME_PATH, TOKEN_PATH, closed_port, fake_auth,  # noqa: F401 - fixtures
                         fake_ingest, make_token, token_reply)

TENANT = "00000000-0000-0000-0000-000000000001"
CLIENT = "00000000-0000-0000-0000-000000000002"
API_APP = "00000000-0000-0000-0000-000000000003"
NOW = 1_800_000_000.0
DAY = 86_400


class Clock:
    def __init__(self, now=NOW):
        self.now = now

    def __call__(self):
        return self.now


def _cfg(ingest_url, auth_url=None, **extra):
    return Config(ingest_url=ingest_url, tenant_id=TENANT, client_id=CLIENT, api_app_id=API_APP,
                  auth_base_url=auth_url or "http://127.0.0.1:%d" % closed_port(), **extra)


def _setup(data_dir, cfg, signed_in=True, state=None):
    clock = Clock()
    sp = Spool(data_dir, cfg, clock=clock)
    cache = auth.TokenCache(data_dir)
    access = make_token("acc")
    if signed_in:
        cache.save(access, make_token("ref"), NOW + 3600)
    state = state or ForwarderState()
    up = uploader.Uploader(cfg, sp, cache, state, log.get_logger(data_dir))
    return up, sp, cache, state, clock, access


def _batch(sp, clock, session="sess-a", name="x", advance=1.0, payload=None):
    clock.now += advance
    sp.append(session, {"signal": "event", "payload": payload or {"name": name}})
    (path,) = sp.close_all()
    return path


def _sent(call):
    return json.loads(gzip.decompress(call.body).decode("utf-8"))


def _open_gaps(sp):
    gaps = []
    for path in sp.root.glob("*/*.open.jsonl"):
        for line in path.read_text().splitlines():
            record = json.loads(line)
            if record["payload"].get("name") == "gap":
                gaps.append(record["payload"])
    return gaps


def _log(data_dir):
    path = data_dir / "forwarder.log"
    return path.read_text() if path.exists() else ""


def test_upload_ok_deletes_batch(fake_ingest, data_dir):
    up, sp, _, state, clock, access = _setup(data_dir, _cfg(fake_ingest.url))
    path = _batch(sp, clock)
    raw = path.read_bytes()
    up.tick(NOW + 5)
    (call,) = fake_ingest.calls(BATCHES_PATH)
    assert call.method == "POST"
    assert call.headers["Authorization"] == "Bearer " + access
    assert call.headers["Content-Type"] == "application/json"
    assert call.headers["Content-Encoding"] == "gzip"
    assert call.body == raw
    assert _sent(call)["session_id"] == "sess-a"
    assert sp.closed_batches_oldest_first() == []
    assert state.last_ack == NOW + 5 and state.last_error is None
    assert access not in _log(data_dir)


def test_401_drops_access_token(fake_ingest, fake_auth, data_dir):
    fake_ingest.default(BATCHES_PATH, (401, {"error": "unauthorized"}))
    fake_auth.default(TOKEN_PATH, token_reply(make_token("new"), make_token("nrf")))
    up, sp, cache, state, clock, access = _setup(data_dir, _cfg(fake_ingest.url, fake_auth.url))
    path = _batch(sp, clock)

    up.tick(NOW + 5)
    assert cache.load()["access_token"] is None
    assert cache.load()["refresh_token"] == make_token("ref")
    assert path.exists()
    assert fake_auth.calls(TOKEN_PATH) == []

    up.tick(NOW + 10)  # refreshed, refused again: 2 in a row
    up.tick(NOW + 15)  # 3 in a row: the refresh token goes too
    assert len(fake_auth.calls(TOKEN_PATH)) == 2
    assert len(fake_ingest.calls(BATCHES_PATH)) == 3
    assert cache.load().get("refresh_token") is None

    up.tick(NOW + 20)  # signed out: nothing is sent
    assert len(fake_ingest.calls(BATCHES_PATH)) == 3
    assert path.exists()
    text = _log(data_dir)
    for secret in (access, make_token("ref"), make_token("new"), make_token("nrf"), "Bearer"):
        assert secret not in text


def test_200_resets_the_401_count(fake_ingest, fake_auth, data_dir):
    fake_ingest.script(BATCHES_PATH, (401, {"error": "unauthorized"}), (401, {"error": "unauthorized"}),
                       (200, {"accepted": []}), (401, {"error": "unauthorized"}))
    fake_auth.default(TOKEN_PATH, token_reply())
    up, sp, cache, _, clock, _ = _setup(data_dir, _cfg(fake_ingest.url, fake_auth.url))
    _batch(sp, clock)
    up.tick(NOW + 5)
    up.tick(NOW + 10)
    up.tick(NOW + 15)  # 200
    _batch(sp, clock, advance=20)
    up.tick(NOW + 40)  # one 401 after the success
    assert cache.load()["refresh_token"] is not None


def test_403_not_on_roster_deletes_spool_and_sets_rejected_until(fake_ingest, data_dir):
    fake_ingest.default(BATCHES_PATH, (403, {"error": "not_on_roster"}))
    up, sp, _, state, clock, _ = _setup(data_dir, _cfg(fake_ingest.url))
    _batch(sp, clock, session="sess-a")
    _batch(sp, clock, session="sess-b")
    sp.append("sess-c", {"signal": "event", "payload": {"name": "open"}})
    now = NOW + 5
    up.tick(now)
    assert len(fake_ingest.calls(BATCHES_PATH)) == 1
    assert sp.is_empty()
    assert list(sp.root.glob("*/manifest.json")) == []
    assert float((data_dir / "rejected-until").read_text()) == now + DAY
    assert forwarder._read_rejected_until(data_dir) == now + DAY
    assert state.rejected_until == now + DAY

    _batch(sp, clock, session="sess-d", advance=10)  # still refused: nothing is uploaded
    up.tick(now + 60)
    assert len(fake_ingest.calls(BATCHES_PATH)) == 1


def test_403_with_another_word_keeps_the_spool_and_backs_off(fake_ingest, data_dir):
    fake_ingest.default(BATCHES_PATH, (403, {"error": "forbidden"}))
    up, sp, _, state, clock, _ = _setup(data_dir, _cfg(fake_ingest.url))
    path = _batch(sp, clock)
    up.tick(NOW + 5)
    assert path.exists() and state.rejected_until == 0.0
    assert state.last_error == "http_403"
    assert not (data_dir / "rejected-until").exists()


def test_409_resequences_and_resends(fake_ingest, data_dir):
    fake_ingest.script(BATCHES_PATH, (409, {"error": "sha_conflict"}), (200, {"accepted": []}))
    up, sp, _, state, clock, _ = _setup(data_dir, _cfg(fake_ingest.url))
    _batch(sp, clock)
    up.tick(NOW + 5)
    first, second = fake_ingest.calls(BATCHES_PATH)
    assert _sent(second)["batch_seq"] > _sent(first)["batch_seq"]
    assert _sent(second)["events"] == _sent(first)["events"]
    assert sp.closed_batches_oldest_first() == []
    assert state.last_ack == NOW + 5


def test_409_sha_conflict_forever_is_bounded(fake_ingest, data_dir):
    fake_ingest.default(BATCHES_PATH, (409, {"error": "sha_conflict"}))
    up, sp, _, _, clock, _ = _setup(data_dir, _cfg(fake_ingest.url))
    _batch(sp, clock)
    up.tick(NOW + 5)
    assert 1 < len(fake_ingest.calls(BATCHES_PATH)) <= uploader.MAX_RESEQUENCE + 1
    assert len(sp.closed_batches_oldest_first()) == 1


def test_409_other_error_drops_with_gap_and_gap_only_batch_is_not_regapped(fake_ingest, data_dir):
    fake_ingest.default(BATCHES_PATH, (409, {"error": "session_not_owned"}))
    up, sp, _, _, clock, _ = _setup(data_dir, _cfg(fake_ingest.url))
    path = _batch(sp, clock)
    up.tick(NOW + 5)
    assert not path.exists()
    (gap,) = _open_gaps(sp)
    assert gap["reason"] == "rejected_409"
    assert "session_not_owned" in _log(data_dir)

    up.tick(NOW + 60)  # the gap batch closes, is refused again and is deleted without a new gap
    assert len(fake_ingest.calls(BATCHES_PATH)) == 2
    assert sp.is_empty()
    up.tick(NOW + 120)
    assert len(fake_ingest.calls(BATCHES_PATH)) == 2


def test_5xx_backs_off_and_keeps_batch(fake_ingest, data_dir):
    fake_ingest.default(BATCHES_PATH, (503, {"error": "store_unavailable"}))
    up, sp, _, state, clock, _ = _setup(data_dir, _cfg(fake_ingest.url))
    path = _batch(sp, clock)
    t = NOW + 5
    up.tick(t)
    assert len(fake_ingest.calls(BATCHES_PATH)) == 1
    assert path.exists() and state.last_error == "http_503"
    up.tick(t + 4.9)
    assert len(fake_ingest.calls(BATCHES_PATH)) == 1
    up.tick(t + 5)  # back-off was 5 s, now 10 s
    assert len(fake_ingest.calls(BATCHES_PATH)) == 2
    up.tick(t + 14.9)
    assert len(fake_ingest.calls(BATCHES_PATH)) == 2
    up.tick(t + 15)
    assert len(fake_ingest.calls(BATCHES_PATH)) == 3
    for _ in range(10):  # doubling stops at 300 s
        up.tick(up.next_attempt_at)
    assert up.backoff_s == 300
    fake_ingest.default(BATCHES_PATH, (200, {"accepted": []}))
    up.tick(up.next_attempt_at)
    assert not path.exists() and state.last_error is None and up.backoff_s == 0


def test_429_and_unreachable_ingest_back_off(fake_ingest, data_dir):
    fake_ingest.script(BATCHES_PATH, (429, {"error": "rate_limited"}))
    up, sp, _, state, clock, _ = _setup(data_dir, _cfg(fake_ingest.url))
    path = _batch(sp, clock)
    up.tick(NOW + 5)
    assert state.last_error == "http_429" and path.exists()

    up2, sp2, _, state2, clock2, _ = _setup(data_dir, _cfg("http://127.0.0.1:%d" % closed_port()))
    up2.tick(NOW + 5)
    assert state2.last_error == "URLError" and path.exists()
    assert up2.backoff_s == 5


def test_413_deletes_batch_and_writes_gap(fake_ingest, data_dir):
    fake_ingest.default(BATCHES_PATH, (413, {"error": "too_large"}))
    up, sp, _, _, clock, _ = _setup(data_dir, _cfg(fake_ingest.url))
    path = _batch(sp, clock)
    seq = int(path.name.split(".")[0])
    up.tick(NOW + 5)
    assert not path.exists()
    (gap,) = _open_gaps(sp)
    assert gap["reason"] == "too_large" and gap["batch_seq"] == seq and gap["session_id"] == "sess-a"


def test_400_deletes_poison_batch_and_writes_gap(fake_ingest, data_dir):
    fake_ingest.default(BATCHES_PATH, (400, {"error": "bad_batch"}))
    up, sp, _, _, clock, _ = _setup(data_dir, _cfg(fake_ingest.url))
    path = _batch(sp, clock)
    up.tick(NOW + 5)
    assert not path.exists()
    (gap,) = _open_gaps(sp)
    assert gap["reason"] == "rejected_400"


def test_batch_over_upload_max_is_dropped_before_any_attempt(fake_ingest, data_dir):
    up, sp, _, _, clock, _ = _setup(data_dir, _cfg(fake_ingest.url, upload_max_bytes=100_000))
    path = _batch(sp, clock, payload={"name": "big", "text": "x" * 200_000})  # small on disk, large inflated
    assert path.stat().st_size < 100_000
    up.tick(NOW + 5)
    assert fake_ingest.requests == []
    assert not path.exists()
    (gap,) = _open_gaps(sp)
    assert gap["reason"] == "too_large"


def test_oldest_batch_first(fake_ingest, data_dir):
    up, sp, _, _, clock, _ = _setup(data_dir, _cfg(fake_ingest.url))
    _batch(sp, clock, session="sess-z", name="older")
    _batch(sp, clock, session="sess-a", name="newer")
    _batch(sp, clock, session="sess-z", name="newest")
    up.tick(NOW + 10)
    names = [_sent(c)["events"][0]["payload"]["name"] for c in fake_ingest.calls(BATCHES_PATH)]
    assert names == ["older", "newer", "newest"]


def test_nothing_uploaded_while_rejected_or_signed_out(fake_ingest, data_dir):
    state = ForwarderState(rejected_until=NOW + 100)
    up, sp, _, _, clock, _ = _setup(data_dir, _cfg(fake_ingest.url), state=state)
    path = _batch(sp, clock)
    up.tick(NOW + 5)
    assert fake_ingest.requests == [] and path.exists()

    up2, _, _, _, _, _ = _setup(data_dir, _cfg(fake_ingest.url), signed_in=False)
    auth.TokenCache(data_dir).clear()
    up2.tick(NOW + 5)
    assert fake_ingest.requests == [] and path.exists()


def test_failed_refresh_backs_off_and_keeps_the_refresh_token(fake_ingest, data_dir):
    up, sp, cache, state, clock, _ = _setup(data_dir, _cfg(fake_ingest.url))  # auth endpoint refuses connections
    refresh = make_token("ref")
    cache.save(None, refresh, 0)
    path = _batch(sp, clock)
    up.tick(NOW + 5)
    assert fake_ingest.requests == [] and path.exists()
    assert state.last_error == "token_refresh" and up.backoff_s == 5
    assert cache.load()["refresh_token"] == refresh


def test_tick_closes_due_batches_and_sends_them(fake_ingest, data_dir):
    up, sp, _, _, clock, _ = _setup(data_dir, _cfg(fake_ingest.url))
    sp.append("sess-a", {"signal": "event", "payload": {"name": "late"}})
    up.tick(NOW + 60)  # the open batch is past batch_max_age_s: closed and sent in the same tick
    (call,) = fake_ingest.calls(BATCHES_PATH)
    assert _sent(call)["events"][0]["payload"]["name"] == "late"


def test_default_tick_uploads_with_the_forwarder_spool(fake_ingest, data_dir):
    cfg = _cfg(fake_ingest.url)
    up, sp, _, state, clock, access = _setup(data_dir, cfg)
    _batch(sp, clock)
    tick = forwarder._default_tick(cfg, data_dir, sp, state)
    tick(NOW + 5)
    (call,) = fake_ingest.calls(BATCHES_PATH)
    assert call.headers["Authorization"] == "Bearer " + access
    assert sp.closed_batches_oldest_first() == [] and state.last_ack == NOW + 5


def test_probe_me(fake_ingest, data_dir):
    cfg = _cfg(fake_ingest.url)
    cache = auth.TokenCache(data_dir)
    assert uploader.probe_me(cfg, cache) is None  # signed out: no request
    assert fake_ingest.requests == []
    access = make_token("acc")
    cache.save(access, make_token("ref"), 4_000_000_000)
    me = {"on_roster": True, "team": "t", "area": "a", "dev_id_prefix": "0123abcd", "eligible_until": None}
    fake_ingest.script(ME_PATH, (200, me), (401, {"error": "unauthorized"}))
    assert uploader.probe_me(cfg, cache) == me
    (call,) = fake_ingest.calls(ME_PATH)
    assert call.method == "GET" and call.headers["Authorization"] == "Bearer " + access
    assert uploader.probe_me(cfg, cache) is None
