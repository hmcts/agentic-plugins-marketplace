import json
import logging
import re
import time
from pathlib import Path

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
TWO_MB = 2_000_000


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


def _strings(node):
    if isinstance(node, dict):
        return [s for value in node.values() for s in _strings(value)]
    if isinstance(node, list):
        return [s for item in node for s in _strings(item)]
    return [node] if isinstance(node, str) else []


def _attr(attributes, key):
    return next(item["value"] for item in attributes if item["key"] == key)


def _sample_corpus():
    """One sample per guard pattern, built at run time: no file in the tree may hold a
    string the guard hooks would block."""
    return [
        "urn " + "01" + "AA" + "1234567" + " end",
        "nino " + "AB" + "123456" + "C",
        "D" + "OB: " + "01/02/1990",
        "pass" + "port: " + "123456789",
        "defen" + "dant name: X",
        "case" + " ref: 12",
        "see my-vault" + ".vault" + ".azure.net/x",
        "Account" + "Key=" + "A" * 44,
        "url?s" + "ig=" + "a" * 30,
        "DefaultEndpointsProtocol=https;" + "AccountName=x",
        "AZURE_CLIENT" + "_SECRET = abc",
        "--pass" + "word=" + "a" * 20,
        "Bearer " + "eyJ" + "a" * 20 + "." + "b" * 20 + "." + "c" * 20,
        "-----BEGIN " + "RSA PRIVATE KEY-----",
        "-----BEGIN " + "CERTIFICATE-----",
        "client-key" + "-data: x",
        "AK" + "IA" + "Q" * 16,
        "gh" + "p_" + "a" * 36,
        "xo" + "xb-" + "1" * 12,
        "pass" + "word: '" + "x" * 10 + "'",
        "postgres" + "://u:p@h jdbc:" + "mysql" + "://svc:" + "s" * 5 + "@db",
    ]


def _timed_scrub(text):
    start = time.perf_counter()
    out = scrub.scrub_text(text, IDENT)
    return out, time.perf_counter() - start


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


def test_short_literals_match_whole_words_only():
    short = scrub.Identity(username="al", home="/home/al", hostname="dev", email="")
    text = "also a final value for the devices"
    assert scrub.scrub_text(text, short) == text
    assert scrub.scrub_text("al ran it on dev. (/home/al/x)", short) == (
        "[REDACTED:self] ran it on [REDACTED:self]. (~/x)"
    )


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


def _logs_with(attributes):
    return {"resourceLogs": [{"scopeLogs": [{"logRecords": [{"attributes": attributes}]}]}]}


def _record_attributes(out):
    return out["resourceLogs"][0]["scopeLogs"][0]["logRecords"][0]["attributes"]


