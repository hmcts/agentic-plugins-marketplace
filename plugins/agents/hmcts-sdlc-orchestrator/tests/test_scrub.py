import json
import time
from pathlib import Path

import pytest

from cpp_telemetry import scrub

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"
IDENT = scrub.Identity(
    username="devuser", home="/home/devuser", hostname="laptop-01", email="devuser@example.invalid"
)
FIXTURE_BY_SIGNAL = {
    "logs": "otlp-logs-small.json",
    "metrics": "otlp-metrics-small.json",
    "traces": "otlp-traces-small.json",
}


def _load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _attribute_keys(node):
    """Every attribute key anywhere in an OTLP payload (resource, record, point, span, event)."""
    keys = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "attributes" and isinstance(value, list):
                keys.extend(item.get("key") for item in value if isinstance(item, dict))
            keys.extend(_attribute_keys(value))
    elif isinstance(node, list):
        for item in node:
            keys.extend(_attribute_keys(item))
    return keys


def _attr(attributes, key):
    return next(item["value"] for item in attributes if item["key"] == key)


def test_drop_keys_are_the_six_keys():
    assert scrub.DROP_KEYS == frozenset(
        {"user.email", "user.id", "user.account_uuid", "organization.id", "vcs.repository.url.full", "host.name"}
    )


def test_drop_keys_removed_from_logs_metrics_spans():
    seen_before = set()
    for signal, name in FIXTURE_BY_SIGNAL.items():
        payload = _load(name)
        before = _attribute_keys(payload)
        seen_before.update(key for key in before if key in scrub.DROP_KEYS)

        out = scrub.scrub_payload(signal, payload, IDENT)

        after = _attribute_keys(out)
        assert not set(after) & scrub.DROP_KEYS, signal
        assert after == [key for key in before if key not in scrub.DROP_KEYS], signal
        assert "session.id" in after, signal
        assert payload == _load(name), "the input payload must not be modified"
    # The fixtures between them carry every key on the drop list, resource attributes included.
    assert seen_before == scrub.DROP_KEYS


def test_identity_literals_inside_longer_text():
    text = "see /home/devuser/repo/x.py by devuserx on laptop-01 <DevUser@Example.invalid>"
    assert scrub.scrub_text(text, IDENT) == "see ~/repo/x.py by [REDACTED:self]x on [REDACTED:self] <[REDACTED:self]>"
    # The email literal wins over the username it starts with.
    assert scrub.scrub_text("mail devuser@example.invalid now", IDENT) == "mail [REDACTED:self] now"


def test_generic_email_redacted():
    text = "ask colleague@example.invalid or Team.Lead+ops@example.invalid"
    assert scrub.scrub_text(text, IDENT) == "ask [REDACTED:email] or [REDACTED:email]"


def test_log_body_and_attribute_values_are_scrubbed():
    out = scrub.scrub_payload("logs", _load("otlp-logs-small.json"), IDENT)
    records = out["resourceLogs"][0]["scopeLogs"][0]["logRecords"]
    assert _attr(records[0]["attributes"], "prompt") == {"stringValue": "open ~/repo/app.py on [REDACTED:self]"}
    assert records[2]["body"] == {"stringValue": "listing of ~/repo for [REDACTED:self]"}
    assert _attr(records[1]["attributes"], "input_tokens") == {"intValue": "120"}
    assert _attr(records[2]["attributes"], "success") == {"boolValue": True}


def test_tool_output_span_event_is_scrubbed():
    out = scrub.scrub_payload("traces", _load("otlp-traces-small.json"), IDENT)
    span = out["resourceSpans"][0]["scopeSpans"][0]["spans"][0]
    event = span["events"][0]
    assert event["name"] == "tool.output"
    assert event["attributes"] == [
        {"key": "output", "value": {"stringValue": "read ~/notes.txt for [REDACTED:email] owner [REDACTED:self]"}}
    ]
    assert span["traceId"] == "0af7651916cd43dd8448eb211c80319c"
    assert span["spanId"] == "b7ad6b7169203331"


def test_patterns_match_guard_scripts():
    shell = scrub.patterns_from_shell(PLUGIN_ROOT / "hooks" / "block-pii.sh") + scrub.patterns_from_shell(
        PLUGIN_ROOT / "hooks" / "block-secrets.sh"
    )
    assert len(shell) == 21  # 6 PII shapes + 15 secret shapes
    assert len({name for name, _ in shell}) == 21
    assert shell == [(name, compiled.pattern) for name, compiled in scrub.PATTERNS]


def test_patterns_from_shell_unescapes_and_splits(tmp_path):
    script = tmp_path / "guard.sh"
    script.write_text(
        r'''#!/usr/bin/env bash
# "Not::an entry"
patterns=(
  "Label one::\\bfoo\\s*[:=]\\s*['\"][^'\"]{8,}['\"]"
  # "Commented::out"
  "Two::colon::pairs::x\\.y"
  "Posix classes::[[:digit:]]{3}[[:space:]]"
)
others=(
  "Ignored::z"
)
''',
        encoding="utf-8",
    )
    assert scrub.patterns_from_shell(script) == [
        ("Label one", r"""\bfoo\s*[:=]\s*['"][^'"]{8,}['"]"""),
        ("Two", r"x\.y"),
        ("Posix classes", r"[0-9]{3}[\s]"),
    ]


