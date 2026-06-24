---
name: bootstrap-context
description: Bootstrap the gitignored .claude/CLAUDE.md for any api-cp-* or service-cp-* repo with three @import lines pointing to hmcts-apim-sdlc-orchestrator context standards. Runs automatically on every session start via the SessionStart hook — invoke manually only to force an update.
---

# Skill: Bootstrap Context

> **Automatic:** The `SessionStart` hook (`hooks/bootstrap-context.sh`) runs this logic
> automatically whenever Claude Code opens in an `api-cp-*` or `service-cp-*` repo.
> Run `/bootstrap-context` manually only to force-update.

## Trigger

Invoke this skill when a user asks to:
- Bootstrap Claude context for this repo
- Wire Claude context for this repo
- Set up shared template imports for Claude
- Run `/bootstrap-context`
- Initialise `.claude/CLAUDE.md`

Invocation command: `/bootstrap-context`

---

## Process

### Step 1 — Identify the repo

```bash
REPO_NAME=$(basename "$PWD")
echo "Repo: $REPO_NAME"
```

### Step 2 — Detect repo type

- If `$REPO_NAME` starts with `api-cp-` → **API spec repo** → use `api-spec-shared.md`
- If `$REPO_NAME` starts with `service-cp-` → **Service repo** → use `service-shared.md`
- Otherwise → stop and tell the user: *"This skill only supports `api-cp-*` and `service-cp-*` repos. Current directory: `$REPO_NAME`."*

### Step 3 — Create `.claude/` directory if needed

```bash
mkdir -p .claude
```

### Step 4 — Write `.claude/CLAUDE.md`

Write exactly 3 lines. Paths are relative from `.claude/CLAUDE.md` — `../../agentic-plugins-marketplace/` navigates up to the workspace root and into the marketplace repo. This works on any machine where repos are cloned as siblings.

**For `api-cp-*` repos:**
```
@../../agentic-plugins-marketplace/plugins/agents/hmcts-apim-sdlc-orchestrator/context/shared-code-rules.md
@../../agentic-plugins-marketplace/plugins/agents/hmcts-apim-sdlc-orchestrator/context/api-spec-shared.md
@../../agentic-plugins-marketplace/plugins/agents/hmcts-apim-sdlc-orchestrator/context/claude-md-standards.md
```

**For `service-cp-*` repos:**
```
@../../agentic-plugins-marketplace/plugins/agents/hmcts-apim-sdlc-orchestrator/context/shared-code-rules.md
@../../agentic-plugins-marketplace/plugins/agents/hmcts-apim-sdlc-orchestrator/context/service-shared.md
@../../agentic-plugins-marketplace/plugins/agents/hmcts-apim-sdlc-orchestrator/context/claude-md-standards.md
```

Claude Code automatically reads both `CLAUDE.md` (repo root, committed) and `.claude/CLAUDE.md` (gitignored) on every session. No explicit import of `CLAUDE.md` is needed — it is loaded natively.

### Step 5 — Ensure `.claude/CLAUDE.md` is gitignored

Check if `.gitignore` already contains `.claude/CLAUDE.md`:

```bash
grep -q "\.claude/CLAUDE\.md" .gitignore 2>/dev/null && echo "already ignored" || echo "missing"
```

- If **missing**: append `.claude/CLAUDE.md` to `.gitignore`

```bash
echo ".claude/CLAUDE.md" >> .gitignore
```

- If **already ignored**: do nothing.

Note: `.claude/settings.local.json` and the root `CLAUDE.md` must remain committed — do **not** add `.claude/` (the whole directory) to `.gitignore`, only `.claude/CLAUDE.md`.

### Step 6 — Confirm

Tell the user:

> ✓ `.claude/CLAUDE.md` bootstrapped for `<REPO_NAME>` (gitignored).
>
> On every Claude Code session, Claude loads:
> - `CLAUDE.md` (this repo) — repo-specific context, committed here
> - `hmcts-apim-sdlc-orchestrator/context/shared-code-rules.md` — team-wide code rules
> - `hmcts-apim-sdlc-orchestrator/context/api-spec-shared.md` (or `service-shared.md`) — repo-category standards
> - `hmcts-apim-sdlc-orchestrator/context/claude-md-standards.md` — HMCTS guidance for generating `CLAUDE.md`
>
> **This will also happen automatically on every future session start** — the `SessionStart`
> hook in `hmcts-apim-sdlc-orchestrator` creates or verifies `.claude/CLAUDE.md` before
> Claude reads any prompt.
>
> **Next step:** run `/init` to generate (or refresh) the committed `CLAUDE.md` for this repo.
> `/init` will use the HMCTS standards now in context to produce a compliant, non-duplicating file.
>
> When shared standards change in `hmcts-apim-sdlc-orchestrator`, this repo picks them up automatically — no further action needed.

---

## Rules

- **Never commit `.claude/CLAUDE.md`** — it is a local developer file; only gitignore it, never stage it.
- **Do not touch `.claude/settings.local.json`** — that file is separate and is committed.
- **Do not touch root `CLAUDE.md`** — that file is committed and owned by this repo; use `/init` to generate or refresh it.
- **Paths are relative** from `.claude/CLAUDE.md` — `../../agentic-plugins-marketplace/` navigates up to the workspace root. This works on any machine where repos are cloned as siblings under the same workspace root.
- **Idempotent** — re-running this skill overwrites `.claude/CLAUDE.md` safely with the same content.
