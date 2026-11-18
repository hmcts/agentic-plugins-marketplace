"""Manifests, README, validator check and a literal scan of the plugin tree (Task 9)."""
import importlib.util
import json
import re
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


def test_validator_check_hook_timeouts_flags_a_missing_or_non_integer_timeout(monkeypatch, tmp_path):
    validator = _load_validator(monkeypatch)
    hooks_dir = tmp_path / "plugins" / "hooks" / "sample" / "hooks"
    hooks_dir.mkdir(parents=True)

    def command(name, **extra):
        return dict({"type": "command", "command": "${CLAUDE_PLUGIN_ROOT}/" + name}, **extra)

    (hooks_dir / "hooks.json").write_text(json.dumps({"hooks": {
        "SessionStart": [{"hooks": [command("start.sh")]}],
        "Stop": [{"hooks": [command("stop.sh", timeout="5")]}],
        "SubagentStop": [{"hooks": [command("sub.sh", timeout=True)]}],
        "SessionEnd": [{"hooks": [command("end.sh", timeout=5), command("late.sh", timeout=2.5)]}],
        "PreToolUse": [{"matcher": "Bash", "hooks": [command("guard.sh")]}],
    }}), encoding="utf-8")
    monkeypatch.setattr(validator, "REPO", tmp_path)
    monkeypatch.setattr(validator, "PLUGINS_DIR", tmp_path / "plugins")

    validator.check_hook_timeouts()

    flagged = sorted(re.search(r"\$\{CLAUDE_PLUGIN_ROOT\}/(\S+?)'", error).group(1) for error in validator.errors)
    assert flagged == ["late.sh", "start.sh", "stop.sh", "sub.sh"]
    assert all("plugins/hooks/sample/hooks/hooks.json" in error for error in validator.errors)


def test_validator_runs_the_hook_timeout_check(monkeypatch):
    validator = _load_validator(monkeypatch)
    source = (REPO / "scripts" / "validate_marketplace.py").read_text(encoding="utf-8")
    assert '("lifecycle hook timeouts", check_hook_timeouts)' in source
    assert callable(validator.check_hook_timeouts)


def _plugin_files():
    for path in sorted(PLUGIN_ROOT.rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts:
            yield path


def _is_decorator(path, line, at):
    return path.suffix == ".py" and line[:at].strip() == ""


def _defines_regex(path, line):
    if path.name != REGEX_DEFINITION_FILE:
        return False
    stripped = line.strip()
    return "re.compile(" in stripped or re.match(r"""^(\("[^"]*",\s*)?r["']""", stripped) is not None


def _line_violations(path, line):
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
            violations.append("{}: not UTF-8 text".format(path.relative_to(PLUGIN_ROOT)))
            continue
        scanned += 1
        for number, line in enumerate(text.splitlines(), 1):
            if _defines_regex(path, line):
                continue
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
