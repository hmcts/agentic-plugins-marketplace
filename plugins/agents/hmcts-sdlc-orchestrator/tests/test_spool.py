import gzip
import hashlib
import json
from pathlib import Path

import pytest

from cpp_telemetry import PLUGIN_VERSION, spool
from cpp_telemetry.config import Config

SID = "11111111-1111-1111-1111-111111111111"
SID_B = "22222222-2222-2222-2222-222222222222"
T0 = 1_800_000_000.0  # invented instant, 2027-01-15T08:00:00Z
DAY = 86_400.0


class FakeClock:
    def __init__(self, now: float = T0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def sp(tmp_path, clock):
    return spool.Spool(tmp_path, Config(), clock=clock)


def env(text="invented prompt text", signal="logs"):
    return {"signal": signal, "payload": {"body": text}}


def read_gz(path: Path) -> dict:
    with gzip.open(str(path), "rt", encoding="utf-8") as fh:
        return json.load(fh)


def manifest(tmp_path: Path, sid: str = SID) -> dict:
    return json.loads((tmp_path / "spool" / sid / "manifest.json").read_text(encoding="utf-8"))


def sha(events) -> str:
    return hashlib.sha256(json.dumps(events, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def test_append_opens_batch_and_writes_line(tmp_path, sp):
    sp.append(SID, env("first"))
    seq = int(T0 * 1000)
    path = tmp_path / "spool" / SID / "{}.open.jsonl".format(seq)
    lines = path.read_text(encoding="utf-8").splitlines()
    assert [json.loads(line) for line in lines] == [
        {"signal": "logs", "received_at": "2027-01-15T08:00:00.000Z", "payload": {"body": "first"}}
    ]
    assert list(json.loads(lines[0])) == ["signal", "received_at", "payload"]
    assert manifest(tmp_path) == {"open_seq": seq, "last_seq": seq}
    sp.append(SID, env("second", signal="hook"))
    assert len(path.read_text(encoding="utf-8").splitlines()) == 2
    assert sorted(p.name for p in (tmp_path / "spool" / SID).iterdir()) == ["{}.open.jsonl".format(seq), "manifest.json"]


def test_append_keeps_a_supplied_received_at_and_rejects_bad_envelopes(tmp_path, sp):
    sp.append(SID, {"signal": "event", "received_at": "2027-01-15T07:59:59.123Z", "payload": {"name": "x"}, "extra": 1})
    sp.append(SID, {"signal": "unknown", "payload": {}})
    sp.append(SID, {"signal": "logs", "payload": "not an object"})
    sp.append(SID, {"signal": "metrics", "payload": {"value": float("nan")}})
    sp.append(SID, {"signal": "metrics", "payload": {"value": object()}})
    sp.append(SID, "not a dict")
    (path,) = (tmp_path / "spool" / SID).glob("*.open.jsonl")
    assert [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()] == [
        {"signal": "event", "received_at": "2027-01-15T07:59:59.123Z", "payload": {"name": "x"}}
    ]


@pytest.mark.parametrize("bad", ["", ".", "..", "../escape", "a/b", "a..b", "x" * 129, "id\nnext", "nul\x00", "sp ace"])
def test_invalid_session_id_is_refused_and_not_logged(tmp_path, sp, bad):
    sp.append(bad, env())
    assert not any((tmp_path / "spool").glob("*.open.jsonl"))
    assert not (tmp_path / "escape").exists()
    assert [p.name for p in (tmp_path / "spool").iterdir()] == [] if (tmp_path / "spool").exists() else True
    log_text = (tmp_path / "forwarder.log").read_text(encoding="utf-8")
    assert "session id refused" in log_text
    if bad.strip(".\n\x00 "):
        assert bad not in log_text
    with pytest.raises(ValueError):
        sp.next_seq(bad)


def test_close_on_size(tmp_path, sp):
    big = "x" * 1_000_100
    sp.append(SID, env(big))
    closed = sp.close_due(T0)  # age 0, size over 1,000,000 bytes
    assert len(closed) == 1 and closed[0].name == "{}.json.gz".format(int(T0 * 1000))
    assert read_gz(closed[0])["events"][0]["payload"]["body"] == big
    assert manifest(tmp_path)["open_seq"] is None
    # A record that would take a non-empty batch past the limit rolls the batch over first.
    sp.append(SID, env("y" * 600_000))
    sp.append(SID, env("z" * 600_000))
    assert len(sp.closed_batches_oldest_first()) == 2
    (open_path,) = (tmp_path / "spool" / SID).glob("*.open.jsonl")
    assert json.loads(open_path.read_text(encoding="utf-8"))["payload"]["body"][0] == "z"
    assert sp.close_due(T0) == []  # 600,000 bytes, age 0: stays open


def test_close_on_age_with_fake_clock(tmp_path, sp, clock):
    sp.append(SID, env())
    clock.now = T0 + 5
    sp.append(SID, env("later"))  # age counts from the first record
    assert sp.close_due(T0 + 9.999) == []
    clock.now = T0 + 10
    closed = sp.close_due()
    assert [p.name for p in closed] == ["{}.json.gz".format(int(T0 * 1000))]
    assert len(read_gz(closed[0])["events"]) == 2
    assert not any((tmp_path / "spool" / SID).glob("*.open.jsonl"))
    assert sp.close_due() == []


def test_closed_batch_has_sha_of_canonical_events(tmp_path, sp, clock):
    sp.append(SID, env("b", signal="traces"))
    sp.append(SID, {"signal": "event", "payload": {"z": [1, 2.5, None], "a": "é中"}})
    (path,) = sp.close_all()
    batch = read_gz(path)
    assert list(batch) == ["plugin_version", "engine_version", "session_id", "batch_seq", "content_sha256", "events"]
    assert batch["plugin_version"] == PLUGIN_VERSION and batch["engine_version"] is None
    assert batch["session_id"] == SID and batch["batch_seq"] == int(T0 * 1000)
    assert [e["signal"] for e in batch["events"]] == ["traces", "event"]
    assert batch["content_sha256"] == sha(batch["events"])
    assert manifest(tmp_path) == {"open_seq": None, "last_seq": int(T0 * 1000)}
    sp.set_engine_version("2.1.300")
    clock.now = T0 + 1
    sp.append(SID, env())
    (path2,) = sp.close_all()
    assert read_gz(path2)["engine_version"] == "2.1.300"


def test_next_seq_is_forced_past_the_previous_in_the_same_millisecond(tmp_path, sp):
    sp.append(SID, env())
    sp.close_all()
    sp.append(SID, env())
    first, second = sp.closed_batches_oldest_first() + sp.close_all()
    assert int(second.name.split(".")[0]) == int(first.name.split(".")[0]) + 1
    assert sp.next_seq(SID) == int(T0 * 1000) + 2


def test_reaper_closes_orphan_and_next_seq_is_greater(tmp_path, clock):
    orphan_seq = int(T0 * 1000) + 60_000  # opened under a clock that ran ahead
    session = tmp_path / "spool" / SID
    session.mkdir(parents=True)
    good = [
        {"signal": "logs", "received_at": "2027-01-15T08:01:00.000Z", "payload": {"body": "invented one"}},
        {"signal": "logs", "received_at": "2027-01-15T08:01:01.000Z", "payload": {"body": "invented two"}},
    ]
    torn = '{"signal": "logs", "received_at": "2027-01-15T08:01:02.000Z", "payload": {"body": "torn secretive tail'
    body = "".join(json.dumps(e) + "\n" for e in good) + torn
    (session / "{}.open.jsonl".format(orphan_seq)).write_bytes(body.encode("utf-8"))
    (session / "manifest.json").write_text('{"open_seq": 5, "last_seq": 5}', encoding="utf-8")  # stale
    (session / "{}.json.gz.tmp".format(orphan_seq - 1)).write_bytes(b"half")  # crash leftover
    # A second session whose close finished but whose open file was not yet removed.
    done = tmp_path / "spool" / SID_B
    done.mkdir()
    (done / "100.open.jsonl").write_text(json.dumps(good[0]) + "\n", encoding="utf-8")
    sp = spool.Spool(tmp_path, Config(), clock=clock)
    sp.append(SID_B, env())  # a second open batch in SID_B: the reaper closes it too
    with gzip.open(str(done / "100.json.gz"), "wt", encoding="utf-8") as fh:
        json.dump({"marker": "already closed"}, fh)

    reaped = spool.Spool(tmp_path, Config(), clock=clock).reap_orphans()

    assert session / "{}.json.gz".format(orphan_seq) in reaped
    batch = read_gz(session / "{}.json.gz".format(orphan_seq))
    assert batch["events"] == good and batch["batch_seq"] == orphan_seq and batch["content_sha256"] == sha(good)
    assert not any(session.glob("*.open.jsonl")) and not any(session.glob("*.tmp"))
    assert manifest(tmp_path) == {"open_seq": None, "last_seq": orphan_seq}
    assert spool.Spool(tmp_path, Config(), clock=clock).next_seq(SID) > orphan_seq
    assert read_gz(done / "100.json.gz") == {"marker": "already closed"}
    assert not (done / "100.open.jsonl").exists() and not any(done.glob("*.open.jsonl"))
    log_text = (tmp_path / "forwarder.log").read_text(encoding="utf-8")
    assert "dropped 1 corrupt line" in log_text
    assert "secretive" not in log_text and "invented" not in log_text


def test_reaper_survives_an_unreadable_orphan(tmp_path, clock):
    session = tmp_path / "spool" / SID
    session.mkdir(parents=True)
    (session / "7.open.jsonl").write_bytes(b"\xff\xfe\x00garbage\n{not json}\n")
    (session / "8.open.jsonl").write_text('{"signal": "logs", "payload": "not an object"}\n', encoding="utf-8")
    sp = spool.Spool(tmp_path, Config(), clock=clock)
    assert sp.reap_orphans() == []
    assert list(session.glob("*.open.jsonl")) == [] and list(session.glob("*.json.gz")) == []
    assert sp.next_seq(SID) == int(T0 * 1000)
    assert manifest(tmp_path) == {"open_seq": None, "last_seq": 8}


def test_resequence_gives_new_seq_same_events(tmp_path, sp, clock):
    sp.append(SID, env("one"))
    sp.append(SID, env("two"))
    (old,) = sp.close_all()
    before = read_gz(old)
    clock.now = T0 + 3
    new = sp.resequence(old)
    after = read_gz(new)
    assert not old.exists() and new.parent == old.parent
    assert int(new.name.split(".")[0]) == after["batch_seq"] == int((T0 + 3) * 1000) > before["batch_seq"]
    assert after["events"] == before["events"]
    assert after["content_sha256"] == sha(after["events"])  # events-only formula: same value, recomputed
    assert manifest(tmp_path)["last_seq"] == after["batch_seq"]
    assert sp.closed_batches_oldest_first() == [new]


def test_expire_after_30_days_writes_gap(tmp_path, sp, clock):
    sp.append(SID, env("a"))
    clock.now = T0 + 2
    sp.append(SID, env("b"))
    (old,) = sp.close_all()
    assert sp.expire(T0 + 30 * DAY) == []  # exactly 30 days is not older
    clock.now = T0 + 30 * DAY + 1
    gaps = sp.expire(clock.now)
    assert not old.exists()
    assert len(gaps) == 1
    gap = gaps[0]
    assert gap["signal"] == "event"
    assert gap["payload"] == {
        "name": "gap",
        "reason": "dwell",
        "session_id": SID,
        "batch_seq": int(T0 * 1000),
        "from_ts": "2027-01-15T08:00:00.000Z",
        "to_ts": "2027-01-15T08:00:02.000Z",
    }
    (open_path,) = (tmp_path / "spool" / SID).glob("*.open.jsonl")
    assert json.loads(open_path.read_text(encoding="utf-8")) == gap
    assert sp.expire(clock.now) == []


def test_drop_with_gap_for_uploader_reasons(tmp_path, sp):
    sp.append(SID, env())
    (path,) = sp.close_all()
    gap = sp.drop_with_gap(path, "too_large")
    assert gap["payload"]["reason"] == "too_large" and gap["payload"]["batch_seq"] == int(T0 * 1000)
    assert not path.exists()


def test_append_survives_a_spool_deleted_from_outside(tmp_path, sp):
    import shutil

    sp.append(SID, env("before"))
    shutil.rmtree(str(tmp_path / "spool"))
    sp.append(SID, env("after"))
    (path,) = (tmp_path / "spool" / SID).glob("*.open.jsonl")
    assert json.loads(path.read_text(encoding="utf-8"))["payload"]["body"] == "after"


def test_is_full_guard(tmp_path, sp, monkeypatch):
    assert Config().spool_max_bytes == 2_000_000_000
    sp.append(SID, env("abc"))
    real = sp.total_bytes()
    files = [p for p in (tmp_path / "spool").rglob("*") if p.is_file()]
    assert real == sum(p.stat().st_size for p in files) > 0
    assert not sp.is_full()
    monkeypatch.setattr(sp, "total_bytes", lambda: 2_000_000_000)
    assert not sp.is_full()
    monkeypatch.setattr(sp, "total_bytes", lambda: 2_000_000_001)
    assert sp.is_full()
    small = spool.Spool(tmp_path, Config(spool_max_bytes=real - 1))
    assert small.is_full()


def test_oldest_first_order_across_sessions(tmp_path, sp, clock):
    sp.append(SID, env())
    sp.close_all()
    clock.now = T0 + 1
    sp.append(SID_B, env())
    sp.close_all()
    clock.now = T0 + 2
    sp.append(SID, env())
    sp.close_all()
    sp.append(SID_B, env())  # open batches are never listed
    order = [(p.parent.name, int(p.name.split(".")[0])) for p in sp.closed_batches_oldest_first()]
    ms = int(T0 * 1000)
    assert order == [(SID, ms), (SID_B, ms + 1000), (SID, ms + 2000)]


def test_delete_removes_only_closed_spool_batches(tmp_path, sp):
    sp.append(SID, env())
    (path,) = sp.close_all()
    outside = tmp_path / "keep.json.gz"
    outside.write_bytes(b"x")
    with pytest.raises(ValueError):
        sp.delete(outside)
    sp.append(SID, env())
    (open_path,) = (tmp_path / "spool" / SID).glob("*.open.jsonl")
    with pytest.raises(ValueError):
        sp.delete(open_path)
    sp.delete(path)
    sp.delete(path)  # already gone: no error
    assert not path.exists() and outside.exists() and open_path.exists()


def test_expire_prunes_stale_empty_session_dirs(tmp_path, sp, clock):
    sp.append(SID, env())
    (path,) = sp.close_all()
    sp.delete(path)  # uploaded
    clock.now = T0 + 31 * DAY
    sp.append(SID_B, env())
    assert sp.expire(clock.now) == []
    assert not (tmp_path / "spool" / SID).exists()
    assert (tmp_path / "spool" / SID_B).exists()


def test_next_seq_follows_the_manifest_after_upload_when_the_clock_steps_back(tmp_path, sp, clock):
    sp.append(SID, env())
    (path,) = sp.close_all()
    sp.delete(path)  # uploaded: only the manifest remembers the number
    clock.now = T0 - 60
    sp.append(SID, env())
    (open_path,) = (tmp_path / "spool" / SID).glob("*.open.jsonl")
    assert open_path.name == "{}.open.jsonl".format(int(T0 * 1000) + 1)


def test_gap_joins_the_existing_open_batch(tmp_path, sp, clock):
    sp.append(SID, env("old"))
    (old,) = sp.close_all()
    clock.now = T0 + 31 * DAY
    sp.append(SID, env("current"))
    (open_path,) = (tmp_path / "spool" / SID).glob("*.open.jsonl")
    (gap,) = sp.expire()
    lines = [json.loads(line) for line in open_path.read_text(encoding="utf-8").splitlines()]
    assert [line["payload"].get("body", line["payload"].get("name")) for line in lines] == ["current", "gap"]
    assert lines[1] == gap and not old.exists()


def test_threaded_appends_keep_every_line(tmp_path, sp):
    import threading

    def worker(n):
        for i in range(50):
            sp.append(SID, env("t{}-{}".format(n, i)))

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    (path,) = sp.close_all()
    batch = read_gz(path)
    bodies = sorted(e["payload"]["body"] for e in batch["events"])
    assert bodies == sorted("t{}-{}".format(n, i) for n in range(8) for i in range(50))
    assert batch["content_sha256"] == sha(batch["events"])


def test_unhashable_signal_is_refused_not_raised(tmp_path, sp):
    sp.append(SID, {"signal": ["logs"], "payload": {}})
    sp.append(SID, {"signal": {"x": 1}, "payload": {}})
    assert not (tmp_path / "spool" / SID).exists()


def test_close_due_survives_a_non_os_error(tmp_path, sp, clock, monkeypatch):
    sp.append(SID, env())
    clock.now += 11

    def broken(session_id, seq):
        raise ValueError("invented failure")

    monkeypatch.setattr(sp, "_close", broken)
    assert sp.close_due() == [] and sp.close_all() == []
    assert "ValueError" in (tmp_path / "forwarder.log").read_text()


def test_total_bytes_skips_only_a_vanished_file(tmp_path, sp, monkeypatch):
    sp.append(SID, env("abc"))
    sp.append(SID_B, env("def"))
    full = sp.total_bytes()
    vanished = next((tmp_path / "spool" / SID).glob("*.open.jsonl"))
    real_lstat = spool.os.lstat

    def lstat(path, *args, **kwargs):
        if str(path) == str(vanished):
            raise FileNotFoundError(str(path))
        return real_lstat(path, *args, **kwargs)

    monkeypatch.setattr(spool.os, "lstat", lstat)
    assert sp.total_bytes() == full - vanished.stat().st_size


def test_is_empty_counts_open_and_closed_batches(tmp_path, sp):
    assert sp.is_empty()
    sp.append(SID, env())
    assert not sp.is_empty()
    sp.close_all()
    assert not sp.is_empty()
    for path in sp.closed_batches_oldest_first():
        sp.delete(path)
    assert sp.is_empty()
