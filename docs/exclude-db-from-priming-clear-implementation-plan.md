# Exclude DB From Priming Clear Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a new `exclude-db-from-priming-clear` skill to `hmcts-apim-sdlc-orchestrator` that detects a `service-cp-*`'s dedicated Postgres database and raises a PR against `hmcts/cpp-aks-ops` excluding it from the nonprod priming pipeline's `quick_clear` sweep; chain it automatically from `wire-service-deployment` so every future service is protected at onboarding time; then run it once, live, to fix the `pcr` data-wipe incident.

**Architecture:** One new skill file (markdown + embedded bash/python3, no compiled code) plus a small addition to an existing skill file. "Testing" here means structural validation (YAML frontmatter parses, required sections present — the same convention `docs/apim-template-and-catalog-implementation-plan.md` established) and the repo's own plugin-testing convention (`code-review:review`, `/reload-plugins`, `/doctor`). The final task is a real, live action (not a test) — it raises an actual PR against `cpp-aks-ops`.

**Tech Stack:** Markdown + YAML frontmatter (Claude Code skill format), `gh` CLI, `git`, Python 3, `jq`.

## Global Constraints

- Only touch the two database-discovery deny-lists inside the single `runQuickClear` task (`condition: eq('${{ parameters.quick_clear }}', true)`) in `aks_priming_deploy.yaml` — never `priming_enable`/`restore_dataset` logic.
- Never patch without a human-confirmed database name — local dev config (`docker-compose.yml`/`application.yaml`) can diverge from the deployed name (confirmed case: local `pcrdb` vs. deployed `pcr`).
- Never auto-merge the PR to `cpp-aks-ops` — shared ops repo outside this plugin's owned repos, always a human gate (same posture as `wire-service-deployment`'s PR to `cp-vp-aks-deploy`).
- Idempotent — skip patching if the database name is already in both deny-lists.
- No AI-attribution trailers or mentions in any commit message or PR body (`context/hmcts-standards.md`).
- Spec doc of record: `docs/exclude-db-from-priming-clear-design.md`.

---

### Task 1: Write the `exclude-db-from-priming-clear` skill

**Files:**
- Create: `plugins/agents/hmcts-apim-sdlc-orchestrator/skills/exclude-db-from-priming-clear/SKILL.md`

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces: a skill named `exclude-db-from-priming-clear`, invocable standalone and referenced by name from `wire-service-deployment` (Task 2).

- [x] **Step 1: Write the skill file**

```markdown
---
name: exclude-db-from-priming-clear
description: >
  Detects whether a service-cp-* repo owns a dedicated Postgres database and, if so,
  raises a PR against hmcts/cpp-aks-ops excluding that database from the nonprod
  priming pipeline's quick_clear sweep (aks_priming_deploy.yaml). quick_clear discovers
  every database on the shared Postgres flexible server by default and truncates all its
  tables except a small hardcoded system deny-list — any new service database is wiped
  until explicitly excluded. Idempotent — safe to invoke again if already excluded.
  Chained automatically from wire-service-deployment for new services; also invoked
  standalone to remediate an existing service after a data-loss incident.
---

# Skill: Exclude Database From Priming Quick-Clear

## When to invoke

- Chained automatically from `wire-service-deployment`'s Step 11, for any new
  `service-cp-*` that has just provisioned its own dedicated Postgres database.
- Standalone, for an existing `service-cp-*` whose database was swept by a
  `quick_clear` run and needs the same protection retroactively.

Invocation command: `/exclude-db-from-priming-clear`

## Background

`hmcts/cpp-aks-ops/aks_priming_deploy.yaml` runs a `quick_clear` job
(`condition: eq('${{ parameters.quick_clear }}', true)`) that discovers **every**
database on the shared nonprod Postgres flexible server — via
`az postgres flexible-server db list` (dev) or `SELECT datname FROM pg_database`
(non-dev) — and truncates all tables in each one, except a small hardcoded deny-list
of system databases: `template0`, `template1`, `postgres`, `repmgr`,
`azure_maintenance`, `azure_sys`, `hrds`, and any previously-excluded service databases.

Any new service database that appears on that server is swept by default. `hrds`
already being in the deny-list shows this "add the db name to the deny-list" fix
pattern is established precedent, not a new mechanism this skill invents.

This skill does **not** change that mechanism (see the design doc's rejected
alternative — flipping to an allow-list) — it only keeps the existing deny-list
current for every `service-cp-*`-owned database.

## Step 1 — Detect a dedicated database

Run from the root of the service-cp-* repo:

```bash
python3 - <<'EOF'
import re, os

