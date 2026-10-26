---
name: promote-cnp-environment
description: >
  Use when a CNP-hosted app (Jenkins + Flux, e.g. web-api-marketplace, service-api-marketplace)
  works in one environment and must be brought up in another — sbox to AAT/staging, demo or
  prod — or when asked what infra is missing in an environment, which PRs to raise and in
  what order, or why an app starts in sandbox but not elsewhere (502, pod stuck in Init,
  AADSTS50011, WAF 403 on callback).
---

# Promote a CNP app to another environment

## Overview

Treat the working environment (usually sbox) as the specification. Inventory it layer by
layer, diff the target against it, then raise the missing changes as **waves of PRs**, where
each wave only references things an earlier wave created and that are already applied.
Every wave is behind a human gate. Nothing is raised without approval, and **the agent never
merges or applies**: each PR is reviewed, approved and merged by the owners of its repo.

## Inputs

Ask for any you cannot infer: components (repos + HelmRelease names), Flux namespace/product,
source env, target env(s), Jira key.

**Delta mode:** when called for one change (a PR or design that adds a secret, vault mount,
Entra app, env var or role), run steps 3–6 for that change only, across every target env.

## Process

1. **Health and work in flight.** `curl` each env's public `/health` and record the commit it
   serves; for internal-only components use the HelmRelease or Jenkins status. A target
   already down is fixed in Wave 0. List open, and recently closed-unmerged, PRs touching the
   target's files (`gh pr list --search`): they conflict with or already cover the plan. A
   rename or product move in flight is resolved first (finish it, or promote under the old
   name); otherwise every wave is built twice.
2. **Inventory the source**, per layer in the table below. For each item record the file and
   the PR that added it. Grants often live outside the app's repos, so search the org for each
   identifier (identity object/client id, app name, host):
   `gh search code --owner hmcts "<id>"`. Only after that search finds nothing is an item
   "not in code" (a portal grant, a hand-made secret). Codify it rather than copying it by hand.
   Flag any name that disagrees between files (e.g. a vault named differently in two configs).
3. **Scan app defaults.** Grep `application.yaml`, `config/*.json` and chart `values.yaml` for
   values with a default that names the source env (tenant ids, APIM names, client ids,
   inboxes, URLs). Each must be overridden in the target, or the target silently talks to
   the source env.
4. **Diff the target** layer by layer. Mark each item Done / To do / To confirm. To confirm is
   state the code cannot show (role assignments, vault contents, identity object ids): name the
   owner and what they check (portal or their own CLI). Never assume it is done.
5. **Write the plan** (format below) and stop at **Gate 0**.
6. **Per wave:** show the exact diffs and get approval to raise them. Raise each PR and
   request review from its owners: the repo's `CODEOWNERS`, or the team that owns that
   environment (PlatOps for platform repos, tenant owners for Entra, the service team for app
   repos). Prod PRs go to the prod owners. Then report the PR links and stop. The owners
   review, approve and merge. The next gate opens only when the wave is merged **and**
   applied (Terraform pipeline green, Flux reconciled, `/health` unchanged or better).

## Layers and waves

| Wave | Layer | Where (CNP) | Must exist first |
|---|---|---|---|
| 0 | Keep the target running: switch off features whose dependencies are missing | `cnp-flux-config apps/<ns>/<app>/<env>.yaml` | — |
| 1 | Managed identity, RBAC (APIM, Key Vault) | `apps/<ns>/serviceaccount/<env>.yaml`; APIM role in `shared-platform-services-infra environments/<env>/` (`apim_subscription_managers`); app `infrastructure/` | — |
| 1 | Entra: sign-in, onboarding and resource apps, user flows, redirect URIs, secret readers | `external-entra-id tenants/<tenant>/config/` | identity object id |
| 1 | DNS | `azure-public-dns environments/<env>/` | — |
| 2 | App infra: DB, Redis, vault, generated secrets; every Terraform variable with no default (e.g. `aks_subscription_id`) | each repo `infrastructure/<env>.tfvars` | identity |
| 2 | Manual secrets (third-party keys) | vault, by an owner | vault |
| 3 | Front Door + WAF exclusions (cookies, `code`/`state`/`session_state`) | `azure-platform-terraform environments/<env>/` | DNS |
| 4 | Pipeline: `values.<env>.template.yaml`, prod approval | app repo `charts/`, `cnp-jenkins-config environment-approvals.yml` | secrets exist |
| 5 | Flux overlays: identity, vault mounts, env settings; cluster inclusion | `cnp-flux-config apps/<ns>/`, `clusters/<env>/` | waves 1–4 applied |
| 6 | Switch features back on, then smoke test | Flux overlay | wave 5 healthy |

Tenant map is per product; read it from `external-entra-id` (sbox→sbox, aat/demo→stg or none, prod→prod).

## No-regression rules

- **Additive and env-scoped.** A PR touches only the target env's files. Shared files (base
  HelmRelease, chart `values.yaml`, app defaults) change in their own PR, after every env using
  them is checked.
- **Mount only what exists.** A vault secret listed before it exists leaves the pod in Init.
- **Keep the old value during a migration** (both redirect URIs, both hosts) and remove it in a later wave.
- **Terraform plan:** any destroy or replace stops the wave.
- **One concern per PR**, each revertable on its own. The body states depends-on, verification and rollback.
- **Owners merge, not the agent.** Never merge, approve, self-approve, enable auto-merge or
  apply, even when you have the rights. Track each PR until its owner merges it, and nudge
  owners before the stale bot closes it.
- **A rename or product move is its own migration**: new identity means new secret readers and RBAC. Finish it in the source env before promoting.

## Gates

| Gate | Opens when |
|---|---|
| 0 Plan | The human approves the gap report and wave list |
| Wave N | Every PR in the previous wave is approved and merged by its owners, then applied and verified; this wave's diffs approved for raising |
| Demo | A scope decision is recorded: full parity, or running with features off |
| **Prod** | AAT smoke test passed; prod checklist met (sizing/HA/backups, least-privilege roles, no localhost URIs or test users as secret readers, alerts, shutter runbook, prod approval in Jenkins); a named approver says go; each prod PR is approved and merged by the prod owners of its repo |

Never skip a gate because a change "looks safe". Prod image bumps stay manual.

## Plan format

Under 700 words; one block per target env.

```
<env> — <status in one line> (health: <code>/<commit>)
Gaps: table Layer | Item | Done/To do/To confirm | Evidence (file or PR)
Waves: W<n>: <repo> — <change> — owner/reviewer — depends on — rollback
Risks: anything that could break source or other envs
Decisions needed: question — owner
```

## Common mistakes

| Symptom in target | Cause |
|---|---|
| 502, app refuses to start | Required config missing and no feature switch set |
| Pod stuck in Init | Vault secret mounted before it was created, or identity is not a secret reader |
| AADSTS50011 on sign-in | Redirect URI not registered for the target host |
| 403 on `/auth/callback` | WAF query-string exclusions missing |
| Works, but writes to sandbox resources | Source-env default not overridden |
| Prod stage fails in Jenkins | Repo missing from `environment-approvals.yml` |
| Fix was approved but never landed | PR closed by the stale bot |