def test_id_values_skip_only_the_self_steps():
    short = scrub.Identity(username="ab", home="/home/ab", hostname="laptop-01", email="")
    attributes = [
        # "ab" stands as a whole word here, so without the exemption the short-name rule would redact it.
        {"key": "tool_use_id", "value": {"stringValue": "toolu_01x-ab-y"}},
        {"key": "tool_use_id", "value": {"stringValue": "toolu_01devuserXYZ"}},
        {"key": "request_id", "value": {"stringValue": "req_011CdevuserDEF"}},
        {"key": "session.id", "value": {"stringValue": "sess-devuser-01"}},
        {"key": "prompt", "value": {"stringValue": "toolu_01x-ab-y by devuser"}},
        {"key": "custom.id", "value": {"stringValue": "x-ab-devuser"}},  # not on the allowlist
        {"key": "request.id", "value": {"stringValue": "req:colleague@example.invalid"}},
        {"key": "span_id", "value": {"stringValue": "AK" + "IA" + "Q" * 16}},
        {"key": "tool.use_id", "value": {"arrayValue": {"values": [{"stringValue": "devuser ab"}]}}},
    ]
    payload = _logs_with(attributes)

    by_short = [item["value"] for item in _record_attributes(scrub.scrub_payload("logs", payload, short))]
    assert by_short[0] == {"stringValue": "toolu_01x-ab-y"}
    assert by_short[4] == {"stringValue": "toolu_01x-[REDACTED:self]-y by devuser"}
    assert by_short[5] == {"stringValue": "x-[REDACTED:self]-devuser"}

    by_long = [item["value"] for item in _record_attributes(scrub.scrub_payload("logs", payload, IDENT))]
    assert by_long[1] == {"stringValue": "toolu_01devuserXYZ"}
    assert by_long[2] == {"stringValue": "req_011CdevuserDEF"}
    assert by_long[3] == {"stringValue": "sess-devuser-01"}
    assert by_long[4] == {"stringValue": "toolu_01x-ab-y by [REDACTED:self]"}
    assert by_long[5] == {"stringValue": "x-ab-[REDACTED:self]"}
    # The generic email step and the guard patterns still apply to id values.
    assert by_long[6] == {"stringValue": "req:[REDACTED:email]"}
    assert by_long[7] == {"stringValue": "[REDACTED:AWS access key]"}
    # Only a scalar directly under the id key is exempt, never a nested container.
    assert by_long[8] == {"arrayValue": {"values": [{"stringValue": "[REDACTED:self] ab"}]}}

    hook = {"tool_use_id": "toolu_01devuserXYZ", "session_id": "sess-devuser-01", "request_id": ["devuser"]}
    assert scrub.scrub_payload("hook", hook, IDENT) == {
        "tool_use_id": "toolu_01devuserXYZ",
        "session_id": "sess-devuser-01",  # hook stdin key, on the allowlist since Task 5
        "request_id": ["[REDACTED:self]"],
    }


def test_keys_are_scrubbed_and_collisions_keep_both_values():
    hook = {"devuser": "one", "laptop-01": "two", "plain": "/home/devuser/x"}
    assert scrub.scrub_payload("hook", hook, IDENT) == {
        "[REDACTED:self]": "one",
        "[REDACTED:self]#2": "two",
        "plain": "~/x",
    }
    kvlist = {
        "kvlistValue": {
            "values": [
                {"key": "/home/devuser/a", "value": {"stringValue": "1"}},
                {"key": "devuser", "value": {"stringValue": "2"}},
                {"key": "laptop-01", "value": {"stringValue": "3"}},
            ]
        }
    }
    out = scrub.scrub_payload("logs", _logs_with([{"key": "body.map", "value": kvlist}]), IDENT)
    entries = _record_attributes(out)[0]["value"]["kvlistValue"]["values"]
    assert [entry["key"] for entry in entries] == ["~/a", "[REDACTED:self]", "[REDACTED:self]#2"]
    assert [entry["value"]["stringValue"] for entry in entries] == ["1", "2", "3"]
    # OTLP attribute names are schema names and stay as they are.
    assert _record_attributes(out)[0]["key"] == "body.map"


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


def test_linearise_keeps_matches_identical():
    corpus = _sample_corpus()
    texts = [s for name in FIXTURE_BY_SIGNAL.values() for s in _strings(_load(name))] + corpus + ["\n".join(corpus)]
    for (name, original), (runtime_name, runtime) in zip(scrub.PATTERNS, scrub.RUNTIME_PATTERNS):
        assert name == runtime_name
        hits = 0
        for text in texts:
            expected = [m.span() for m in original.finditer(text)]
            assert [m.span() for m in runtime.finditer(text)] == expected, name
            hits += len(expected)
        assert hits, name + " never matched the corpus"
    for text in texts:
        reference = text
        for name, original in scrub.PATTERNS:
            reference = original.sub(lambda _m, label=name: "[REDACTED:" + label + "]", reference)
        assert scrub._redact_patterns(text) == reference


def test_runtime_patterns_have_no_unbounded_repeat():
    for name, compiled in scrub.RUNTIME_PATTERNS:
        bare = re.sub(r"\\.", "", compiled.pattern)  # drop escapes
        bare = re.sub(r"\[[^\]]*\]", "", bare)  # drop character classes
        assert not re.search(r"[+*]|\{\d+,\}", bare), name