candidate = None

if os.path.exists("docker-compose.yml"):
    with open("docker-compose.yml") as f:
        m = re.search(r"POSTGRES_DB:[ \t]*(\S+)", f.read())
        if m:
            candidate = m.group(1).strip()

if not candidate and os.path.exists("src/main/resources/application.yaml"):
    with open("src/main/resources/application.yaml") as f:
        text = f.read()
    m = re.search(
        r"datasource:\s*\n\s*url:\s*.*jdbc:postgresql://[^/]+/([a-zA-Z0-9_]+)",
        text,
    )
    if m:
        candidate = m.group(1)

print(f"DB_DETECTED:{candidate}" if candidate else "NO_DB_OWNED")
EOF
```

If `NO_DB_OWNED`: report *"This service has no dedicated database — nothing to
protect from priming quick_clear."* and exit.

## Step 2 — Confirm the real database name with a human

The candidate name comes from **local dev config only** (`docker-compose.yml` /
`application.yaml`). It can diverge from what is actually provisioned on the shared
nonprod Postgres server — confirmed case: `service-cp-crime-results-pcr`'s local
config uses `pcrdb`, but the deployed database that was actually wiped is named `pcr`.

Ask the user directly:

> "I detected a local dev database name of `<candidate>` for this service. Before I
> raise a PR to `cpp-aks-ops`, please confirm the actual database name provisioned on
> the shared nonprod Postgres server (dev/ste/sit) — it may not match the local name."

Do not proceed to Step 3 without an explicit confirmed name from the user. Never
write the unconfirmed local candidate into the PR.

Validate the confirmed name before using it anywhere below — it must be a
plausible Postgres identifier, not arbitrary text:

```bash
DB_NAME=$(cat <<'NAME_EOF'
<confirmed name from Step 2>
NAME_EOF
)
if ! [[ "$DB_NAME" =~ ^[a-z0-9_]+$ ]]; then
  echo "REJECTED: '$DB_NAME' is not a valid Postgres identifier (lowercase letters, digits, underscore only) — ask the user to confirm again."
  exit 1
fi
```

Each step below re-declares `DB_NAME` at the top of its own commands —
do not assume shell state (exported variables) persists between separate
tool invocations of different steps.

## Step 3 — Idempotency check

```bash
if [ -d /tmp/cpp-aks-ops ]; then
  git -C /tmp/cpp-aks-ops fetch origin
  git -C /tmp/cpp-aks-ops checkout -B priming-exclusion-work origin/HEAD
else
  gh repo clone hmcts/cpp-aks-ops /tmp/cpp-aks-ops
  git -C /tmp/cpp-aks-ops checkout -B priming-exclusion-work origin/HEAD
fi
```

```bash
DB_NAME=$(cat <<'NAME_EOF'
<confirmed name from Step 2, validated above>
NAME_EOF
)
[[ "$DB_NAME" =~ ^[a-z0-9_]+$ ]] || { echo "REJECTED: invalid DB_NAME"; exit 1; }
if grep -q "!= \"$DB_NAME\"" /tmp/cpp-aks-ops/aks_priming_deploy.yaml \
   && grep -q "'$DB_NAME'" /tmp/cpp-aks-ops/aks_priming_deploy.yaml; then
  echo "ALREADY_EXCLUDED"
else
  echo "NEEDS_PATCH"
fi
```

If `ALREADY_EXCLUDED`: report *"`$DB_NAME` is already excluded from quick_clear.
Nothing to do."* and exit.

## Step 4 — Patch both deny-lists

Both edits are inside the single `runQuickClear` task
(`condition: eq('${{ parameters.quick_clear }}', true)`) — nothing in
`priming_enable`/`restore_dataset` logic is touched.

```bash
DB_NAME=$(cat <<'NAME_EOF'
<confirmed name from Step 2, validated above>
NAME_EOF
)
[[ "$DB_NAME" =~ ^[a-z0-9_]+$ ]] || { echo "REJECTED: invalid DB_NAME"; exit 1; }
export DB_NAME
python3 - <<'EOF'
import os

