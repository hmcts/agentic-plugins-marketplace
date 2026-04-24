#!/usr/bin/env python3
"""Validate the marketplace repo configuration.

Covers the checks Claude Code's built-in `/plugin validate` does NOT do:
cross-file consistency, orphan plugins, CATALOG coverage, dangling skill
references, and shellcheck on hook scripts.

Exits 1 if any check fails; all violations are reported in one run.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    print("error: PyYAML is required (pip install pyyaml)", file=sys.stderr)
    sys.exit(2)

REPO = Path(__file__).resolve().parent.parent
MARKETPLACE_JSON = REPO / ".claude-plugin" / "marketplace.json"
SETTINGS_JSON = REPO / ".claude" / "settings.json"
CATALOG_MD = REPO / "CATALOG.md"
PLUGINS_DIR = REPO / "plugins"
MARKETPLACE_SUFFIX = "@agentic-plugins-marketplace"

errors: list[str] = []
warnings: list[str] = []


def fail(msg: str) -> None:
    errors.append(msg)


def warn(msg: str) -> None:
    warnings.append(msg)


def load_marketplace() -> dict[str, Any]:
    return json.loads(MARKETPLACE_JSON.read_text())


def load_plugin_manifest(plugin_dir: Path) -> dict[str, Any] | None:
    manifest = plugin_dir / ".claude-plugin" / "plugin.json"
    if not manifest.exists():
        return None
    return json.loads(manifest.read_text())


def parse_frontmatter(md_path: Path) -> dict[str, Any] | None:
    text = md_path.read_text()
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---", 4)
    if end == -1:
        return None
    return yaml.safe_load(text[4:end]) or {}


def check_source_paths(mp: dict[str, Any]) -> None:
    """Check 1: every `source` path in marketplace.json resolves to a directory."""
    for entry in mp.get("plugins", []):
        source = entry.get("source")
        if not source:
            fail(f"plugin '{entry.get('name')}' missing `source` field")
            continue
        abs_path = (REPO / source.lstrip("./")).resolve()
        if not abs_path.is_dir():
            fail(f"plugin '{entry['name']}': source '{source}' is not a directory")


def check_plugin_manifest_coherence(mp: dict[str, Any]) -> None:
    """Check 2: plugin.json `name` and `version` match the marketplace.json entry."""
    for entry in mp.get("plugins", []):
        source = entry.get("source", "")
        plugin_dir = (REPO / source.lstrip("./")).resolve()
        if not plugin_dir.is_dir():
            continue  # covered by check 1
        manifest = load_plugin_manifest(plugin_dir)
        if manifest is None:
            fail(f"plugin '{entry['name']}': missing .claude-plugin/plugin.json")
            continue
        if manifest.get("name") != entry.get("name"):
            fail(
                f"plugin '{entry['name']}': plugin.json name "
                f"'{manifest.get('name')}' does not match marketplace.json entry"
            )
        if manifest.get("version") != entry.get("version"):
            fail(
                f"plugin '{entry['name']}': plugin.json version "
                f"'{manifest.get('version')}' does not match marketplace.json version "
                f"'{entry.get('version')}'"
            )


def check_orphan_plugins(mp: dict[str, Any]) -> None:
    """Check 3: every directory containing a plugin.json appears in marketplace.json."""
    declared = {
        (REPO / e["source"].lstrip("./")).resolve()
        for e in mp.get("plugins", [])
        if e.get("source")
    }
    for manifest in PLUGINS_DIR.rglob(".claude-plugin/plugin.json"):
        plugin_dir = manifest.parent.parent.resolve()
        if plugin_dir not in declared:
            rel = plugin_dir.relative_to(REPO)
            fail(f"orphan plugin at ./{rel} has no entry in marketplace.json")


def check_catalog_coverage(mp: dict[str, Any]) -> None:
    """Check 4: CATALOG.md references every plugin (by name or source path)."""
    if not CATALOG_MD.exists():
        fail("CATALOG.md is missing")
        return
    catalog = CATALOG_MD.read_text()
    for entry in mp.get("plugins", []):
        name = entry.get("name", "")
        source = entry.get("source", "").lstrip("./").rstrip("/")
        # Accept either a link to the source dir or the bare name in a list item/table cell
        patterns = [
            re.escape(source),
            rf"\[{re.escape(name)}\]",
            rf"\b{re.escape(name)}\b",
        ]
        if not any(re.search(p, catalog) for p in patterns):
            fail(f"CATALOG.md does not mention plugin '{name}' (source {source})")


def check_enabled_plugins(mp: dict[str, Any]) -> None:
    """Check 5: enabledPlugins with our suffix all resolve to a plugin in marketplace.json."""
    if not SETTINGS_JSON.exists():
        return
    settings = json.loads(SETTINGS_JSON.read_text())
    enabled = settings.get("enabledPlugins", {})
    names = {e.get("name") for e in mp.get("plugins", [])}
    for key in enabled:
        if not key.endswith(MARKETPLACE_SUFFIX):
            continue
        plugin_name = key[: -len(MARKETPLACE_SUFFIX)]
        if plugin_name not in names:
            fail(
                f".claude/settings.json enables '{key}' but no plugin of that name "
                f"is published in marketplace.json"
            )


# Heuristic patterns for dangling skill references.
# Match backticked kebab-case identifiers in skill-invocation contexts.
_TASK_REFERENCE = re.compile(r"\bTask:\s*[`\"]?([a-z][a-z0-9-]*-[a-z0-9-]+)\b")
_BACKTICK_SKILL = re.compile(
    r"`([a-z][a-z0-9-]*-[a-z0-9-]+)`\s+skill\b", re.IGNORECASE
)
_INVOKE_SKILL = re.compile(
    r"(?:invoke|use|run|call) the `([a-z][a-z0-9-]*-[a-z0-9-]+)` skill",
    re.IGNORECASE,
)


def check_dangling_references(mp: dict[str, Any]) -> None:
    """Check 6: SKILL.md bodies that reference other skills must reference real ones."""
    # Collect known skill trigger names from frontmatter.
    known: set[str] = set()
    for skill_md in PLUGINS_DIR.rglob("SKILL.md"):
        fm = parse_frontmatter(skill_md)
        if fm and "name" in fm:
            known.add(fm["name"])

    # Infer known prefixes so we only flag names that *look* like skills from this repo.
    prefixes = {n.split("-", 1)[0] for n in known if "-" in n}

    for skill_md in PLUGINS_DIR.rglob("SKILL.md"):
        text = skill_md.read_text()
        body_start = text.find("\n---", 4)
        body = text[body_start + 4 :] if body_start != -1 else text

        for pattern in (_TASK_REFERENCE, _BACKTICK_SKILL, _INVOKE_SKILL):
            for m in pattern.finditer(body):
                name = m.group(1)
                if name in known:
                    continue
                # Only flag names using a prefix we recognise as a skill namespace.
                prefix = name.split("-", 1)[0]
                if prefix in prefixes:
                    rel = skill_md.relative_to(REPO)
                    fail(
                        f"{rel}: references unknown skill '{name}' "
                        f"(matched pattern: {pattern.pattern!r})"
                    )


def check_hook_scripts() -> None:
    """Check 7: shellcheck on every hook script."""
    scripts = list(PLUGINS_DIR.rglob("hooks/*.sh"))
    if not scripts:
        return
    if shutil.which("shellcheck") is None:
        warn("shellcheck not installed — skipping hook script lint (install via apt/brew)")
        return
    for script in scripts:
        result = subprocess.run(
            ["shellcheck", "-f", "gcc", str(script)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            output = (result.stdout + result.stderr).strip()
            rel = script.relative_to(REPO)
            fail(f"shellcheck failed on {rel}:\n{output}")


def check_version_bumps(mp: dict[str, Any]) -> None:
    """Check 8: plugin.json version changes require matching marketplace.json bumps.

    Git diff–driven. Only runs in PR context (base ref available). Silent when no
    baseline is present.
    """
    base_ref = os.environ.get("GITHUB_BASE_REF")
    if not base_ref:
        return
    # `actions/checkout@v4` with default fetch-depth only has one commit; widen once.
    merge_base = subprocess.run(
        ["git", "merge-base", f"origin/{base_ref}", "HEAD"],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    if merge_base.returncode != 0:
        warn(
            f"version-bump check skipped: could not find merge-base with origin/{base_ref}"
        )
        return
    base_sha = merge_base.stdout.strip()

    def file_at(sha: str, path: str) -> str | None:
        result = subprocess.run(
            ["git", "show", f"{sha}:{path}"],
            cwd=REPO,
            capture_output=True,
            text=True,
        )
        return result.stdout if result.returncode == 0 else None

    mp_old_text = file_at(base_sha, ".claude-plugin/marketplace.json")
    mp_old = json.loads(mp_old_text) if mp_old_text else {"plugins": []}
    old_versions = {e["name"]: e.get("version") for e in mp_old.get("plugins", [])}

    for entry in mp.get("plugins", []):
        source = entry.get("source", "").lstrip("./")
        manifest_path = f"{source}/.claude-plugin/plugin.json"
        old_manifest_text = file_at(base_sha, manifest_path)
        if old_manifest_text is None:
            continue  # new plugin, no baseline
        old_manifest = json.loads(old_manifest_text)
        old_version = old_manifest.get("version")
        new_version = entry.get("version")
        if old_version != new_version and old_versions.get(entry["name"]) == old_version:
            fail(
                f"plugin '{entry['name']}': plugin.json version bumped "
                f"{old_version} → {new_version} but marketplace.json version unchanged"
            )


def main() -> int:
    try:
        mp = load_marketplace()
    except Exception as e:
        print(f"fatal: could not load marketplace.json: {e}", file=sys.stderr)
        return 2

    checks = [
        ("source paths", lambda: check_source_paths(mp)),
        ("plugin manifest coherence", lambda: check_plugin_manifest_coherence(mp)),
        ("orphan plugins", lambda: check_orphan_plugins(mp)),
        ("CATALOG coverage", lambda: check_catalog_coverage(mp)),
        ("enabledPlugins references", lambda: check_enabled_plugins(mp)),
        ("dangling skill references", lambda: check_dangling_references(mp)),
        ("hook script shellcheck", check_hook_scripts),
        ("version-bump coherence", lambda: check_version_bumps(mp)),
    ]

    for name, fn in checks:
        try:
            fn()
        except Exception as e:
            fail(f"check '{name}' crashed: {e}")

    if warnings:
        for w in warnings:
            print(f"warning: {w}", file=sys.stderr)

    if errors:
        print("", file=sys.stderr)
        print(f"{len(errors)} validation error(s):", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    print(f"all {len(checks)} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
