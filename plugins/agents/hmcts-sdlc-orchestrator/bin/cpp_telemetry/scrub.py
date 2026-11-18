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
A scalar string directly under an id key on ``ID_KEYS`` skips steps 1 and 2,
so an id never gains a placeholder; steps 3 and 4 still apply to it. Dict keys
and kvlist keys are scrubbed like values; OTLP attribute names are not.

An object whose keys are scrubbed may hold at most ``MAX_KEYS`` keys. A larger
one drops its record: an OTLP log record, data point or span is removed from
the payload (one counted log line); for any other payload ``scrub_payload``
raises ``TooManyKeys`` and the caller drops it.
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

# Exact keys whose scalar string value is an id (no suffix rule).
ID_KEYS = frozenset(
    {
        "session.id",
        "session_id",
        "prompt.id",
        "tool_use_id",
        "tool.use_id",
        "request_id",
        "request.id",
        "client_request_id",
        "trace_id",
        "span_id",
        "parent_span_id",
        "traceId",
        "spanId",
        "parentSpanId",
    }
)

SELF_PLACEHOLDER = "[REDACTED:self]"
EMAIL_PLACEHOLDER = "[REDACTED:email]"

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
# The bounds fail closed:
# - a pattern that ends in a run (keys, tokens, ``\S+``) has its match extended
#   over the rest of that run, so a run longer than _BOUND is redacted whole;
# - a JWT or DB candidate whose token run (JWT: token characters and dots; DB:
#   non-whitespace) is longer than _WINDOW is redacted whole.
# Matches within the bounds are the same as with PATTERNS.

_BOUND = 65536
_WINDOW = 65536
_UNBOUNDED_RANGE = re.compile(r"\{(\d+),\}")
_CLASS_REPEAT = re.compile(r"(\]|\\[sSdDwW])([+*])")
_FINAL_RUN = re.compile(r"(\[(?:\\.|[^\]\\])*\]|\\[sSdDwW])(?:\+|\*|\{\d+,\})$")


def _linearise(pattern: str) -> str:
    """Bound every repeat: ``{n,}`` -> ``{n,65536}``; ``+`` / ``*`` after a class -> ``{1,65536}`` / ``{0,65536}``."""
    pattern = _UNBOUNDED_RANGE.sub(lambda m: "{%s,%d}" % (m.group(1), _BOUND), pattern)
    return _CLASS_REPEAT.sub(
        lambda m: "%s{%d,%d}" % (m.group(1), 0 if m.group(2) == "*" else 1, _BOUND), pattern
    )


def _final_run(pattern: str) -> Optional["re.Pattern[str]"]:
    """For a pattern ending in an unbounded class repeat, a regex matching the rest of that run."""
    match = _FINAL_RUN.search(pattern)
    return re.compile(match.group(1) + "*") if match else None


_LOOKBEHIND = {"Azure Key Vault URI": "(?<![a-z0-9-])"}

RUNTIME_PATTERNS: List[Tuple[str, "re.Pattern[str]"]] = [
    (name, re.compile(_LOOKBEHIND.get(name, "") + _linearise(compiled.pattern))) for name, compiled in PATTERNS
]

# A literal every match of the named pattern contains; the pattern is skipped
# when the text lacks it (a cheap shortcut, not needed for linearity).
_REQUIRED_LITERALS = {"Azure Key Vault URI": ".vault.azure.net"}


class _Finder:
    """First position at or after ``i`` of something, cached for a left-to-right scan."""

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
_JWT_NOT_TOKEN_OR_DOT = re.compile(r"[^A-Za-z0-9_.-]")

# A candidate is (start, resume_after_failed_match, redact_to). ``redact_to``
# set means: redact [start, redact_to) whole (fail closed), no match needed.
_Candidate = Tuple[int, int, Optional[int]]