def test_patterns_redact_with_guard_labels():
    aws_key = "AK" + "IA" + "Q" * 16
    nino = "A" + "B" + "123456" + "C"
    text = scrub.scrub_text("key " + aws_key + " and nino " + nino, IDENT)
    assert text == "key [REDACTED:AWS access key] and nino [REDACTED:NINO]"


def test_long_runs_scrub_quickly():
    # Without its literal prefilter the vault pattern took 6.4 s on 100 KB of [a-z0-9-] (quadratic).
    text = "a" * 200_000 + " " + "b.c" * 50_000
    out, seconds = _timed_scrub(text)
    assert out == text and seconds < 2.0
    host = "my" + "-vault"
    assert scrub.scrub_text("see " + host + ".vault.azure.net/", IDENT) == "see [REDACTED:Azure Key Vault URI]/"


def test_jwt_pattern_is_linear_on_2mb():
    # One 2 MB token run from an "eyJ" start is longer than the window: redacted whole (fail closed).
    out, seconds = _timed_scrub("eyJ" * (TWO_MB // 3))
    assert out == "[REDACTED:JWT]"
    assert seconds < 2.0, seconds
    dotted = ("eyJ" * 1365 + ".!") * (TWO_MB // 4097)
    out, seconds = _timed_scrub(dotted)
    assert out == dotted
    assert seconds < 2.0, seconds


def test_db_pattern_is_linear_on_2mb():
    repeated = ("postgres" + "://user") * (TWO_MB // 15)
    out, seconds = _timed_scrub(repeated)
    assert out == "[REDACTED:DB connection w/ creds]"  # 2 MB without whitespace: fail closed
    assert seconds < 2.0, seconds
    spaced = (("postgres" + "://user") * 270 + " ") * (TWO_MB // 4051)
    out, seconds = _timed_scrub(spaced)
    assert out == spaced
    assert seconds < 2.0, seconds
    with_at = (("postgres" + "://user") * 500 + "@ ") * (TWO_MB // 7502)
    out, seconds = _timed_scrub(with_at)
    assert out.count("[REDACTED:DB connection w/ creds]") == TWO_MB // 7502
    assert seconds < 2.0, seconds


def test_bounded_repeats_fail_closed():
    segment = "a" * 23_330
    jwt = "eyJ" + segment + "." + segment + "." + segment  # about 70 KB
    assert scrub.scrub_text("Bearer " + jwt + " end", IDENT) == "Bearer [REDACTED:JWT] end"
    storage_key = "Account" + "Key=" + "A" * 70_000
    assert scrub.scrub_text(storage_key + " end", IDENT) == "[REDACTED:Azure Storage key] end"
    long_user = "postgres" + "://" + "u" * 70_000 + ":p@h"
    assert scrub.scrub_text(long_user + " end", IDENT) == "[REDACTED:DB connection w/ creds] end"


def test_vault_pattern_is_linear_on_2mb_with_its_literal_present():
    text = "my" + ".vault" + ".azure.net " + "a" * TWO_MB
    out, seconds = _timed_scrub(text)
    assert out == "[REDACTED:Azure Key Vault URI] " + "a" * TWO_MB
    assert seconds < 2.0, seconds


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


def test_depth_is_capped_with_one_log_line():
    node = "devuser"
    for _ in range(100):
        node = [node]
    records = []
    handler = logging.Handler()
    handler.emit = records.append
    logger = logging.getLogger("cpp_telemetry")
    logger.addHandler(handler)
    try:
        out = scrub.scrub_payload("hook", {"deep": node, "flat": "devuser"}, IDENT)
    finally:
        logger.removeHandler(handler)
    dumped = json.dumps(out)
    assert "devuser" not in dumped
    inner = out["deep"]
    for _ in range(63):  # the containers at depths 1..63 survive; the one at depth 64 is emptied
        assert isinstance(inner, list) and len(inner) == 1
        inner = inner[0]
    assert inner == []
    assert out["flat"] == "[REDACTED:self]"
    assert len(records) == 1 and "devuser" not in records[0].getMessage()
    # An OTLP attribute list at the cap becomes an empty list, never a string.
    deep_kv = {"key": "k", "value": {"stringValue": "devuser"}}
    node = {"attributes": [deep_kv]}
    for _ in range(40):
        node = {"kvlistValue": {"values": [{"key": "k", "value": node}]}}
    flat = json.dumps(scrub.scrub_payload("logs", {"resourceLogs": [{"resource": node}]}, IDENT))
    assert "devuser" not in flat and '"values": []' in flat


def test_empty_identity_values_change_nothing():
    blank = scrub.Identity(username="", home="", hostname="", email="")
    assert scrub.scrub_text("plain text stays", blank) == "plain text stays"
    root_home = scrub.Identity(username="devuser", home="/", hostname="laptop-01", email="")
    assert scrub.scrub_text("/etc/hosts by devuser", root_home) == "/etc/hosts by [REDACTED:self]"


def test_non_otlp_signal_scrubs_every_string_value_and_key():
    hook = {
        "cwd": "/home/devuser/repo",
        "prompt": "hi devuser",
        "count": 1,
        "user.email": "x",
        "nested": ["laptop-01"],
        "devuser": "laptop-01",
    }
    assert scrub.scrub_payload("hook", hook, IDENT) == {
        "cwd": "~/repo",
        "prompt": "hi [REDACTED:self]",
        "count": 1,
        "nested": ["[REDACTED:self]"],
        "[REDACTED:self]": "[REDACTED:self]",
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


def test_hook_session_id_keeps_a_hex_username_out():
    hex_ident = scrub.Identity(username="aaaa", home="/home/aaaa", hostname="laptop-01", email="")
    hook = {"session_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", "cwd": "/home/aaaa/repo"}
    assert scrub.scrub_payload("hook", hook, hex_ident) == {
        "session_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        "cwd": "~/repo",
    }
    assert "session_id" in scrub.ID_KEYS


def test_colliding_keys_get_suffixes_in_linear_time():
    hook = {"user%d@example.invalid" % n: n for n in range(9000)}
    started = time.perf_counter()
    out = scrub.scrub_payload("hook", hook, IDENT)
    elapsed = time.perf_counter() - started
    assert list(out)[:3] == ["[REDACTED:email]", "[REDACTED:email]#2", "[REDACTED:email]#3"]
    assert out["[REDACTED:email]#9000"] == 8999 and len(out) == 9000
    assert elapsed < 2.0


def test_suffix_counter_skips_a_literal_suffixed_key():
    hook = {"devuser": 1, "[REDACTED:self]#2": 2, "laptop-01": 3, "x@example.invalid": 4}
    out = scrub.scrub_payload("hook", hook, IDENT)
    assert out == {"[REDACTED:self]": 1, "[REDACTED:self]#2": 2, "[REDACTED:self]#3": 3, "[REDACTED:email]": 4}


def test_object_over_10000_keys_drops_the_hook_record():
    hook = {"k%d" % n: n for n in range(10_001)}
    try:
        scrub.scrub_payload("hook", hook, IDENT)
    except scrub.TooManyKeys:
        pass
    else:
        raise AssertionError("an object over the key cap must not be scrubbed")
    assert scrub.scrub_payload("hook", {"k%d" % n: n for n in range(10_000)}, IDENT)["k9999"] == 9999


def test_otlp_record_over_10000_keys_is_dropped_and_counted():
    huge = {"kvlistValue": {"values": [{"key": "k%d" % n, "value": {"intValue": "1"}} for n in range(10_001)]}}
    payload = _logs_with([{"key": "body.map", "value": huge}])
    good = {"attributes": [{"key": "event.name", "value": {"stringValue": "kept"}}]}
    payload["resourceLogs"][0]["scopeLogs"][0]["logRecords"].append(good)
    records = []
    handler = logging.Handler()
    handler.emit = records.append
    logger = logging.getLogger("cpp_telemetry")
    logger.addHandler(handler)
    try:
        out = scrub.scrub_payload("logs", payload, IDENT)
    finally:
        logger.removeHandler(handler)
    assert out["resourceLogs"][0]["scopeLogs"][0]["logRecords"] == [good]
    assert len(records) == 1 and "dropped 1 record" in records[0].getMessage()
