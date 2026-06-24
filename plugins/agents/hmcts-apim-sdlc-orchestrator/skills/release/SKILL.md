---
name: release
description: Use when cutting a new GitHub release for an APIM service — finds PRs merged since the last tag, filters out dependencies, chores and docs, computes the next version, and creates the release with a functional changelog.
---

# Skill: Release

## Trigger

Invoke this skill when a user asks to:
- Create a new release
- Cut a release
- Tag and release the service
- Publish a new version

Invocation command: `/release`

---

## Process

### Step 1 — Get the last release tag

```bash
gh release list --limit 1 --json tagName,publishedAt,name
```

Extract:
- `tagName` — current version (e.g. `v1.2.4`)
- `publishedAt` — ISO timestamp used to filter PRs

Tell the user: *"Last release: `<tagName>` published on `<date>`."*

### Step 2 — Compute the next version

Default: **increment the patch number.**

| Current | Next (default) |
|---|---|
| `v1.2.4` | `v1.2.5` |
| `v2.0.0` | `v2.0.1` |

Override only if the user explicitly states:
- `minor` → `v1.2.4` → `v1.3.0`
- `major` → `v1.2.4` → `v2.0.0`

### Step 3 — Collect PRs merged since last release

```bash
gh pr list --state merged --limit 50 \
  --json number,title,mergedAt,author,body \
  --jq '.[] | select(.mergedAt > "<publishedAt>") | {number: .number, title: .title, author: .author.login, body: .body}'
```

### Step 4 — Filter and categorise

**Exclude entirely — do not mention in release notes:**
- Author is `app/dependabot` or `app/renovate`
- Title starts with `chore:`, `chore(deps):`, `docs:`, `ci:`
- Title matches pattern `bump <X> from <Y> to <Z>`
- PR configures or migrates dependency management tooling (e.g. Renovate → Dependabot, auto-merge workflow setup)

**Categorise what remains:**

| Category | Title signals |
|---|---|
| **Bug Fixes** | `fix:`, `bugfix:`, `AMP-NNN bugfix:` |
| **New Features** | `feat:`, `feature:`, `AMP-NNN Add` |
| **Improvements** | `perf:`, `refactor:`, `chore(AMP-` with JIRA ticket, `Decommission`, `Switch`, `Replace` |
| **Other Changes** | Anything else functional |

### Step 5 — Generate release notes

For each included PR:
1. Read the `## What changed` section from the PR body
2. Read the `## Why it's needed` section from the PR body
3. Write a **plain-English summary** of what the change does and why it matters — one short paragraph per PR

Do not copy raw PR titles. Do not bullet-point the `## What changed` list verbatim. Synthesise into a readable changelog entry.

**Format:**

```markdown
## What's changed in <version>

### New Features
**#<N> — <Plain English summary: what the feature does and why it was added>**

### Bug Fixes
**#<N> — <Plain English summary: what was broken and what the fix does>**

### Improvements
**#<N> — <Plain English summary: what improved and the benefit>**
```

Omit any section that has no entries.

### Step 6 — Confirm with user

Present a summary before creating anything:

```
Next version:  v1.2.5
Included PRs:  N (functional changes)
Excluded PRs:  M (dependabot: X, chore: Y, docs: Z)

Draft release notes:
---
<draft>
---

Shall I create the release?
```

**Wait for the user to confirm.** Do not create the release until they say yes.

### Step 7 — Create the release

```bash
gh release create <version> \
  --title "<version> — <one-line summary of the most significant change>" \
  --notes "$(cat <<'EOF'
<release notes>
EOF
)"
```

After creation, print the release URL.

---

## Rules

- **Always confirm** the version, PR list, and draft notes with the user before creating the release.
- **Never include** dependabot, renovate, chore, or docs PRs in the release notes — not even as a footnote.
- **Default is patch bump.** Only change minor or major if the user explicitly says so.
- **Use the PR body** (`## What changed` / `## Why it's needed`) for summaries — not just the PR title.
- **No code commits.** This skill creates a release only — it does not stage, commit, or push anything.
- If there are **no functional PRs** since the last release, tell the user: *"No functional changes found since `<tag>`. Nothing to release."*
- If `gh` CLI is not authenticated, tell the user: *"Run `gh auth login` first."*

---

## Example output format

The content below is generated dynamically at runtime from the actual merged PR bodies
(`## What changed` and `## Why it's needed` sections). Nothing is hardcoded — every
entry reflects the real PRs merged since the last tag in the repo you run `/release` from.

**Confirmation prompt shown to engineer:**
```
Last release:  v<X.Y.Z> (<date>)
Next version:  v<X.Y.Z+1>
Included PRs:  N (functional changes)
Excluded PRs:  M (dependabot: A, chore: B, docs: C)

Draft release notes:
---
## What's changed in v<X.Y.Z+1>

### New Features
**#<N> — <Plain-English summary synthesised from PR body: what the feature does and why it was added>**

### Bug Fixes
**#<N> — <Plain-English summary synthesised from PR body: what was broken and what the fix does>**

### Improvements
**#<N> — <Plain-English summary synthesised from PR body: what improved and the benefit>**
---

Shall I create the release?
```

**Release title format:**
```
v<X.Y.Z+1> — <One-line summary of the most significant change in this release>
```