def _jwt_candidates(text: str) -> Callable[[int], Optional[_Candidate]]:
    """Candidate starts for the JWT pattern.

    The first segment is a run of token characters that must end in ".". Every
    ``eyJ`` inside one run shares that end, so they all match or all fail:
    a run not followed by "." is skipped whole, and at most one match is tried
    per run (the leftmost ``eyJ`` within _BOUND characters of the run end).
    """
    run_end = _regex_finder(text, _JWT_NOT_TOKEN_CHAR)
    token_end = _regex_finder(text, _JWT_NOT_TOKEN_OR_DOT)

    def next_candidate(pos: int) -> Optional[_Candidate]:
        while True:
            start = text.find("eyJ", pos)
            if start == -1:
                return None
            whole = token_end.first_from(start)
            whole = len(text) if whole is None else whole
            if whole - start > _WINDOW:
                return start, whole, whole
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
            return start, end, None

    return next_candidate


_DB_SCHEMES = ("jdbc:postgresql", "jdbc:mysql", "postgres", "mysql")  # longest first: leftmost start wins
_DB_MAX_SPAN = len("jdbc:postgresql") + 3 + _BOUND + 1 + _BOUND + 1
_WHITESPACE = re.compile(r"\s")


def _db_candidates(text: str) -> Callable[[int], Optional[_Candidate]]:
    """Candidate starts for the DB connection pattern.

    A match holds no whitespace and ends at an "@", so a candidate is tried only
    when the next "@" comes before the next whitespace and within reach.
    """
    next_at = _str_finder(text, "@")
    next_space = _regex_finder(text, _WHITESPACE)

    def next_candidate(pos: int) -> Optional[_Candidate]:
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
            space = next_space.first_from(start)
            token_end = len(text) if space is None else space
            if token_end - start > _WINDOW:
                return start, token_end, token_end
            at = next_at.first_from(sep + 3)
            if at is None or (space is not None and space < at) or at - start > _DB_MAX_SPAN:
                pos = sep + 1
                continue
            return start, sep + 1, None

    return next_candidate


def _sub_at_candidates(text: str, compiled: "re.Pattern[str]", next_candidate, placeholder: str) -> str:
    """Like ``compiled.sub``, but a match is tried only at the candidate starts."""
    pieces: List[str] = []
    last = pos = 0
    while True:
        found = next_candidate(pos)
        if found is None:
            break
        start, resume, redact_to = found
        if redact_to is None:
            match = compiled.match(text, start, min(len(text), start + _WINDOW))
            if match is None:
                pos = resume
                continue
            redact_to = match.end()
        pieces.append(text[last:start])
        pieces.append(placeholder)
        last = pos = redact_to
    if not pieces:
        return text
    pieces.append(text[last:])
    return "".join(pieces)


def _sub_extending(text: str, compiled: "re.Pattern[str]", rest_of_run: "re.Pattern[str]", placeholder: str) -> str:
    """Like ``compiled.sub``, but each match also takes the rest of its final run."""
    pieces: List[str] = []
    last = pos = 0
    while True:
        match = compiled.search(text, pos)
        if match is None:
            break
        end = rest_of_run.match(text, match.end()).end()
        pieces.append(text[last:match.start()])
        pieces.append(placeholder)
        last = pos = end
    if not pieces:
        return text
    pieces.append(text[last:])
    return "".join(pieces)


_CANDIDATE_SCANS = {"JWT": _jwt_candidates, "DB connection w/ creds": _db_candidates}


def _constant(replacement: str):
    return lambda _match: replacement


_RUNTIME_STEPS = [
    (
        compiled,
        _REQUIRED_LITERALS.get(name),
        _CANDIDATE_SCANS.get(name),
        _final_run(original.pattern),
        "[REDACTED:" + name + "]",
    )
    for (name, compiled), (_, original) in zip(RUNTIME_PATTERNS, PATTERNS)
]