def test_patterns_redact_with_guard_labels():
    # Built at run time: no file in the tree may hold a string the guard hooks would block.
    aws_key = "AK" + "IA" + "Q" * 16
    nino = "A" + "B" + "123456" + "C"
    text = scrub.scrub_text("key " + aws_key + " and nino " + nino, IDENT)
    assert text == "key [REDACTED:AWS access key] and nino [REDACTED:NINO]"


def test_long_runs_scrub_quickly():
    # Without its literal prefilter the vault pattern took 6.4 s on 100 KB of [a-z0-9-] (quadratic).
    text = "a" * 200_000 + " " + "b.c" * 50_000
    start = time.perf_counter()
    assert scrub.scrub_text(text, IDENT) == text
    assert time.perf_counter() - start < 2.0
    host = "my" + "-vault"  # the vault pattern still applies when its literal is present
    assert scrub.scrub_text("see " + host + ".vault.azure.net/", IDENT) == "see [REDACTED:Azure Key Vault URI]/"


def test_db_connection_pattern_reads_backslash_s_in_brackets_as_whitespace():
    pw = "s" + "ecretpass"  # contains "s": GNU grep would read [^@\s] as excluding the letter
    text = scrub.scrub_text("url postgres://svc:" + pw + "@dbhost/app", IDENT)
    assert text == "url [REDACTED:DB connection w/ creds]dbhost/app"


def test_scrub_never_raises_on_non_string_values():
    weird = {
        "resourceLogs": [
            None,
            5,
            "x",
            {
                "resource": None,
                "scopeLogs": [
                    {
                        "logRecords": [
                            {"body": None, "attributes": None},
                            {
                                "body": {"stringValue": 7},
                                "attributes": [
                                    None,
                                    3,
                                    {"key": None},
                                    {"key": ["user.email"]},
                                    {"key": {"a": 1}},
                                    {"key": "user.email"},
                                    {"key": "k", "value": None},
                                    {"key": "n", "value": {"intValue": 3}},
                                    {"key": "d", "value": {"doubleValue": 1.5}},
                                    {
                                        "key": "a",
                                        "value": {
                                            "arrayValue": {"values": [{"stringValue": "devuser"}, {"boolValue": False}, None]}
                                        },
                                    },
                                    {
                                        "key": "kv",
                                        "value": {
                                            "kvlistValue": {
                                                "values": [
                                                    {"key": "user.id", "value": {"stringValue": "x"}},
                                                    {"key": "p", "value": {"stringValue": "/home/devuser/x"}},
                                                ]
                                            }
                                        },
                                    },
                                ],
                            },
                        ]
                    }
                ],
            },
        ]
    }
    out = scrub.scrub_payload("logs", weird, IDENT)
    record = out["resourceLogs"][3]["scopeLogs"][0]["logRecords"][1]
    assert record["body"] == {"stringValue": 7}
    assert [item.get("key") if isinstance(item, dict) else item for item in record["attributes"]] == [
        None, 3, None, ["user.email"], {"a": 1}, "k", "n", "d", "a", "kv"
    ]
    assert _attr(record["attributes"][5:], "n") == {"intValue": 3}
    assert _attr(record["attributes"][5:], "a") == {
        "arrayValue": {"values": [{"stringValue": "[REDACTED:self]"}, {"boolValue": False}, None]}
    }
    assert _attr(record["attributes"][5:], "kv") == {
        "kvlistValue": {"values": [{"key": "p", "value": {"stringValue": "~/x"}}]}
    }
    for odd in (None, [], "text", 12, {"resourceLogs": None}, {"resourceSpans": "x"}):
        assert scrub.scrub_payload("traces", odd, IDENT) == odd
    assert scrub.scrub_text(None, IDENT) is None
    assert scrub.scrub_text(42, IDENT) == 42


def test_empty_identity_values_change_nothing():
    blank = scrub.Identity(username="", home="", hostname="", email="")
    assert scrub.scrub_text("plain text stays", blank) == "plain text stays"
    root_home = scrub.Identity(username="devuser", home="/", hostname="laptop-01", email="")
    assert scrub.scrub_text("/etc/hosts by devuser", root_home) == "/etc/hosts by [REDACTED:self]"


def test_non_otlp_signal_scrubs_every_string():
    hook = {"cwd": "/home/devuser/repo", "prompt": "hi devuser", "count": 1, "user.email": "x", "nested": ["laptop-01"]}
    assert scrub.scrub_payload("hook", hook, IDENT) == {
        "cwd": "~/repo",
        "prompt": "hi [REDACTED:self]",
        "count": 1,
        "nested": ["[REDACTED:self]"],
    }


def test_identity_from_environment(monkeypatch):
    monkeypatch.setattr(scrub.getpass, "getuser", lambda: "devuser")
    monkeypatch.setattr(scrub.Path, "home", lambda: Path("/home/devuser"))
    monkeypatch.setattr(scrub.socket, "gethostname", lambda: "laptop-01")
    assert scrub.identity_from_environment("devuser@example.invalid") == IDENT
    assert scrub.identity_from_environment(None).email == ""

    def boom():
        raise OSError("no user database")

    monkeypatch.setattr(scrub.getpass, "getuser", boom)
    monkeypatch.setattr(scrub.socket, "gethostname", boom)
    ident = scrub.identity_from_environment(None)
    assert ident.username == "" and ident.hostname == "" and ident.home == "/home/devuser"


def test_first_user_email_finds_the_attribute():
    assert scrub.first_user_email(_load("otlp-logs-small.json")) == "devuser@example.invalid"
    assert scrub.first_user_email({"resourceLogs": []}) is None
    assert scrub.first_user_email(None) is None
