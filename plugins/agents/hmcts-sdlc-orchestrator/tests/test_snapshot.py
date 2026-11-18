import gzip
import json
import subprocess

import pytest

from cpp_telemetry import forwarder, scrub, snapshot
from cpp_telemetry.config import Config
from cpp_telemetry.receiver import ForwarderState, IdentityProvider
from cpp_telemetry.spool import Spool

ORIGIN = "https://example.invalid/org/repo.git"
PROMPT = "please refactor the invented widget module"
IDENT = scrub.Identity(username="devperson", home="/nonexistent/devperson", hostname="box.example.invalid",
                       email="")


def _git(cwd, *args):
    subprocess.run(["git", "-C", str(cwd), "-c", "user.name=Invented Dev", "-c", "user.email=dev@example.invalid"]
                   + list(args), check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path):
    path = tmp_path / "work" / "checkout"
    path.mkdir(parents=True)
    _git(path, "init", "-q", "-b", "main")
    _git(path, "remote", "add", "origin", ORIGIN)
    _git(path, "commit", "-q", "--allow-empty", "-m", "first")
    return path


@pytest.fixture
def transcript(tmp_path):
    path = tmp_path / "transcript.jsonl"
    path.write_text(json.dumps({"type": "user", "version": "2.1.3", "message": PROMPT}) + "\n"
                    + json.dumps({"type": "assistant", "message": PROMPT}) + "\n")
    return path


def _start_hook(cwd, transcript_path, **extra):
    hook = {"hook_event_name": "SessionStart", "session_id": "sess-1", "cwd": str(cwd),
            "transcript_path": str(transcript_path), "source": "startup", "prompt": PROMPT}
    hook.update(extra)
    return hook


def test_session_start_snapshot_has_repo_branch_and_no_content(repo, transcript):
    state = ForwarderState()
    envelopes = snapshot.from_hook(_start_hook(repo, transcript), "1.1.0", state, ident=IDENT, clock=lambda: 0.0)
    assert envelopes == [{"signal": "hook", "payload": {
        "name": "session_start", "session_id": "sess-1", "ts": "1970-01-01T00:00:00.000Z", "repo": "repo",
        "branch": "main", "plugin_version": "1.1.0", "engine_version": "2.1.3", "entrypoint": "cli",
        "source": "startup"}}]
    text = json.dumps(envelopes)
    assert PROMPT not in text and str(repo) not in text and str(transcript) not in text
    assert state.engine_version == "2.1.3"


def test_turn_seq_increments():
    state = ForwarderState()
    seqs = [snapshot.from_hook({"hook_event_name": "Stop", "session_id": sid, "prompt": PROMPT}, "1.1.0", state)
            for sid in ("sess-1", "sess-1", "sess-2", "sess-1")]
    assert [e[0]["payload"]["seq"] for e in seqs] == [1, 2, 1, 3]
    assert set(seqs[0][0]["payload"]) == {"name", "session_id", "ts", "seq"}
    assert seqs[0][0]["payload"]["name"] == "turn" and PROMPT not in json.dumps(seqs)


def test_subagent_stop_session_end_and_unknown_events():
    state = ForwarderState()
    (sub,) = snapshot.from_hook({"hook_event_name": "SubagentStop", "session_id": "s"}, "1.1.0", state)
    assert sub["payload"]["name"] == "subagent_stop" and set(sub["payload"]) == {"name", "session_id", "ts"}
    (end,) = snapshot.from_hook({"hook_event_name": "SessionEnd", "session_id": "s", "reason": "logout"}, "1.1.0",
                                state)
    assert end["payload"]["name"] == "session_end" and end["payload"]["reason"] == "logout"
    (odd,) = snapshot.from_hook({"hook_event_name": "SessionEnd", "session_id": "s", "reason": PROMPT}, "1.1.0", state)
    assert odd["payload"]["reason"] is None
    for event in ("UserPromptSubmit", "PreToolUse", None):
        assert snapshot.from_hook({"hook_event_name": event, "prompt": PROMPT}, "1.1.0", state) == []
    assert snapshot.from_hook("not a dict", "1.1.0", state) == []


def test_session_start_outside_a_repo_falls_back_to_the_directory_name(tmp_path):
    plain = tmp_path / "plain-dir"
    plain.mkdir()
    (env,) = snapshot.from_hook(_start_hook(plain, tmp_path / "absent.jsonl", entrypoint="sdk-ts"), "1.1.0",
                                ForwarderState(), ident=IDENT)
    payload = env["payload"]
    assert (payload["repo"], payload["branch"], payload["engine_version"], payload["entrypoint"]) == \
        ("plain-dir", "", None, "sdk-ts")


def test_repo_and_branch_values_are_scrubbed(tmp_path):
    own = tmp_path / "devperson"
    own.mkdir()
    _git(own, "init", "-q", "-b", "feature/dev@example.invalid")
    _git(own, "commit", "-q", "--allow-empty", "-m", "first")
    (env,) = snapshot.from_hook(_start_hook(own, tmp_path / "absent.jsonl"), "1.1.0", ForwarderState(), ident=IDENT)
    assert env["payload"]["repo"] == scrub.SELF_PLACEHOLDER
    assert "example.invalid" not in env["payload"]["branch"] and scrub.EMAIL_PLACEHOLDER in env["payload"]["branch"]


@pytest.mark.parametrize("url", ["https://example.invalid/org/repo.git", "git@example.invalid:org/repo.git",
                                 "https://example.invalid/org/repo/", "/srv/git/repo.git", "repo"])
def test_repo_basename_forms(url):
    assert snapshot.repo_basename(url) == "repo"


@pytest.mark.parametrize("first_line", ['{"version": "1.0 beta"}', '{"version": 3}', "not json", "[1]", ""])
def test_engine_version_invalid_or_unreadable_is_null(tmp_path, first_line):
    path = tmp_path / "t.jsonl"
    path.write_text(first_line + "\n")
    assert snapshot.engine_version(str(path)) is None
    assert snapshot.engine_version(None) is None


def test_forwarder_on_hook_snapshots_and_stamps_the_engine_version(data_dir, repo, transcript):
    sp = Spool(data_dir, Config())
    state = ForwarderState()
    on_hook = forwarder._default_on_hook("1.1.0", state, IdentityProvider(trusted_email=None), sp)
    (env,) = on_hook(_start_hook(repo, transcript))
    sp.append("sess-1", env)
    (path,) = sp.close_all()
    batch = json.loads(gzip.decompress(path.read_bytes()))
    assert batch["engine_version"] == "2.1.3" and batch["events"][0]["payload"]["repo"] == "repo"
