"""Manifests, README, validator check and a literal scan of the plugin tree (Task 9)."""
import importlib.util
import json
import re
import subprocess
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
REPO = PLUGIN_ROOT.parent.parent.parent
PLUGIN_NAME = "hmcts-sdlc-orchestrator"
VERSION = "1.1.0"

ONBOARDING_LINE = (
    'prev=$(git config --global --get core.hooksPath); '
    '[ "$prev" != "$HOME/.cpp-harness/git-hooks" ] && git config --global cpp.previousHooksPath "$prev"; '
    'git config --global core.hooksPath ~/.cpp-harness/git-hooks'
)

# The invented identities the tests use; every other GUID must repeat one character.
INVENTED_GUIDS = {
    "00000000-0000-0000-0000-000000000001",
    "00000000-0000-0000-0000-000000000002",
    "00000000-0000-0000-0000-000000000003",
}
INVENTED_TENANT = "00000000-0000-0000-0000-000000000001"
ALLOWED_DOMAIN = "example.invalid"

# Needles are assembled from fragments so this file does not match itself.
FORBIDDEN_SUBSTRINGS = ("cjscp" + ".org" + ".uk", "azurecr" + ".io")
LOGIN_HOST = "login.microsoft" + "online.com/"
JWT_RE = re.compile("ey" + "J[A-Za-z0-9_-]{20,}")
GUID_RE = re.compile(r"(?<![0-9A-Fa-f-])[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}(?![0-9A-Fa-f-])")
DOMAIN_AFTER_AT_RE = re.compile(r"@((?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,})")
REGEX_DEFINITION_FILE = "scrub.py"


def _plugin_manifest():
    return json.loads((PLUGIN_ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))