path = "/tmp/cpp-aks-ops/aks_priming_deploy.yaml"
db_name = os.environ["DB_NAME"]

with open(path) as f:
    text = f.read()

jq_old = 'and . != "hrds"'
jq_new = f'and . != "hrds" and . != "{db_name}"'
assert jq_old in text, "jq deny-list anchor not found — file may have changed upstream"
assert text.count(jq_old) == 1, "jq deny-list anchor appears more than once — ambiguous patch target"
text = text.replace(jq_old, jq_new, 1)

sql_old = "'azure_sys', 'hrds'"
sql_new = f"'azure_sys', 'hrds', '{db_name}'"
assert sql_old in text, "psql NOT IN anchor not found — file may have changed upstream"
assert text.count(sql_old) == 1, "psql NOT IN anchor appears more than once — ambiguous patch target"
text = text.replace(sql_old, sql_new, 1)

with open(path, "w") as f:
    f.write(text)

print("PATCHED")
EOF
```

If either `assert` fails, **stop** — the upstream file has changed shape since this
skill was written. Report the mismatch to the user rather than patching blind.

## Step 5 — Raise a PR against `cpp-aks-ops`

Check for an existing open PR first:

```bash
DB_NAME=$(cat <<'NAME_EOF'
<confirmed name from Step 2, validated above>
NAME_EOF
)
[[ "$DB_NAME" =~ ^[a-z0-9_]+$ ]] || { echo "REJECTED: invalid DB_NAME"; exit 1; }
gh pr list --repo hmcts/cpp-aks-ops --head "chore/exclude-$DB_NAME-from-priming-quick-clear" --state open
```

If an open PR is found, report its URL to the user and stop — do not raise a duplicate.

If none exists:

```bash
DB_NAME=$(cat <<'NAME_EOF'
<confirmed name from Step 2, validated above>
NAME_EOF
)
[[ "$DB_NAME" =~ ^[a-z0-9_]+$ ]] || { echo "REJECTED: invalid DB_NAME"; exit 1; }
cd /tmp/cpp-aks-ops
BRANCH="chore/exclude-$DB_NAME-from-priming-quick-clear"
git checkout -B "$BRANCH"
git add aks_priming_deploy.yaml
git commit -m "chore(priming): exclude $DB_NAME from quick_clear sweep

$DB_NAME is a dedicated service-owned Postgres database (service-cp-*),
not a legacy shared schema. quick_clear discovers every database on the
server by default (system deny-list only) and truncates all its tables,
which wiped $DB_NAME during a routine priming run. Adds it to both
discovery deny-lists (dev az-cli path and non-dev psql path), following
the same pattern already used for hrds."
git push -u origin "$BRANCH"

gh pr create \
  --repo hmcts/cpp-aks-ops \
  --title "chore(priming): exclude $DB_NAME from quick_clear sweep" \
  --body "$(cat <<BODY
## Summary

Excludes the \`$DB_NAME\` database from the priming pipeline's \`quick_clear\`
step. \`quick_clear\` enumerates every database on the shared nonprod Postgres
server and truncates all its tables except a small system deny-list
(\`template0\`, \`template1\`, \`postgres\`, \`repmgr\`, \`azure_maintenance\`,
\`azure_sys\`, \`hrds\`, and any previously-excluded service databases). \`$DB_NAME\` is owned by a service-cp-* Spring Boot
service with its own dedicated datastore, not a legacy shared schema, and
should not be swept by this job.

## Change

Adds \`$DB_NAME\` to both database-discovery deny-lists inside the
quick_clear-gated task only — no change to \`priming_enable\` or
\`restore_dataset\` behaviour.

## Verification needed before merge

- [ ] Confirm \`$DB_NAME\` is the correct database name in every environment
      this pipeline targets (dev/ste/sit) — instance naming can vary per
      environment.
BODY
)"
```

