"""Redaction applied by the forwarder before anything is spooled.

Every string value goes through ``scrub_text``, in this order:

1. the developer's home directory becomes ``~``;
2. the developer's own email (any case), username and hostname become
   ``[REDACTED:self]``, also inside longer words;
3. any other email address becomes ``[REDACTED:email]``;
4. each PII or secret shape of ``hooks/block-pii.sh`` and
   ``hooks/block-secrets.sh`` becomes ``[REDACTED:<label>]``, where the label
   is the one the guard script prints for that pattern.

``scrub_payload`` also removes every attribute whose key is on ``DROP_KEYS``,
wherever it appears (resource, scope, record, data point, span, span event).
"""
from __future__ import annotations

import functools
import getpass
import re
import socket
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional, Tuple

DROP_KEYS = frozenset(
    {
        "user.email",
        "user.id",
        "user.account_uuid",
        "organization.id",
        "vcs.repository.url.full",
        "host.name",
    }
)

SELF_PLACEHOLDER = "[REDACTED:self]"
EMAIL_PLACEHOLDER = "[REDACTED:email]"

# The lookbehind lets a match start only where a local part starts, which keeps
# the search linear on long runs of address characters without an "@".
_EMAIL_RE = re.compile(r"(?<![A-Za-z0-9._%+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

# Ported from the two guard scripts, in script order. The parity test compares
# this list with ``patterns_from_shell`` on both scripts: edit the scripts first.
#
# The scripts run these with ``grep -E``. The one dialect difference that
# applies here: inside a bracket expression GNU and BSD grep read a backslash
# literally, so the guard's ``[^/\s:]`` excludes "\" and "s", while Python reads
# ``\s`` as whitespace (what the pattern evidently means). The Python reading
# redacts strictly more, which is the safe side for a scrubber.
#
# Three patterns are plain literals; they are split into adjacent string
# literals so this source file does not itself match the guard hooks that
# check every file write.
PATTERNS: List[Tuple[str, "re.Pattern[str]"]] = [
    (name, re.compile(regex))
    for name, regex in (
        # hooks/block-pii.sh
        ("URN (CJS)", r"\b[0-9]{2}[A-Z]{2}[0-9]{7}\b"),
        ("NINO", r"\b[A-CEGHJ-PR-TW-Z]{2}[0-9]{6}[A-D]\b"),
        (
            "DOB w/ label",
            r"\b(DOB|date.of.birth)\b[^A-Za-z0-9]{0,5}([0-9]{2}[/.-][0-9]{2}[/.-][0-9]{2,4}|[0-9]{4}-[0-9]{2}-[0-9]{2})",
        ),
        ("UK passport hint", r"\bpassport\b[^A-Za-z0-9]{0,5}[0-9]{9}\b"),
        ("Defendant block", r"\b(defendant|witness|victim)\s*(name|surname)\s*[:=]"),
        ("Court reference label", r"\b(case|court).?(ref(erence)?|number)\s*[:=]"),
        # hooks/block-secrets.sh
        ("Azure Key Vault URI", r"[a-z0-9-]+\.vault\.azure\.net"),
        ("Azure Storage key", r"AccountKey=[A-Za-z0-9+/=]{40,}"),
        ("Azure SAS token", r"[?&]sig=[A-Za-z0-9%]{20,}"),
        ("Azure connection string", "DefaultEndpointsProtocol=https;" "AccountName="),
        ("Azure SP secret env", r"AZURE_CLIENT_SECRET\s*=\s*\S+"),
        ("Service principal password", r"--password[= ][A-Za-z0-9~._-]{16,}"),
        ("JWT", r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
        ("Private key block", r"-----BEGIN (RSA |EC |OPENSSH |PGP |DSA )?PRIVATE KEY-----"),
        ("PEM certificate body", "-----BEGIN " "CERTIFICATE-----"),
        ("Kubeconfig marker", "client-certificate" "-data:|client-key" "-data:"),
        ("AWS access key", r"AKIA[0-9A-Z]{16}"),
        ("GitHub PAT", r"gh[pousr]_[A-Za-z0-9]{30,}"),
        ("Slack token", r"xox[baprs]-[A-Za-z0-9-]{10,}"),
        ("Generic password assignment", r"""(password|passwd|pwd)\s*[:=]\s*['"][^'"]{8,}['"]"""),
        ("DB connection w/ creds", r"(postgres|jdbc:postgresql|mysql|jdbc:mysql)://[^/\s:]+:[^@\s]+@"),
    )
]

_OTLP_SIGNALS = frozenset({"logs", "metrics", "traces"})
# Lists of {key, value} pairs in OTLP JSON: attributes everywhere and exemplar
# filteredAttributes (kvlistValue entries are handled next to them).
_KEY_VALUE_LISTS = frozenset({"attributes", "filteredAttributes"})
# Free-text string fields in OTLP JSON: AnyValue strings and the span status message.
# Ids (traceId, spanId) and the time fields are left alone.
_OTLP_TEXT_KEYS = frozenset({"stringValue", "message"})


@dataclass(frozen=True)
class Identity:
    """The developer's own identity values, matched as literals by ``scrub_text``."""

    username: str
    home: str
    hostname: str
    email: str


def _lookup(read) -> str:
    try:
        value = read()
    except Exception:  # noqa: BLE001 - a missing value only means one literal less to redact
        return ""
    return value if isinstance(value, str) else ""


def identity_from_environment(records_email: Optional[str]) -> Identity:
    """Read the identity at run time; ``records_email`` comes from the first ``user.email`` seen."""
    return Identity(
        username=_lookup(getpass.getuser),
        home=_lookup(lambda: str(Path.home())),
        hostname=_lookup(socket.gethostname),
        email=records_email if isinstance(records_email, str) else "",
    )


def first_user_email(payload: Any) -> Optional[str]:
    """Return the first non-empty ``user.email`` attribute value in an OTLP payload, else None."""
    stack = [payload]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            for key, value in node.items():
                if key in _KEY_VALUE_LISTS and isinstance(value, list):
                    for item in value:
                        if isinstance(item, dict) and item.get("key") == "user.email":
                            found = item.get("value")
                            text = found.get("stringValue") if isinstance(found, dict) else None
                            if isinstance(text, str) and text:
                                return text
            stack.extend(reversed(list(node.values())))
        elif isinstance(node, list):
            stack.extend(reversed(node))
    return None


def _text(value: Any) -> str:
    return value if isinstance(value, str) else ""


@functools.lru_cache(maxsize=16)
def _identity_patterns(ident: Identity):
    home = _text(ident.home)
    if len(home) > 1:
        home = home.rstrip("/")
    # A home of "/" (or nothing) is not an identity value.
    home_re = re.compile(re.escape(home) + r"(?![\w-])") if len(home) > 1 else None

    alternatives = []
    email = _text(ident.email)
    if email:
        # First, so the email wins over a username it starts with.
        alternatives.append("(?i:" + re.escape(email) + ")")
    literals = {value for value in (_text(ident.username), _text(ident.hostname)) if value}
    for literal in sorted(literals, key=len, reverse=True):
        alternatives.append(re.escape(literal))
    self_re = re.compile("|".join(alternatives)) if alternatives else None
    return home_re, self_re


def _constant(replacement: str):
    return lambda _match: replacement


# A literal every match of the named pattern contains; the pattern is skipped
# when the text lacks it. The vault pattern backtracks quadratically over a long
# run of [a-z0-9-] characters (about 6 s per 100 KB), and values reach 2 MiB.
_REQUIRED_LITERALS = {"Azure Key Vault URI": ".vault.azure.net"}

_PATTERN_REPLACEMENTS = [
    (compiled, _REQUIRED_LITERALS.get(name), _constant("[REDACTED:" + name + "]")) for name, compiled in PATTERNS
]


def scrub_text(text: str, ident: Identity) -> str:
    """Redact one string; anything that is not a string is returned unchanged."""
    if not isinstance(text, str) or not text:
        return text
    home_re, self_re = _identity_patterns(ident)
    if home_re is not None:
        text = home_re.sub("~", text)
    if self_re is not None:
        text = self_re.sub(_constant(SELF_PLACEHOLDER), text)
    text = _EMAIL_RE.sub(_constant(EMAIL_PLACEHOLDER), text)
    for compiled, required, replace in _PATTERN_REPLACEMENTS:
        if required is None or required in text:
            text = compiled.sub(replace, text)
    return text


def _scrub_key_values(items: list, ident: Identity) -> list:
    kept = []
    for item in items:
        if isinstance(item, dict) and item.get("key") in DROP_KEYS:
            continue
        kept.append(_scrub_otlp(item, ident))
    return kept


def _scrub_otlp(node: Any, ident: Identity) -> Any:
    if isinstance(node, dict):
        out = {}
        for key, value in node.items():
            if key in _KEY_VALUE_LISTS and isinstance(value, list):
                out[key] = _scrub_key_values(value, ident)
            elif key == "kvlistValue" and isinstance(value, dict):
                out[key] = {
                    inner_key: (
                        _scrub_key_values(inner, ident)
                        if inner_key == "values" and isinstance(inner, list)
                        else _scrub_otlp(inner, ident)
                    )
                    for inner_key, inner in value.items()
                }
            elif key in _OTLP_TEXT_KEYS:
                out[key] = scrub_text(value, ident)
            else:
                out[key] = _scrub_otlp(value, ident)
        return out
    if isinstance(node, list):
        return [_scrub_otlp(item, ident) for item in node]
    return node


def _scrub_any(node: Any, ident: Identity) -> Any:
    if isinstance(node, dict):
        return {
            scrub_text(key, ident): _scrub_any(value, ident)
            for key, value in node.items()
            if key not in DROP_KEYS
        }
    if isinstance(node, list):
        return [_scrub_any(item, ident) for item in node]
    return scrub_text(node, ident)


def scrub_payload(signal: str, payload: dict, ident: Identity) -> dict:
    """Return a scrubbed copy of one payload; the input is not modified.

    For ``logs``, ``metrics`` and ``traces`` (OTLP http/json) the walk removes
    the DROP_KEYS attributes and scrubs every ``stringValue`` (attribute values
    at every level, log bodies, nested array and kvlist values) and span status
    messages. Any other signal (hook or event JSON) has every string value and
    every string key scrubbed and DROP_KEYS keys removed.
    """
    if signal in _OTLP_SIGNALS:
        return _scrub_otlp(payload, ident)
    return _scrub_any(payload, ident)


# --- guard-script parity -------------------------------------------------------

_ARRAY_START = re.compile(r"^\s*patterns=\(\s*$")
_ARRAY_END = re.compile(r"^\s*\)\s*$")
_DOUBLE_QUOTED = re.compile(r'"((?:[^"\\]|\\.)*)"')
# Inside bash double quotes a backslash escapes only $ ` " \ and a newline.
_BASH_ESCAPE = re.compile(r'\\([$`"\\\n])')
# POSIX named classes have no Python spelling; translate them to ranges.
_POSIX_CLASSES = {
    "alpha": "A-Za-z",
    "digit": "0-9",
    "alnum": "A-Za-z0-9",
    "upper": "A-Z",
    "lower": "a-z",
    "xdigit": "0-9A-Fa-f",
    "space": r"\s",
    "blank": r" \t",
}
_POSIX_CLASS_RE = re.compile(r"\[:(" + "|".join(_POSIX_CLASSES) + r"):\]")


def _ere_to_python(regex: str) -> str:
    return _POSIX_CLASS_RE.sub(lambda match: _POSIX_CLASSES[match.group(1)], regex)


def patterns_from_shell(path: Path) -> List[Tuple[str, str]]:
    """Extract ``(label, regex)`` pairs from a guard script's ``patterns=( ... )`` array.

    Each entry is a bash double-quoted ``"label::regex"`` string. The bash
    unescaping is applied, the label is the text before the first ``::`` and the
    regex the text after the last ``::`` (as ``${p%%::*}`` and ``${p##*::}`` do),
    and POSIX named classes are translated for Python ``re``.
    """
    entries: List[Tuple[str, str]] = []
    inside = False
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not inside:
            inside = bool(_ARRAY_START.match(line))
            continue
        if _ARRAY_END.match(line):
            break
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        for raw in _DOUBLE_QUOTED.findall(stripped):
            value = _BASH_ESCAPE.sub(r"\1", raw)
            label = value.split("::", 1)[0]
            regex = value.rsplit("::", 1)[-1]
            entries.append((label, _ere_to_python(regex)))
    return entries