def _marketplace_entry():
    marketplace = json.loads((REPO / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
    return next(entry for entry in marketplace["plugins"] if entry["name"] == PLUGIN_NAME)


def _readme():
    return (PLUGIN_ROOT / "README.md").read_text(encoding="utf-8")


def _telemetry_section(readme):
    start = readme.index("\n## Telemetry\n")
    end = readme.find("\n## ", start + 1)
    return readme[start:] if end == -1 else readme[start:end]


def _load_validator(monkeypatch):
    spec = importlib.util.spec_from_file_location("validate_marketplace_under_test",
                                                  str(REPO / "scripts" / "validate_marketplace.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "errors", [])
    monkeypatch.setattr(module, "warnings", [])
    return module


def test_versions_match_1_1_0():
    manifest = _plugin_manifest()
    entry = _marketplace_entry()
    assert manifest["version"] == VERSION
    assert entry["version"] == VERSION
    assert manifest["description"].endswith(", and session telemetry (opt-out, /telemetry).")
    assert entry["description"].endswith(", session telemetry (opt-out, /telemetry).")
    row = next(line for line in (REPO / "CATALOG.md").read_text(encoding="utf-8").splitlines()
               if line.startswith("| [" + PLUGIN_NAME + "]"))
    assert "telemetry" in row
    assert "`/telemetry`" in row


def test_readme_has_telemetry_section_and_no_gate():
    readme = _readme()
    section = _telemetry_section(readme)
    for needle in (
        "prompts", "replies", "tool inputs and outputs", "cost and tokens", "hook and git events",
        "scrubbed on your laptop", "30 days", "acknowledges",
        "the CPP-internal telemetry ingest configured by the programme "
        "(sign in with your Entra account: `/telemetry login`)",
        "`CPP_HARNESS_TELEMETRY=off`", "`/telemetry optout`", "`/telemetry status`",
        "`/telemetry uninstall`", ONBOARDING_LINE,
        "every git hook in every repository", "`.git/hooks`", "Husky v9",
        "Local override", "`override.json`", "never commit",
        # What the per-session switch does, and what it does not.
        "removes the telemetry keys from your Claude Code settings and stops a running forwarder",
        "It does not opt you out", "at its own next start", "`/telemetry optout` is the lasting opt-out",
    ):
        assert needle in section, needle
    for key in ("ingest_url", "tenant_id", "client_id", "api_app_id", "auth_base_url", "port"):
        assert "`{}`".format(key) in section, key
    # The onboarding line must never copy our own directory into cpp.previousHooksPath.
    assert 'cpp.previousHooksPath "$(git config' not in section
    # No hostname or URL: the section names the ingest generically.
    assert "://" not in section
    for path in (PLUGIN_ROOT / "README.md", PLUGIN_ROOT / ".claude-plugin" / "plugin.json", PLUGIN_ROOT / "CLAUDE.md"):
        assert "/gate" not in path.read_text(encoding="utf-8"), path.name


def test_validator_check_hook_timeouts_passes_on_this_tree(monkeypatch):
    validator = _load_validator(monkeypatch)
    validator.check_hook_timeouts()
    assert validator.errors == []


def _command(name, **extra):
    return dict({"type": "command", "command": "${CLAUDE_PLUGIN_ROOT}/" + name}, **extra)


def _write_hooks(plugin_dir, events):
    (plugin_dir / "hooks").mkdir(parents=True)
    (plugin_dir / "hooks" / "hooks.json").write_text(json.dumps({"hooks": events}), encoding="utf-8")


def _flagged(messages):
    return sorted(re.search(r"\$\{CLAUDE_PLUGIN_ROOT\}/(\S+?)'", message).group(1) for message in messages)


def test_validator_check_hook_timeouts_flags_a_missing_or_non_integer_timeout(monkeypatch, tmp_path):
    validator = _load_validator(monkeypatch)
    _write_hooks(tmp_path / "plugins" / "agents" / PLUGIN_NAME, {
        "SessionStart": [{"hooks": [_command("start.sh")]}],
        "Stop": [{"hooks": [_command("stop.sh", timeout="5")]}],
        "SubagentStop": [{"hooks": [_command("sub.sh", timeout=True)]}],
        "SessionEnd": [{"hooks": [_command("end.sh", timeout=5), _command("late.sh", timeout=2.5)]}],
        "PreToolUse": [{"matcher": "Bash", "hooks": [_command("guard.sh")]}],
    })
    monkeypatch.setattr(validator, "REPO", tmp_path)
    monkeypatch.setattr(validator, "PLUGINS_DIR", tmp_path / "plugins")

    validator.check_hook_timeouts()

    assert _flagged(validator.errors) == ["late.sh", "start.sh", "stop.sh", "sub.sh"]
    assert all("plugins/agents/{}/hooks/hooks.json".format(PLUGIN_NAME) in error for error in validator.errors)
    assert validator.warnings == []


def test_validator_check_hook_timeouts_only_warns_for_other_plugins(monkeypatch, tmp_path):
    validator = _load_validator(monkeypatch)
    other = tmp_path / "plugins" / "hooks" / "other"
    (other / ".claude-plugin").mkdir(parents=True)
    (other / ".claude-plugin" / "plugin.json").write_text(json.dumps({"name": "other"}), encoding="utf-8")
    _write_hooks(other, {"Stop": [{"hooks": [_command("notify.sh")]}]})
    # A directory named like ours does not borrow our strictness when its manifest names another plugin.
    lookalike = tmp_path / "plugins" / "agents" / "copy" / PLUGIN_NAME
    (lookalike / ".claude-plugin").mkdir(parents=True)
    (lookalike / ".claude-plugin" / "plugin.json").write_text(json.dumps({"name": "copy"}), encoding="utf-8")
    _write_hooks(lookalike, {"SessionEnd": [{"hooks": [_command("end.sh")]}]})
    monkeypatch.setattr(validator, "REPO", tmp_path)
    monkeypatch.setattr(validator, "PLUGINS_DIR", tmp_path / "plugins")

    validator.check_hook_timeouts()

    assert validator.errors == []
    assert _flagged(validator.warnings) == ["end.sh", "notify.sh"]


def test_validator_runs_the_hook_timeout_check(monkeypatch, capsys):
    validator = _load_validator(monkeypatch)
    called = []
    for name in dir(validator):
        if name.startswith("check_"):
            monkeypatch.setattr(validator, name, lambda *args, _name=name: called.append(_name))
    assert validator.main() == 0
    assert "check_hook_timeouts" in called
    assert len(called) == len(set(called)) == 9
    assert "all 9 checks passed" in capsys.readouterr().out


def _plugin_files():
    """The files git tracks under the plugin root (the committed tree, never local leftovers)."""
    listed = subprocess.run(["git", "ls-files", "-z"], cwd=str(PLUGIN_ROOT), capture_output=True, check=True).stdout
    for name in sorted(item for item in listed.decode("utf-8").split("\0") if item):
        path = PLUGIN_ROOT / name
        if path.is_file():
            yield path


def _is_decorator(path, line, at):
    return path.suffix == ".py" and line[:at].strip() == ""


_STRING_LITERAL_RE = re.compile(r"""(?P<q>["'])(?P<body>(?:\\.|(?!(?P=q)).)*)(?P=q)""")
_REGEX_METACHARACTERS = set("[](){}*+?|\\^$")


def _is_pattern(body):
    if not _REGEX_METACHARACTERS & set(body):
        return False
    try:
        re.compile(body)
    except re.error:
        return False
    return True


def _without_regex_definitions(path, line):
    """In scrub.py, blank the string literals that compile as regex patterns; a plain literal is still scanned."""
    if path.name != REGEX_DEFINITION_FILE:
        return line
    return _STRING_LITERAL_RE.sub(
        lambda match: match.group("q") * 2 if _is_pattern(match.group("body")) else match.group(0), line)


def _line_violations(path, line):
    line = _without_regex_definitions(path, line)
    lowered = line.lower()
    for needle in FORBIDDEN_SUBSTRINGS:
        if needle in lowered:
            yield "forbidden host " + needle
    for match in DOMAIN_AFTER_AT_RE.finditer(line):
        domain = match.group(1).lower()
        if domain == ALLOWED_DOMAIN or domain.endswith("." + ALLOWED_DOMAIN):
            continue
        if _is_decorator(path, line, match.start()):
            continue
        yield "address at a real-looking domain @" + domain
    start = lowered.find(LOGIN_HOST)
    while start != -1:
        tail = line[start + len(LOGIN_HOST):]
        if not (tail.startswith(INVENTED_TENANT) or tail.startswith("{")):
            yield "sign-in URL with a real tenant"
        start = lowered.find(LOGIN_HOST, start + 1)
    for match in GUID_RE.finditer(line):
        guid = match.group(0).lower()
        if guid in INVENTED_GUIDS or len(set(guid.replace("-", ""))) == 1:
            continue
        yield "GUID " + guid
    if JWT_RE.search(line):
        yield "token-shaped string"


def test_no_forbidden_literals_in_plugin_tree():
    violations = []
    scanned = 0
    for path in _plugin_files():
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue  # binary: no text literal to leak
        scanned += 1
        for number, line in enumerate(text.splitlines(), 1):
            for reason in _line_violations(path, line):
                violations.append("{}:{}: {}".format(path.relative_to(PLUGIN_ROOT), number, reason))
    assert scanned > 100
    assert violations == []


def test_the_literal_scan_catches_each_kind():
    markdown = PLUGIN_ROOT / "tests" / "sample.md"
    python = PLUGIN_ROOT / "tests" / "sample.py"
    samples = {
        "mail ops" + "@hmcts" + ".net": "address at a real-looking domain",
        "host x." + FORBIDDEN_SUBSTRINGS[0]: "forbidden host",
        "image y." + FORBIDDEN_SUBSTRINGS[1] + "/z": "forbidden host",
        "https://" + LOGIN_HOST + "contoso.onmicrosoft.com": "sign-in URL with a real tenant",
        "id 3f2b8c1e-9d4a-4e7b" + "-8a6c-1d2e3f4a5b6c": "GUID",
        "bearer " + "ey" + "J" + "a" * 24: "token-shaped string",
    }
    for line, reason in samples.items():
        assert any(found.startswith(reason) for found in _line_violations(markdown, line)), line
    clean = ("mail devuser@example.invalid", "id aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
             "https://" + LOGIN_HOST + INVENTED_TENANT, "/plugin install x@agentic-plugins-marketplace")
    for line in clean:
        assert list(_line_violations(markdown, line)) == [], line
    decorator = "    @" + "functools.lru_cache"
    assert list(_line_violations(python, decorator)) == []
    assert list(_line_violations(markdown, decorator)) != []
    assert list(_line_violations(python, "x = 1  # " + decorator.strip())) != []


def test_the_scrub_exemption_covers_only_regex_pattern_literals():
    scrub_py = PLUGIN_ROOT / "bin" / "cpp_telemetry" / REGEX_DEFINITION_FILE
    host = FORBIDDEN_SUBSTRINGS[0]
    exempt = ('_HOST = re.compile(r"(?:' + host + '|x)")', '        ("HOST", r"\\b(' + host + ')\\b"),')
    for line in exempt:
        assert list(_line_violations(scrub_py, line)) == [], line
    planted = (
        '        ("HOST", r"' + host + '"),',  # a plain literal on an r"..." line
        '_HOST = re.compile(r"[a-z]+")  # ' + host,  # a literal outside the pattern
        'URL = "https://x.' + host + '/"',
    )
    for line in planted:
        assert any(found.startswith("forbidden host") for found in _line_violations(scrub_py, line)), line
    # Elsewhere a pattern literal earns no exemption.
    assert list(_line_violations(PLUGIN_ROOT / "bin" / "x.py", exempt[0])) != []


def test_the_walk_reads_only_tracked_files():
    names = {path.relative_to(PLUGIN_ROOT).as_posix() for path in _plugin_files()}
    assert "README.md" in names and "tests/test_manifests.py" in names
    assert not any("__pycache__" in name for name in names)