Never auto-merge. Report the PR URL to the user and stop — a human on the
`cpp-aks-ops` side must review and merge.

## Rules

- **Never patch without a human-confirmed database name** (Step 2) — local dev
  config can diverge from the deployed name.
- **Never auto-merge the PR.** `cpp-aks-ops` is a shared ops repo outside this
  plugin's owned repos — always a human gate, same posture as
  `wire-service-deployment`'s PR to `cp-vp-aks-deploy`.
- **Only touch the two deny-lists inside the `quick_clear`-gated task.** Never
  edit `priming_enable`/`restore_dataset` logic.
- **Idempotent** — check both deny-lists (Step 3) before patching; skip if the
  name is already present in both.
- If `gh repo clone`/`git push` fails on permissions, tell the user directly
  rather than silently failing.
- If either `assert` in Step 4 fails, stop and report — do not attempt a
  fuzzy/partial patch.
```

- [x] **Step 2: Verify the frontmatter parses and required sections exist**

```bash
python3 - <<'EOF'
import yaml, re

path = "plugins/agents/hmcts-apim-sdlc-orchestrator/skills/exclude-db-from-priming-clear/SKILL.md"
with open(path) as f:
    text = f.read()

m = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
assert m, "no YAML frontmatter found"
front = yaml.safe_load(m.group(1))
assert front["name"] == "exclude-db-from-priming-clear", front
assert "description" in front and len(front["description"]) > 20

for required in [
    "## When to invoke",
    "## Background",
    "## Step 1 — Detect a dedicated database",
    "## Step 2 — Confirm the real database name with a human",
    "## Step 3 — Idempotency check",
    "## Step 4 — Patch both deny-lists",
    "## Step 5 — Raise a PR against `cpp-aks-ops`",
    "## Rules",
]:
    assert required in text, f"missing section: {required}"

print("OK: frontmatter valid, all required sections present")
EOF
```

Expected: `OK: frontmatter valid, all required sections present`

- [x] **Step 3: Commit**

```bash
git add plugins/agents/hmcts-apim-sdlc-orchestrator/skills/exclude-db-from-priming-clear/SKILL.md
git commit -m "feat(hmcts-apim-sdlc-orchestrator): add exclude-db-from-priming-clear skill

Detects a service-cp-*'s dedicated Postgres database and raises a PR
against cpp-aks-ops excluding it from the nonprod priming pipeline's
quick_clear sweep, which otherwise discovers and truncates every
database on the shared server by default."
```

---

### Task 2: Chain `exclude-db-from-priming-clear` from `wire-service-deployment`

**Files:**
- Modify: `plugins/agents/hmcts-apim-sdlc-orchestrator/skills/wire-service-deployment/SKILL.md`

**Interfaces:**
- Consumes: the skill name `exclude-db-from-priming-clear` (Task 1) — invoked by name, no shared code/types.
- Produces: `wire-service-deployment` now also protects any dedicated database at onboarding time.

- [x] **Step 1: Update the frontmatter description**

Find this block at the top of the file:

```yaml
---
name: wire-service-deployment
description: >
  Wire up auto-dev and auto-SIT deployment CI for a service-cp-* repo after Azure
  provisioning and cp-vp-aks-deploy registration are complete. Idempotent — safe to
  invoke again if the jobs already exist. Use when a service-cp-* repo is missing the
  deploy-dev and deploy-sit jobs in its ci-build-publish.yml, or when setting up a
  newly bootstrapped service for the first time.
---
```

Replace it with:

```yaml
---
name: wire-service-deployment
description: >
  Wire up auto-dev and auto-SIT deployment CI for a service-cp-* repo after Azure
  provisioning and cp-vp-aks-deploy registration are complete. Idempotent — safe to
  invoke again if the jobs already exist. Use when a service-cp-* repo is missing the
  deploy-dev and deploy-sit jobs in its ci-build-publish.yml, or when setting up a
  newly bootstrapped service for the first time. Also detects a dedicated Postgres
  database and chains to exclude-db-from-priming-clear to protect it from the nonprod
  priming pipeline's quick_clear sweep.
---
```

- [x] **Step 2: Insert the new Step 11, before the `## Rules` section**

Find this block near the end of the file (the last line of Step 10, immediately
before `## Rules`):

