"""Redaction applied by the forwarder before anything is spooled.

Every string value goes through ``scrub_text``, in this order:

1. the developer's home directory becomes ``~``;
2. the developer's own email (any case), username and hostname become
   ``[REDACTED:self]``; a username or hostname of 4 characters or more also
   inside longer words, a shorter one only as a whole word;
3. any other email address becomes ``[REDACTED:email]``;
4. each PII or secret shape of ``hooks/block-pii.sh`` and
   ``hooks/block-secrets.sh`` becomes ``[REDACTED:<label>]``, where the label
   is the one the guard script prints for that pattern.

``scrub_payload`` also removes every attribute whose key is on ``DROP_KEYS``,
wherever it appears (resource, scope, record, data point, span, span event).
Values of id attributes (``session.id``, ``tool_use_id``, any key ending in
``.id`` or ``_id``, ...) skip steps 1-3, so an id never gains a placeholder;
step 4 still applies to them. Attribute names and dict keys are never changed.
"""
from __future__ import annotations

import functools
import getpass
import logging
import re
import socket
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, List, Optional, Tuple

from .log import LOGGER_NAME

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
DEPTH_PLACEHOLDER = "[REDACTED:depth]"

_LOG = logging.getLogger(LOGGER_NAME)

# The lookbehind lets a match start only where a local part starts, which keeps
# the search linear on long runs of address characters without an "@".
_EMAIL_RE = re.compile(r"(?<![A-Za-z0-9._%+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

# Ported from the two guard scripts, in script order. The parity test compares
# this list with ``patterns_from_shell`` on both scripts: edit the scripts first.
# Redaction runs RUNTIME_PATTERNS (below), derived from this list.
#
# The scripts run these with ``grep -E``; the pattern text is kept identical and
# Python reads it more widely in two ways, both on the safe side for a scrubber:
# - inside a bracket expression GNU grep reads a backslash literally (checked
#   with GNU grep 3.11; BSD grep not checked), so the guard's ``[^/\s:]``
#   excludes "\" and "s", while Python reads ``\s`` as whitespace (what the
#   pattern evidently means);
# - grep matches line by line, while Python's ``\s`` and negated classes can
#   cross a newline inside a multi-line value.
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

# --- linear-time runtime patterns ----------------------------------------------
#
# Export values reach 2 MiB and tool output is attacker-influenced, so redaction
# must stay linear. Three guard patterns backtrack quadratically as written
# (Key Vault, JWT, DB connection). Redaction therefore runs RUNTIME_PATTERNS:
# 1. ``_linearise`` bounds every repeat at _BOUND characters;
# 2. the Key Vault pattern gains a leading lookbehind, so a match starts only
#    where a run of host characters starts (the leftmost match started there
#    anyway, so matches are unchanged);
# 3. JWT and DB are tried only at candidate starts found by a linear pre-scan
#    (``eyJ``; a scheme before ``://``), each within _WINDOW characters.
# Matches whose repeats fit within _BOUND characters are the same as with
# PATTERNS. A longer run is redacted only up to _BOUND characters, or not at
# all when a fixed character must follow it.

_BOUND = 4096
_WINDOW = 8192
_UNBOUNDED_RANGE = re.compile(r"\{(\d+),\}")
_CLASS_REPEAT = re.compile(r"(\]|\\[sSdDwW])([+*])")


def _linearise(pattern: str) -> str:
    """Bound every repeat: ``{n,}`` -> ``{n,4096}``; ``+`` / ``*`` after a class -> ``{1,4096}`` / ``{0,4096}``."""
    pattern = _UNBOUNDED_RANGE.sub(lambda m: "{%s,%d}" % (m.group(1), _BOUND), pattern)
    return _CLASS_REPEAT.sub(
        lambda m: "%s{%d,%d}" % (m.group(1), 0 if m.group(2) == "*" else 1, _BOUND), pattern
    )


_LOOKBEHIND = {"Azure Key Vault URI": "(?<![a-z0-9-])"}

RUNTIME_PATTERNS: List[Tuple[str, "re.Pattern[str]"]] = [
    (name, re.compile(_LOOKBEHIND.get(name, "") + _linearise(compiled.pattern))) for name, compiled in PATTERNS
]

# A literal every match of the named pattern contains; the pattern is skipped
# when the text lacks it (a cheap shortcut, not needed for linearity).
_REQUIRED_LITERALS = {"Azure Key Vault URI": ".vault.azure.net"}


class _Finder:
    """First position at or after ``i`` of something, cached for a left-to-right scan.

    Queries must not go backwards; the cache keeps the whole scan linear.
    """

    def __init__(self, search: Callable[[int], Optional[int]]):
        self._search = search
        self._from: Optional[int] = None
        self._found: Optional[int] = None

    def first_from(self, i: int) -> Optional[int]:
        if self._from is None or i < self._from or (self._found is not None and i > self._found):
            self._from = i
            self._found = self._search(i)
        return self._found


def _regex_finder(text: str, regex: "re.Pattern[str]") -> _Finder:
    def search(i: int) -> Optional[int]:
        match = regex.search(text, i)
        return match.start() if match else None

    return _Finder(search)


def _str_finder(text: str, needle: str) -> _Finder:
    def search(i: int) -> Optional[int]:
        index = text.find(needle, i)
        return index if index != -1 else None

    return _Finder(search)


_JWT_NOT_TOKEN_CHAR = re.compile(r"[^A-Za-z0-9_-]")


def _jwt_candidates(text: str):
    """Candidate starts for the JWT pattern.

    The first segment is a run of token characters that must end in ".". Every
    ``eyJ`` inside one run shares that end, so they all match or all fail:
    a run not followed by "." is skipped whole, and at most one match is tried
    per run (the leftmost ``eyJ`` within _BOUND characters of the run end).
    """
    run_end = _regex_finder(text, _JWT_NOT_TOKEN_CHAR)

    def next_candidate(pos: int) -> Optional[Tuple[int, int]]:
        while True:
            start = text.find("eyJ", pos)
            if start == -1:
                return None
            end = run_end.first_from(start + 3)
            if end is None:
                return None  # the run reaches the end of the text: no "." follows
            if text[end] != ".":
                pos = end
                continue
            length = end - start - 3
            if length > _BOUND:
                pos = end - _BOUND - 3
                continue
            if length < 10:
                pos = end
                continue
            return start, end

    return next_candidate


_DB_SCHEMES = ("jdbc:postgresql", "jdbc:mysql", "postgres", "mysql")  # longest first: leftmost start wins
_DB_MAX_SPAN = len("jdbc:postgresql") + 3 + _BOUND + 1 + _BOUND + 1
_WHITESPACE = re.compile(r"\s")


def _db_candidates(text: str):
    """Candidate starts for the DB connection pattern.

    A match holds no whitespace and ends at an "@", so a candidate is tried only
    when the next "@" comes before the next whitespace and within reach.
    """
    next_at = _str_finder(text, "@")
    next_space = _regex_finder(text, _WHITESPACE)

    def next_candidate(pos: int) -> Optional[Tuple[int, int]]:
        while True:
            sep = text.find("://", pos)
            if sep == -1:
                return None
            start = next(
                (sep - len(s) for s in _DB_SCHEMES if sep - len(s) >= pos and text.startswith(s, sep - len(s))),
                None,
            )
            if start is None:
                pos = sep + 1
                continue
            at = next_at.first_from(sep + 3)
            if at is None:
                return None
            space = next_space.first_from(sep + 3)
            if space is not None and space < at:
                pos = space + 1
                continue
            if at - start > _DB_MAX_SPAN:
                pos = sep + 1
                continue
            return start, sep + 1

    return next_candidate


def _sub_at_candidates(text: str, compiled: "re.Pattern[str]", next_candidate, placeholder: str) -> str:
    """Like ``compiled.sub``, but a match is tried only at the candidate starts."""
    pieces: List[str] = []
    last = pos = 0
    while True:
        found = next_candidate(pos)
        if found is None:
            break
        start, resume = found
        match = compiled.match(text, start, min(len(text), start + _WINDOW))
        if match is None:
            pos = resume
            continue
        pieces.append(text[last:start])
        pieces.append(placeholder)
        last = pos = match.end()
    if not pieces:
        return text
    pieces.append(text[last:])
    return "".join(pieces)


_CANDIDATE_SCANS = {"JWT": _jwt_candidates, "DB connection w/ creds": _db_candidates}


def _constant(replacement: str):
    return lambda _match: replacement


_RUNTIME_STEPS = [
    (compiled, _REQUIRED_LITERALS.get(name), _CANDIDATE_SCANS.get(name), "[REDACTED:" + name + "]")
    for name, compiled in RUNTIME_PATTERNS
]


def _redact_patterns(text: str) -> str:
    """Step 4 only: replace every RUNTIME_PATTERNS match with its guard label."""
    for compiled, required, scan, placeholder in _RUNTIME_STEPS:
        if required is not None and required not in text:
            continue
        if scan is None:
            text = compiled.sub(_constant(placeholder), text)
        else:
            text = _sub_at_candidates(text, compiled, scan(text), placeholder)
    return text


# --- identity --------------------------------------------------------------------

_OTLP_SIGNALS = frozenset({"logs", "metrics", "traces"})
# Lists of {key, value} pairs in OTLP JSON: attributes everywhere and exemplar
# filteredAttributes (kvlistValue entries are handled next to them).
_KEY_VALUE_LISTS = frozenset({"attributes", "filteredAttributes"})
# Free-text string fields in OTLP JSON: AnyValue strings and the span status message.
# Ids (traceId, spanId) and the time fields are left alone.
_OTLP_TEXT_KEYS = frozenset({"stringValue", "message"})
# Keys whose values are ids: they skip the identity and email steps.
_ID_KEYS = frozenset(
    {
        "session.id",
        "prompt.id",
        "tool_use_id",
        "tool.use_id",
        "request_id",
        "request.id",
        "client_request_id",
        "trace_id",
        "span_id",
        "parent_span_id",
    }
)
_SHORT_LITERAL = 4
_MAX_DEPTH = 64


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
        escaped = re.escape(literal)
        if len(literal) < _SHORT_LITERAL:
            # A short name inside longer words would mangle ordinary text.
            escaped = r"(?<![A-Za-z0-9_])" + escaped + r"(?![A-Za-z0-9_])"
        alternatives.append(escaped)
    self_re = re.compile("|".join(alternatives)) if alternatives else None
    return home_re, self_re


def _redact(text: Any, ident: Identity, identity_steps: bool) -> Any:
    if not isinstance(text, str) or not text:
        return text
    if identity_steps:
        home_re, self_re = _identity_patterns(ident)
        if home_re is not None:
            text = home_re.sub("~", text)
        if self_re is not None:
            text = self_re.sub(_constant(SELF_PLACEHOLDER), text)
        text = _EMAIL_RE.sub(_constant(EMAIL_PLACEHOLDER), text)
    return _redact_patterns(text)


def scrub_text(text: str, ident: Identity) -> str:
    """Redact one string; anything that is not a string is returned unchanged."""
    return _redact(text, ident, True)


# --- payload walk ------------------------------------------------------------------


def _is_id_key(key: Any) -> bool:
    return isinstance(key, str) and (key in _ID_KEYS or key.endswith(".id") or key.endswith("_id"))


def _is_dropped(key: Any) -> bool:
    return isinstance(key, str) and key in DROP_KEYS


class _Walk:
    """One payload walk: the identity and a count of subtrees cut at _MAX_DEPTH."""

    __slots__ = ("ident", "cut")

    def __init__(self, ident: Identity):
        self.ident = ident
        self.cut = 0

    def too_deep(self) -> str:
        self.cut += 1
        return DEPTH_PLACEHOLDER


def _scrub_key_values(items: list, walk: _Walk, depth: int) -> Any:
    if depth >= _MAX_DEPTH:
        return walk.too_deep()
    kept = []
    for item in items:
        key = item.get("key") if isinstance(item, dict) else None
        if _is_dropped(key):
            continue
        kept.append(_scrub_otlp(item, walk, depth + 1, _is_id_key(key)))
    return kept


def _scrub_otlp(node: Any, walk: _Walk, depth: int, is_id: bool = False) -> Any:
    if isinstance(node, (dict, list)) and depth >= _MAX_DEPTH:
        return walk.too_deep()
    if isinstance(node, dict):
        out = {}
        for key, value in node.items():
            if key in _KEY_VALUE_LISTS and isinstance(value, list):
                out[key] = _scrub_key_values(value, walk, depth + 1)
            elif key == "kvlistValue" and isinstance(value, dict):
                out[key] = {
                    inner_key: (
                        _scrub_key_values(inner, walk, depth + 2)
                        if inner_key == "values" and isinstance(inner, list)
                        else _scrub_otlp(inner, walk, depth + 2, is_id)
                    )
                    for inner_key, inner in value.items()
                }
            elif key in _OTLP_TEXT_KEYS:
                out[key] = _redact(value, walk.ident, not is_id)
            else:
                out[key] = _scrub_otlp(value, walk, depth + 1, is_id)
        return out
    if isinstance(node, list):
        return [_scrub_otlp(item, walk, depth + 1, is_id) for item in node]
    return node


def _scrub_any(node: Any, walk: _Walk, depth: int, is_id: bool = False) -> Any:
    if isinstance(node, (dict, list)) and depth >= _MAX_DEPTH:
        return walk.too_deep()
    if isinstance(node, dict):
        return {
            key: _scrub_any(value, walk, depth + 1, _is_id_key(key))
            for key, value in node.items()
            if not _is_dropped(key)
        }
    if isinstance(node, list):
        return [_scrub_any(item, walk, depth + 1, is_id) for item in node]
    return _redact(node, walk.ident, not is_id)


def scrub_payload(signal: str, payload: dict, ident: Identity) -> dict:
    """Return a scrubbed copy of one payload; the input is not modified.

    For ``logs``, ``metrics`` and ``traces`` (OTLP http/json) the walk removes
    the DROP_KEYS attributes and scrubs every ``stringValue`` (attribute values
    at every level, log bodies, nested array and kvlist values) and span status
    messages. Any other signal (hook or event JSON) has every string value
    scrubbed and DROP_KEYS keys removed. Id values skip the identity and email
    steps. A container nested 64 levels deep is replaced by ``[REDACTED:depth]``
    and one warning is logged (a count, no content).
    """
    walk = _Walk(ident)
    if signal in _OTLP_SIGNALS:
        out = _scrub_otlp(payload, walk, 0)
    else:
        out = _scrub_any(payload, walk, 0)
    if walk.cut:
        _LOG.warning("scrub: replaced %d subtree(s) nested %d or more levels deep", walk.cut, _MAX_DEPTH)
    return out


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
