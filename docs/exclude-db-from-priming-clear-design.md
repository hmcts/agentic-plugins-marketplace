# Design: `exclude-db-from-priming-clear` skill

**Date:** 2026-08-11
**Plugin:** `hmcts-apim-sdlc-orchestrator`
**Status:** Approved for implementation planning

## Problem

`hmcts/cpp-aks-ops/aks_priming_deploy.yaml` runs a `quick_clear` job in the nonprod priming
pipeline that **discovers every database** on the shared Azure Postgres flexible server
(`az postgres flexible-server db list` / `SELECT datname FROM pg_database`) and truncates all
tables in each one, except a small hardcoded deny-list of system databases: `template0`,
`template1`, `postgres`, `repmgr`, `azure_maintenance`, `azure_sys`, `hrds`.

Any new service database that appears on that server is swept by default. This is what
happened to the `pcr` database owned by `service-cp-crime-results-pcr` — its priming run
(build 780429) truncated `cp_judicial_result`, `cp_case_hearing`, `cp_court_application`,
`cp_offence`, and cascaded tables. `hrds` already being in the deny-list shows this
"add the db name to the deny-list" fix pattern is established precedent, not new territory.

This is a recurring failure mode: every new `service-cp-*` that provisions its own Postgres
database is unprotected from `quick_clear` until someone notices data loss and manually
patches the deny-list.

## Goal

1. Prevent recurrence: any future `service-cp-*` with its own database is protected
   automatically at onboarding time, before it can ever be swept. (The live `pcr`
   incident itself was resolved externally, independent of this skill — see
   "Fixing the live incident" below.)

## Non-goals

- Changing `priming_enable` / `restore_dataset` behaviour — only the `quick_clear`-gated
  `runQuickClear` task (`condition: eq('${{ parameters.quick_clear }}', true)`) is touched.
- Redesigning the deny-list into an allow-list model. Bigger change, affects every database
  on the shared server (including databases this plugin has no inventory of), needs
  `cpp-aks-ops` owners' buy-in — out of scope for this fix.
- Auditing every existing `service-cp-*` repo for other unprotected databases. Only `pcr` is
  fixed retroactively as part of this work; future services are covered by the onboarding hook.

## Design

### New skill: `exclude-db-from-priming-clear`

Added to `hmcts-apim-sdlc-orchestrator/skills/exclude-db-from-priming-clear/SKILL.md`.

**Step 1 — Detect a dedicated database.**
Check, in order:
1. `POSTGRES_DB` in `docker-compose.yml`
2. `spring.datasource.url` in `src/main/resources/application.yaml`

If neither is present, report "no dedicated database owned by this service — nothing to
protect" and exit. This is the "if it has any db" gate from the original ask.

**Step 2 — Propose and confirm the real database name.**
Extract a candidate name (prefer the literal `POSTGRES_DB` value; otherwise parse the path
segment of the `spring.datasource.url` JDBC URL). Always pause and ask a human to confirm the
actual nonprod database name before proceeding — local dev naming can diverge from what's
provisioned on the shared server (confirmed case: local `pcrdb` vs. deployed `pcr`). Never
write an unconfirmed name into the ops PR.

**Step 3 — Idempotency check.**
Clone `hmcts/cpp-aks-ops` into `/tmp/cpp-aks-ops` (same `gh repo clone` pattern
`catalog-publisher` already uses for `hmcts/amp-catalog` — a local clone, not a read-only
`gh api` lookup, because Step 4 needs to write the patched file back and Step 5 needs to
push a branch from it). If the confirmed name is already present in both deny-lists below,
report "already excluded" and exit.

**Step 4 — Patch exactly two lines**, both inside the single `runQuickClear` task:
- the dev-path `jq -r '.[].name | select(...)'` chain (currently ends `... and . != "hrds"`)
- the non-dev-path `psql ... datname NOT IN (...)` list (currently ends `..., 'hrds');`)

Append the confirmed name to both, preserving existing formatting exactly.

**Step 5 — Raise a PR against `cpp-aks-ops`.**
New branch, commit, push, PR — never auto-merged (shared ops repo outside this plugin's
owned repos; same human-gate posture as `wire-service-deployment`). PR body states:
- which service owns the database and why it must never be swept by quick_clear
- a checklist item asking the ops reviewer to confirm the name is correct across every
  environment (dev/ste/sit), since instance naming can vary per environment

### Onboarding integration

`wire-service-deployment` gains one additional step after CI wiring is complete: run the
same Step 1 detection, and if a datasource is found, chain to
`exclude-db-from-priming-clear` automatically — the same chaining pattern
`springboot-service-from-template` already uses to call `springboot-api-from-template` when
the matching API repo doesn't exist yet.

This is deliberately a separate skill rather than folded into `wire-service-deployment`
directly: CI-wiring (this repo's GitHub Actions) and priming-exclusion (a PR to a different,
shared ops repo) are different concerns with different blast radii and different reviewers.

### Fixing the live incident

The live `pcr` incident was resolved externally, independent of this skill: a separate,
already-merged PR — `hmcts/cpp-aks-ops#422` ("Exclude pcr database from priming
quick_clear truncation"), merged 2026-08-12T08:18:17Z — added `pcr` to both deny-lists
directly against `cpp-aks-ops`. This skill did not raise that fix; running it against
`service-cp-crime-results-pcr` now correctly reports `ALREADY_EXCLUDED` at Step 3.

## Alternatives considered

| Alternative | Rejected because |
|---|---|
| Bake detection into `springboot-service-from-template` instead of `wire-service-deployment` | DB provisioning/naming isn't finalized at template-scaffold time, before Azure resources exist. `wire-service-deployment`'s gate (Azure provisioning done) is the correct checkpoint. |
| Flip `aks_priming_deploy.yaml` to an allow-list model | Much larger change to a shared, multi-team ops repo; needs `cpp-aks-ops` owners' buy-in; affects every database on the server, not just `service-cp-*`-owned ones. Out of scope for this fix. |

## Rollout / files touched

- New: `hmcts-apim-sdlc-orchestrator/skills/exclude-db-from-priming-clear/SKILL.md`
- Edit: `hmcts-apim-sdlc-orchestrator/skills/wire-service-deployment/SKILL.md` (new chaining step)
- Edit: `hmcts-apim-sdlc-orchestrator/README.md` (list the new skill; note the chaining)
- Edit: `hmcts-apim-sdlc-orchestrator/CLAUDE.md` (stage 0b table — mention priming protection)
- Edit: `hmcts-apim-sdlc-orchestrator/.claude-plugin/plugin.json` (version bump + description)
- One-off: run the new skill against `service-cp-crime-results-pcr` to raise the real fix PR
  against `cpp-aks-ops`