```markdown
EOF
)"
```

---

## Rules
```

Replace it with (note the new `## Step 11` section inserted between the two):

```markdown
EOF
)"
```

---

## Step 11 — Protect any dedicated database from priming quick-clear

Run the same database-detection check `exclude-db-from-priming-clear` uses:

```bash
python3 - <<'EOF'
import re, os

candidate = None

if os.path.exists("docker-compose.yml"):
    with open("docker-compose.yml") as f:
        m = re.search(r"POSTGRES_DB:[ \t]*(\S+)", f.read())
        if m:
            candidate = m.group(1).strip()

if not candidate and os.path.exists("src/main/resources/application.yaml"):
    with open("src/main/resources/application.yaml") as f:
        text = f.read()
    m = re.search(
        r"datasource:\s*\n\s*url:\s*.*jdbc:postgresql://[^/]+/([a-zA-Z0-9_]+)",
        text,
    )
    if m:
        candidate = m.group(1)

print(f"DB_DETECTED:{candidate}" if candidate else "NO_DB_OWNED")
EOF
```

If `NO_DB_OWNED`, this service is a stateless proxy — nothing further to do.

If `DB_DETECTED:<name>`, invoke the `exclude-db-from-priming-clear` skill now,
passing `<name>` as the locally-detected candidate. That skill owns the
human-confirmation step (local dev naming can diverge from the deployed name)
and the PR to `cpp-aks-ops` — do not duplicate that logic here.

---

## Rules
```

- [x] **Step 3: Add a Rules bullet documenting the chain**

Find the last bullet of the `## Rules` section:

```markdown
- If `gh api` cannot read `cp-vp-aks-deploy` (permissions issue), ask the user to provide
  cluster params manually rather than blocking the entire workflow.
```

Replace it with:

```markdown
- If `gh api` cannot read `cp-vp-aks-deploy` (permissions issue), ask the user to provide
  cluster params manually rather than blocking the entire workflow.
- **Step 11's database chain is best-effort, not a gate.** If database detection or the
  chained `exclude-db-from-priming-clear` run fails, report it but do not block or roll
  back the CI-wiring PR already raised in Steps 6–10 — they are independent concerns.
```

- [x] **Step 4: Verify the required sections still exist**

```bash
python3 - <<'EOF'
path = "plugins/agents/hmcts-apim-sdlc-orchestrator/skills/wire-service-deployment/SKILL.md"
with open(path) as f:
    text = f.read()

for required in [
    "## Step 11 — Protect any dedicated database from priming quick-clear",
    "exclude-db-from-priming-clear",
    "Step 11's database chain is best-effort, not a gate.",
]:
    assert required in text, f"missing: {required}"

print("OK: chaining step present")
EOF
```

Expected: `OK: chaining step present`

- [x] **Step 5: Commit**

```bash
git add plugins/agents/hmcts-apim-sdlc-orchestrator/skills/wire-service-deployment/SKILL.md
git commit -m "feat(hmcts-apim-sdlc-orchestrator): chain exclude-db-from-priming-clear from wire-service-deployment

Every new service-cp-* with its own database is now protected from the
nonprod priming pipeline's quick_clear sweep at onboarding time, instead
of relying on someone noticing after data loss."
```

---

### Task 3: Sync README, CLAUDE.md, plugin.json, and marketplace.json

**Files:**
- Modify: `plugins/agents/hmcts-apim-sdlc-orchestrator/README.md`
- Modify: `plugins/agents/hmcts-apim-sdlc-orchestrator/CLAUDE.md`
- Modify: `plugins/agents/hmcts-apim-sdlc-orchestrator/.claude-plugin/plugin.json`
- Modify: `.claude-plugin/marketplace.json`

**Interfaces:**
- Consumes: the skill name `exclude-db-from-priming-clear` (Task 1).
- Produces: no new interfaces — documentation and version metadata only.

- [x] **Step 1: Update the README "What's inside" Skills row**

Find this row in the "What's inside" table:

```markdown
| **Skills** (`skills/`) | `openapi-spec-reviewer` — reviews a spec against 4 lenses (data-sharing/UK-GDPR, infrastructure-SLA/Azure, API standards, security); scored /100; `bootstrap-context` — writes `.claude/CLAUDE.md` with correct context imports (also runs automatically on session start); `springboot-api-from-template` — bootstraps a new `api-cp-*` repo from the HMCTS template, with team-ownership and git-access verification; `springboot-service-from-template` — bootstraps a new `service-cp-*` repo from the HMCTS template, chaining to `springboot-api-from-template` if the matching API repo doesn't exist yet, and trimming the new repo's README of generic template boilerplate (demo-project catalogue, inline build/PMD instructions) at scaffold time; `release` — cuts a GitHub release for an `api-cp-*`/`service-cp-*` repo: finds PRs merged since the last tag, filters out dependency/chore/docs noise, computes the next SemVer version, and creates the release with a synthesised functional changelog (the step that triggers Path B's SIT deploy gate) |
```

Replace it with:

```markdown
| **Skills** (`skills/`) | `openapi-spec-reviewer` — reviews a spec against 4 lenses (data-sharing/UK-GDPR, infrastructure-SLA/Azure, API standards, security); scored /100; `bootstrap-context` — writes `.claude/CLAUDE.md` with correct context imports (also runs automatically on session start); `springboot-api-from-template` — bootstraps a new `api-cp-*` repo from the HMCTS template, with team-ownership and git-access verification; `springboot-service-from-template` — bootstraps a new `service-cp-*` repo from the HMCTS template, chaining to `springboot-api-from-template` if the matching API repo doesn't exist yet, and trimming the new repo's README of generic template boilerplate (demo-project catalogue, inline build/PMD instructions) at scaffold time; `wire-service-deployment` — wires `deploy-dev`/`deploy-sit` CI jobs after Azure provisioning, chaining to `exclude-db-from-priming-clear` when the service owns a database; `exclude-db-from-priming-clear` — detects a service-cp-*'s dedicated Postgres database and raises a PR to `cpp-aks-ops` excluding it from the nonprod priming pipeline's `quick_clear` sweep; `release` — cuts a GitHub release for an `api-cp-*`/`service-cp-*` repo: finds PRs merged since the last tag, filters out dependency/chore/docs noise, computes the next SemVer version, and creates the release with a synthesised functional changelog (the step that triggers Path B's SIT deploy gate) |
```

- [x] **Step 2: Update the CLAUDE.md one-time service lifecycle skills table**

Find:

```markdown
One-time service lifecycle skills (run once per repo, not per feature):

| Skill | When |
|---|---|
| `wire-service-deployment` | After Azure provisioning and `cp-vp-aks-deploy` registration — wires `deploy-dev` and `deploy-sit` CI jobs |
```

Replace it with:

```markdown
One-time service lifecycle skills (run once per repo, not per feature):

| Skill | When |
|---|---|
| `wire-service-deployment` | After Azure provisioning and `cp-vp-aks-deploy` registration — wires `deploy-dev` and `deploy-sit` CI jobs, then chains to `exclude-db-from-priming-clear` if the service owns a database |
| `exclude-db-from-priming-clear` | Chained from `wire-service-deployment` for new services with a dedicated database, or run standalone to remediate an existing service after a priming data-loss incident |
```

- [x] **Step 3: Update the CLAUDE.md Path B stage table row 0b**

Find:

```markdown
| 0b | Wire deployment CI (one-time, new services only) | **`wire-service-deployment`** skill | Prereq: Azure provisioned + service in `cp-vp-aks-deploy` | — | Jobs wired → requirements-analyst |
```

Replace it with:

```markdown
| 0b | Wire deployment CI (one-time, new services only) | **`wire-service-deployment`** skill | Prereq: Azure provisioned + service in `cp-vp-aks-deploy` | — | Jobs wired (chains to `exclude-db-from-priming-clear` if a database is detected) → requirements-analyst |
```

- [x] **Step 4: Update `plugin.json` version and description**

In `plugins/agents/hmcts-apim-sdlc-orchestrator/.claude-plugin/plugin.json`:

```json
{
  "name": "hmcts-apim-sdlc-orchestrator",
  "version": "1.4.0",
  "description": "HMCTS API-Marketplace SDLC orchestrator — a fully self-contained, contract-first pipeline for OpenAPI-first api-cp-* spec libraries and service-cp-* Spring Boot services. Bundles all pipeline agents (requirements-analyst, apim-architect, story-writer, contract-test-engineer, implementation, code-reviewer, ci-orchestrator, deployer, catalog-publisher) plus two hub-and-spoke specialists (contract-compatibility-analyzer, feature-flag-auditor), the openapi-spec-reviewer, bootstrap-context, and release skills, the forked springboot-api-from-template / springboot-service-from-template repo-bootstrap skills (with git-access verification and README-hygiene trimming of template boilerplate), the wire-service-deployment CI-wiring skill now chained to a new exclude-db-from-priming-clear skill (protects any service-cp-*-owned database from the nonprod priming pipeline's quick_clear sweep), APIM context docs (including a standardized ClockService time-access pattern), and guard hooks. catalog-publisher runs a mandatory eligibility check and validates OpenAPI examples against their schemas before registering. Every pipeline stage now states an explicit signal/handoff to the next agent, implementation enforces a physical red-test gate before any code is written, and the Hard rules carry a broadened, enumerated ADR-trigger list. Targets GHA + ADO CI/CD, PMD, CodeQL, GHCR, and the cp-vp-aks-deploy GitOps repo.",
  "author": {
    "name": "HMCTS APIM"
  },
  "license": "MIT",
  "keywords": [
    "hmcts",
    "apim",
    "api-marketplace",
    "sdlc",
    "orchestrator",
    "openapi",
    "spring-boot",
    "contract-first",
    "agents",
    "pipeline"
  ]
}
```

- [x] **Step 5: Verify `plugin.json` is still valid JSON**

```bash
jq . plugins/agents/hmcts-apim-sdlc-orchestrator/.claude-plugin/plugin.json > /dev/null && echo "VALID JSON"
```

Expected: `VALID JSON`

- [x] **Step 6: Update the `marketplace.json` entry**

In `.claude-plugin/marketplace.json`, find the `hmcts-apim-sdlc-orchestrator` entry
(around line 105):

```json
    {
      "name": "hmcts-apim-sdlc-orchestrator",
      "source": "./plugins/agents/hmcts-apim-sdlc-orchestrator",
      "description": "HMCTS API-Marketplace SDLC orchestrator: contract-first dual-path pipeline for OpenAPI-first api-cp-* spec libraries and service-cp-* Spring Boot services. Fully self-contained — bundles its own pipeline agents (requirements-analyst, apim-architect, story-writer, contract-test-engineer, implementation, code-reviewer, ci-orchestrator, deployer, catalog-publisher) plus two hub-and-spoke specialists (contract-compatibility-analyzer, feature-flag-auditor), the openapi-spec-reviewer, bootstrap-context, and release skills, and the forked springboot-api-from-template / springboot-service-from-template repo-bootstrap skills (README-hygiene trimming of template boilerplate). catalog-publisher is eligibility-checked and examples-gated; every stage now signals its handoff explicitly and implementation enforces a physical red-test gate. Does not reuse hmcts-sdlc-orchestrator agents — that plugin targets a different (CQRS/WildFly) stack.",
      "version": "1.3.0",
      "category": "agent",
      "tags": ["hmcts", "apim", "api-marketplace", "sdlc", "orchestrator", "openapi", "spring-boot", "contract-first"]
    },
```

Replace it with:

```json
    {
      "name": "hmcts-apim-sdlc-orchestrator",
      "source": "./plugins/agents/hmcts-apim-sdlc-orchestrator",
      "description": "HMCTS API-Marketplace SDLC orchestrator: contract-first dual-path pipeline for OpenAPI-first api-cp-* spec libraries and service-cp-* Spring Boot services. Fully self-contained — bundles its own pipeline agents (requirements-analyst, apim-architect, story-writer, contract-test-engineer, implementation, code-reviewer, ci-orchestrator, deployer, catalog-publisher) plus two hub-and-spoke specialists (contract-compatibility-analyzer, feature-flag-auditor), the openapi-spec-reviewer, bootstrap-context, and release skills, and the forked springboot-api-from-template / springboot-service-from-template repo-bootstrap skills (README-hygiene trimming of template boilerplate). wire-service-deployment now chains to a new exclude-db-from-priming-clear skill, protecting any service-cp-*-owned database from the nonprod priming pipeline's quick_clear sweep. catalog-publisher is eligibility-checked and examples-gated; every stage now signals its handoff explicitly and implementation enforces a physical red-test gate. Does not reuse hmcts-sdlc-orchestrator agents — that plugin targets a different (CQRS/WildFly) stack.",
      "version": "1.4.0",
      "category": "agent",
      "tags": ["hmcts", "apim", "api-marketplace", "sdlc", "orchestrator", "openapi", "spring-boot", "contract-first"]
    },
```