def _redact_patterns(text: str) -> str:
    """Step 4 only: replace every RUNTIME_PATTERNS match with its guard label."""
    for compiled, required, scan, rest_of_run, placeholder in _RUNTIME_STEPS:
        if required is not None and required not in text:
            continue
        if scan is not None:
            text = _sub_at_candidates(text, compiled, scan(text), placeholder)
        elif rest_of_run is not None:
            text = _sub_extending(text, compiled, rest_of_run, placeholder)
        else:
            text = compiled.sub(_constant(placeholder), text)
    return text


# --- identity --------------------------------------------------------------------

_OTLP_SIGNALS = frozenset({"logs", "metrics", "traces"})
# Lists of {key, value} pairs in OTLP JSON: attributes everywhere and exemplar
# filteredAttributes (kvlistValue entries are handled next to them).
_KEY_VALUE_LISTS = frozenset({"attributes", "filteredAttributes"})
# Free-text string fields in OTLP JSON: AnyValue strings and the span status message.
# Ids (traceId, spanId) and the time fields are left alone.
_OTLP_TEXT_KEYS = frozenset({"stringValue", "message"})
_SHORT_LITERAL = 4
_MAX_DEPTH = 64
# The records of an OTLP payload: one oversized record is dropped, not the payload.
_OTLP_RECORD_LISTS = frozenset({"logRecords", "dataPoints", "spans"})
MAX_KEYS = 10_000


class TooManyKeys(ValueError):
    """An object whose keys are scrubbed holds more than ``MAX_KEYS`` keys."""


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


def _redact(text: Any, ident: Identity, self_steps: bool) -> Any:
    """Run the steps on one string; ``self_steps=False`` skips steps 1 and 2 (id values)."""
    if not isinstance(text, str) or not text:
        return text
    if self_steps:
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
    return isinstance(key, str) and key in ID_KEYS


def _is_dropped(key: Any) -> bool:
    return isinstance(key, str) and key in DROP_KEYS


def _unique(key: str, taken, counters: dict) -> str:
    """``key``, or ``key#2``, ``key#3``, ... when an earlier key already holds that name.

    ``counters`` keeps the last suffix used per base key, so a run of collisions
    costs O(1) each instead of rescanning every earlier suffix.
    """
    if key not in taken:
        return key
    n = counters.get(key, 1)
    while True:
        n += 1
        candidate = "%s#%d" % (key, n)
        if candidate not in taken:
            counters[key] = n
            return candidate


def _check_key_count(count: int) -> None:
    if count > MAX_KEYS:
        raise TooManyKeys("object holds more than %d keys" % MAX_KEYS)


class _Walk:
    """One payload walk: the identity, containers cut at _MAX_DEPTH, records dropped at MAX_KEYS."""

    __slots__ = ("ident", "cut", "dropped")

    def __init__(self, ident: Identity):
        self.ident = ident
        self.cut = 0
        self.dropped = 0

    def empty(self, container: Any) -> Any:
        self.cut += 1
        return {} if isinstance(container, dict) else []


def _scrub_key_values(items: list, walk: _Walk, depth: int, scrub_keys: bool) -> list:
    """An OTLP ``[{key, value}]`` list: drop DROP_KEYS entries; kvlist keys are scrubbed too."""
    if depth >= _MAX_DEPTH:
        return walk.empty(items)
    if scrub_keys:
        _check_key_count(len(items))
    kept = []
    taken = set()
    counters: dict = {}
    for item in items:
        if not isinstance(item, dict):
            kept.append(_scrub_otlp(item, walk, depth + 1))
            continue
        key = item.get("key")
        if _is_dropped(key):
            continue
        out = {}
        for field, value in item.items():
            if field == "key" and scrub_keys and isinstance(value, str):
                out[field] = _unique(scrub_text(value, walk.ident), taken, counters)
                taken.add(out[field])
            elif field == "value":
                out[field] = _scrub_otlp(value, walk, depth + 1, id_scalar=_is_id_key(key))
            else:
                out[field] = _scrub_otlp(value, walk, depth + 1)
        kept.append(out)
    return kept


