"""A secret marker takes its secret with it; an id value skips the self steps only when it looks like an id.

Every PEM body and kubeconfig value here is generated at run time from random bytes,
and every marker is split, so no file in the tree holds what the guard hooks block.
"""
import base64
import os
import time

import pytest

from cpp_telemetry import scrub
from tests.test_scrub import IDENT, TWO_MB, _logs_with, _record_attributes

BEGIN, END = "-----BEGIN ", "-----END "
CERT_DATA = "client-certificate" + "-data:"
KEY_DATA = "client-key" + "-data:"
PRIVATE = "[REDACTED:Private key block]"
CERT = "[REDACTED:PEM certificate body]"
KUBE = "[REDACTED:Kubeconfig marker]"


def _b64(size):
    return base64.b64encode(os.urandom(size)).decode("ascii")


def _pem_body(lines=12):
    raw = _b64(48 * lines)
    return "\n".join(raw[i:i + 64] for i in range(0, len(raw), 64))


def _label(kind):
    return kind + "PRIVATE" + " KEY-----"


def _block(label, body):
    return BEGIN + label + "\n" + body + "\n" + END + label


def _gone(out, secret):
    return all(line not in out for line in secret.splitlines())


@pytest.mark.parametrize("kind", ["", "RSA ", "EC ", "OPENSSH ", "PGP ", "DSA "])
def test_private_key_body_is_redacted_through_its_end_line(kind):
    body = _pem_body()
    out = scrub.scrub_text("key:\n" + _block(_label(kind), body) + "\nnext line", IDENT)
    assert out == "key:\n" + PRIVATE + "\nnext line"
    assert _gone(out, body)


def test_certificate_body_is_redacted_through_its_end_line():
    body = _pem_body(4)
    label = "CERTIFICATE" + "-----"
    out = scrub.scrub_text("ca: " + _block(label, body) + " done", IDENT)
    assert out == "ca: " + CERT + " done" and _gone(out, body)


def test_private_key_without_its_end_line_redacts_the_bounded_window():
    body = _pem_body()
    out = scrub.scrub_text(BEGIN + _label("RSA ") + "\n" + body + "\nmore text", IDENT)
    assert out == PRIVATE
    other_end = END + "CERTIFICATE" + "-----"  # an END line of another kind does not close the block
    out = scrub.scrub_text(BEGIN + _label("") + "\n" + body + "\n" + other_end + " tail", IDENT)
    assert out == PRIVATE
    long_body = "A" * 70_000
    marker = BEGIN + _label("EC ")
    out = scrub.scrub_text(marker + long_body + " tail", IDENT)
    assert out == PRIVATE + long_body[65_536:] + " tail"


def test_kubeconfig_values_are_redacted_to_the_end_of_the_line():
    cert, key = _b64(600), _b64(900)
    text = ("users:\n- name: ci-reader\n  user:\n    " + CERT_DATA + " " + cert + "\n    " + KEY_DATA + " " + key
            + "\n    token-file: /etc/ci/token\n")
    out = scrub.scrub_text(text, IDENT)
    assert out == "users:\n- name: ci-reader\n  user:\n    " + KUBE + "\n    " + KUBE + "\n    token-file: /etc/ci/token\n"
    assert cert not in out and key not in out


def test_kubeconfig_values_take_their_deeper_indented_continuation_lines():
    first, second = _b64(48), _b64(48)
    block = "  user:\n    " + KEY_DATA + " |\n      " + first + "\n      " + second + "\n    username: ci\n"
    assert scrub.scrub_text(block, IDENT) == "  user:\n    " + KUBE + "\n    username: ci\n"
    folded = "    " + CERT_DATA + " " + first + "\n      " + second + "\n\n      after-blank\n"
    assert scrub.scrub_text(folded, IDENT) == "    " + KUBE + "\n\n      after-blank\n"


def test_secret_values_are_gone_from_hook_and_otlp_payloads():
    body, key = _pem_body(), _b64(900)
    text = _block(_label("RSA "), body) + "\n    " + KEY_DATA + " " + key
    hook = scrub.scrub_payload("hook", {"tool_response": {"stdout": text}}, IDENT)
    assert hook == {"tool_response": {"stdout": PRIVATE + "\n    " + KUBE}}
    otlp = scrub.scrub_payload("logs", _logs_with([{"key": "output", "value": {"stringValue": text}}]), IDENT)
    assert _record_attributes(otlp)[0]["value"] == {"stringValue": PRIVATE + "\n    " + KUBE}


def _timed(text):
    start = time.perf_counter()
    out = scrub.scrub_text(text, IDENT)
    return out, time.perf_counter() - start


def test_secret_value_redaction_is_linear_on_2mb():
    marker = BEGIN + _label("RSA ")
    out, seconds = _timed(marker * (TWO_MB // len(marker)))
    assert out.startswith(PRIVATE) and seconds < 2.0, seconds
    block = _block(_label(""), "A" * 64) + "\n"
    out, seconds = _timed(block * (TWO_MB // len(block)))
    assert set(out.split("\n")) <= {PRIVATE, ""} and seconds < 2.0, seconds
    line = "    " + KEY_DATA + " " + "A" * 80 + "\n"
    out, seconds = _timed(line * (TWO_MB // len(line)))
    assert out == ("    " + KUBE + "\n") * (TWO_MB // len(line)) and seconds < 2.0, seconds
    continued = KEY_DATA + "\n" + "  x\n" * (TWO_MB // 4)
    out, seconds = _timed(continued)
    assert out == KUBE + "\n" and seconds < 2.0, seconds
    one_line = (KEY_DATA + " ") * (TWO_MB // (len(KEY_DATA) + 1))
    out, seconds = _timed(one_line)
    assert out == KUBE and seconds < 2.0, seconds


def test_the_parity_list_is_unchanged_and_names_the_value_markers():
    names = [name for name, _ in scrub.PATTERNS]
    assert scrub.VALUE_MARKERS == frozenset({"Private key block", "PEM certificate body", "Kubeconfig marker"})
    assert scrub.VALUE_MARKERS <= set(names) and len(names) == 21


# --- the opaque-id exemption ---------------------------------------------------------


def test_an_id_key_holding_free_text_gets_every_step():
    hook = {"session_id": "devuser pasted /home/devuser/notes", "tool_use_id": "toolu_01devuserXYZ"}
    assert scrub.scrub_payload("hook", hook, IDENT) == {
        "session_id": "[REDACTED:self] pasted ~/notes",
        "tool_use_id": "toolu_01devuserXYZ",  # an opaque id keeps its exemption
    }
    assert scrub.scrub_values({"session_id": "/home/devuser/x", "request_id": "req:devuser.01"}, IDENT) == {
        "session_id": "~/x", "request_id": "req:devuser.01"}


def test_an_otlp_id_attribute_holding_free_text_gets_every_step():
    attributes = [
        {"key": "session.id", "value": {"stringValue": "notes of devuser"}},
        {"key": "prompt.id", "value": {"stringValue": "sess-devuser-01\n"}},  # a newline is not an id shape
        {"key": "trace_id", "value": {"stringValue": "devuser" * 37}},  # 259 characters: too long for an id
        {"key": "span_id", "value": {"stringValue": "span.devuser:01_a-b"}},
    ]
    out = [item["value"]["stringValue"] for item in
           _record_attributes(scrub.scrub_payload("logs", _logs_with(attributes), IDENT))]
    assert out == ["notes of [REDACTED:self]", "sess-[REDACTED:self]-01\n", "[REDACTED:self]" * 37,
                   "span.devuser:01_a-b"]