- [x] **Step 7: Verify `marketplace.json` is still valid JSON and the version bumped**

```bash
jq '.plugins[] | select(.name=="hmcts-apim-sdlc-orchestrator") | {version, description}' .claude-plugin/marketplace.json
```

Expected: `version` is `"1.4.0"` and `description` contains the string
`"exclude-db-from-priming-clear"`.

- [x] **Step 8: Commit**

```bash
git add plugins/agents/hmcts-apim-sdlc-orchestrator/README.md \
        plugins/agents/hmcts-apim-sdlc-orchestrator/CLAUDE.md \
        plugins/agents/hmcts-apim-sdlc-orchestrator/.claude-plugin/plugin.json \
        .claude-plugin/marketplace.json
git commit -m "docs(hmcts-apim-sdlc-orchestrator): sync docs/versions for exclude-db-from-priming-clear

Adds the new skill to README, CLAUDE.md's lifecycle-skills table and
Path B stage 0b, and bumps plugin.json/marketplace.json to 1.4.0."
```

---

### Task 4: Plugin verification pass

**Files:** none (verification only).

**Interfaces:**
- Consumes: the committed state of Tasks 1–3.
- Produces: confidence the plugin still loads cleanly before it is used live in Task 5.

- [x] **Step 1: Run the code-review skill on the branch**

Invoke `code-review:review` on the current branch. Fix all findings (Must fix,
Should fix, and Nits) before proceeding.

- [x] **Step 2: Reload plugins**

```
/reload-plugins
```

Expected: the summary line's skill count increases by 1 for
`hmcts-apim-sdlc-orchestrator` (the new `exclude-db-from-priming-clear` skill), with
no load errors reported.

- [x] **Step 3: Run `/doctor`**

```
/doctor
```

Expected: `"Claude Code diagnostics dismissed"`. Any other output means a config file
has a syntax error — check the flagged file and reload again.

- [x] **Step 4: Smoke-test the new skill's trigger**

Ask Claude, in a session with the plugin loaded: *"Does `service-cp-crime-hearing`
have a database that needs protecting from priming quick-clear?"* Confirm
`exclude-db-from-priming-clear` fires and correctly reports `NO_DB_OWNED` (this
service is a stateless proxy per `service-shared.md`). If it doesn't trigger, the
frontmatter `description` is too narrow — broaden the intent patterns and re-run
Step 2.

- [x] **Step 5: Smoke-test the chaining trigger**

Ask Claude: *"Wire up deployment for a service that just provisioned its own
database."* Confirm `wire-service-deployment` is invoked and its Step 11 correctly
identifies that it should chain to `exclude-db-from-priming-clear`.

---

### Task 5: Remediate the live incident — exclude `pcr` from quick_clear

**Status: resolved externally.** The `pcr` database was excluded from
`quick_clear` via a direct PR against `hmcts/cpp-aks-ops` —
[#422 "Exclude pcr database from priming quick_clear truncation"](https://github.com/hmcts/cpp-aks-ops/pull/422),
merged 2026-08-12T08:18:17Z — raised and merged independently of this skill.
Verified via `gh pr diff 422`: it adds `pcr` to both deny-lists (dev `jq` path
and non-dev `psql NOT IN` path), the same two locations
`exclude-db-from-priming-clear`'s Step 4 targets, with no changes outside the
`quick_clear`-gated task.

No further action needed — running `exclude-db-from-priming-clear` against
`service-cp-crime-results-pcr` now correctly reports `ALREADY_EXCLUDED` at
Step 3 and stops.