# Validation scripts

`validate_marketplace.py` runs the checks CI needs that Claude Code's built-in
`/plugin validate` does not cover: cross-file consistency between
`marketplace.json`, plugin manifests, `CATALOG.md`, and `.claude/settings.json`,
plus orphan-plugin detection, shellcheck on hook scripts, and version-bump
coherence.

## Local run

```bash
pip install pyyaml          # one-off
python scripts/validate_marketplace.py
```

Optional: `brew install shellcheck` (or `apt install shellcheck`) to enable the
hook-script lint — skipped with a warning if the binary is missing.

Exit code `0` means clean; `1` means one or more violations; `2` means the
script itself failed to run (missing dependency, unreadable `marketplace.json`,
etc.). Every violation is reported in a single run — no whack-a-mole.

## What each check covers

| # | Check | What it catches |
|---|---|---|
| 1 | Source paths | A `source` in `marketplace.json` that points at a non-existent directory. Claude Code resolves these lazily at install time, so a missing dir otherwise only surfaces when someone tries to install the plugin. |
| 2 | Manifest coherence | `name` or `version` drift between a plugin's `plugin.json` and its entry in `marketplace.json`. |
| 3 | Orphan plugins | Plugin directories that exist on disk but are not declared in `marketplace.json` (so can't be installed). |
| 4 | CATALOG coverage | A new plugin added to `marketplace.json` without a corresponding row in `CATALOG.md`. |
| 5 | `enabledPlugins` references | `.claude/settings.json` enabling a plugin by name that does not exist in `marketplace.json`. |
| 6 | Dangling skill references | A `SKILL.md` body that references another skill by name (`` `foo` skill``, `Task: foo`) where `foo` is not a real skill — this was the `openspec-sync-specs` bug class. Heuristic: only flags names that share a prefix with a known skill, to keep false positives low. |
| 7 | Hook script shellcheck | `shellcheck` on every `plugins/**/hooks/*.sh`. Skipped with a warning if `shellcheck` is not installed locally. |
| 8 | Version-bump coherence | If a `plugin.json` version changed in a PR but the corresponding `marketplace.json` entry did not. Only runs when `GITHUB_BASE_REF` is set (i.e. in PR CI). |

## What this script intentionally does NOT check

Anything that Claude Code already validates on `/plugin validate` or plugin
load: JSON validity, required fields in `plugin.json`, SKILL.md YAML
frontmatter parsing, `hooks.json` schema. CI duplicating those adds no value.

## Ordering rule with the claude-config repo

The `claude` config repo's validator fetches `main` of this repo and checks
that its `enabledPlugins` all resolve here. If a single change adds a plugin
to the marketplace and enables it in `claude` simultaneously, **land the
marketplace PR first** or the claude-repo CI will fail.