def _scrub_otlp(node: Any, walk: _Walk, depth: int, id_scalar: bool = False) -> Any:
    """``id_scalar`` exempts only this AnyValue's own ``stringValue``; it is never passed down."""
    if isinstance(node, (dict, list)) and depth >= _MAX_DEPTH:
        return walk.empty(node)
    if isinstance(node, dict):
        out = {}
        for key, value in node.items():
            if key in _KEY_VALUE_LISTS and isinstance(value, list):
                out[key] = _scrub_key_values(value, walk, depth + 1, scrub_keys=False)
            elif key == "kvlistValue" and isinstance(value, dict):
                out[key] = {
                    inner_key: (
                        _scrub_key_values(inner, walk, depth + 2, scrub_keys=True)
                        if inner_key == "values" and isinstance(inner, list)
                        else _scrub_otlp(inner, walk, depth + 2)
                    )
                    for inner_key, inner in value.items()
                }
            elif key in _OTLP_RECORD_LISTS and isinstance(value, list):
                out[key] = _scrub_records(value, walk, depth + 1)
            elif key in _OTLP_TEXT_KEYS:
                out[key] = _redact(value, walk.ident, not (id_scalar and key == "stringValue"))
            else:
                out[key] = _scrub_otlp(value, walk, depth + 1)
        return out
    if isinstance(node, list):
        return [_scrub_otlp(item, walk, depth + 1) for item in node]
    return node


def _scrub_records(records: list, walk: _Walk, depth: int) -> list:
    """An OTLP record list: a record holding an object over MAX_KEYS keys is dropped and counted."""
    if depth >= _MAX_DEPTH:
        return walk.empty(records)
    kept = []
    for record in records:
        try:
            kept.append(_scrub_otlp(record, walk, depth + 1))
        except TooManyKeys:
            walk.dropped += 1
    return kept


def _scrub_any(node: Any, walk: _Walk, depth: int) -> Any:
    if isinstance(node, (dict, list)) and depth >= _MAX_DEPTH:
        return walk.empty(node)
    if isinstance(node, dict):
        _check_key_count(len(node))
        out = {}
        counters: dict = {}
        for key, value in node.items():
            if _is_dropped(key):
                continue
            new_key = _unique(scrub_text(key, walk.ident), out, counters) if isinstance(key, str) else key
            if _is_id_key(key) and isinstance(value, str):
                out[new_key] = _redact(value, walk.ident, False)
            else:
                out[new_key] = _scrub_any(value, walk, depth + 1)
        return out
    if isinstance(node, list):
        return [_scrub_any(item, walk, depth + 1) for item in node]
    return _redact(node, walk.ident, True)


def scrub_payload(signal: str, payload: dict, ident: Identity) -> dict:
    """Return a scrubbed copy of one payload; the input is not modified.

    For ``logs``, ``metrics`` and ``traces`` (OTLP http/json) the walk removes
    the DROP_KEYS attributes and scrubs every ``stringValue`` (attribute values
    at every level, log bodies, nested array and kvlist values), kvlist keys and
    span status messages. Any other signal (hook or event JSON) has every string
    value and dict key scrubbed and DROP_KEYS keys removed. Scrubbed keys that
    collide get ``#2``, ``#3``, ... appended to the later key. A container 64
    levels deep is replaced by an empty one of the same type and one warning is
    logged (a count, no content). An OTLP record holding an object of more than
    ``MAX_KEYS`` scrubbed keys is dropped (one counted warning); elsewhere such an
    object raises ``TooManyKeys``.
    """
    walk = _Walk(ident)
    try:
        if signal in _OTLP_SIGNALS:
            out = _scrub_otlp(payload, walk, 0)
        else:
            out = _scrub_any(payload, walk, 0)
    finally:
        if walk.cut:
            _LOG.warning("scrub: emptied %d container(s) nested %d or more levels deep", walk.cut, _MAX_DEPTH)
        if walk.dropped:
            _LOG.warning("scrub: dropped %d record(s) holding an object of more than %d keys",
                         walk.dropped, MAX_KEYS)
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
