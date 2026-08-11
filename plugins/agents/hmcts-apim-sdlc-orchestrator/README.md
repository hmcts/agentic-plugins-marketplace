# hmcts-apim-sdlc-orchestrator

Claude Code plugin that ships the **HMCTS API-Marketplace SDLC pipeline** — a fully
self-contained, contract-first, dual-path orchestrator for **OpenAPI-first `api-cp-*` spec
libraries** and **`service-cp-*` Spring Boot services**. All pipeline agents are built
natively for the API-first, Modern by Default stack.

## What's inside

| Component | Items |
|---|---|
| **Agents** (`agents/`) | Pipeline: `requirements-analyst`, `apim-architect`, `story-writer`, `contract-test-engineer`, `implementation`, `code-reviewer`, `ci-orchestrator`, `deployer`, `catalog-publisher` (eligibility-checked, examples-gated). Hub-and-spoke specialists (not gated to a numbered stage): `contract-compatibility-analyzer` (additive-vs-breaking spec-change + consumer-impact analysis), `feature-flag-auditor` (T1–T5 toggle placement + flag-debt sweep, generic across any service-cp-* repo) |
| **Skills** (`skills/`) | `openapi-spec-reviewer` — reviews a spec against 4 lenses (data-sharing/UK-GDPR, infrastructure-SLA/Azure, API standards, security); scored /100; `bootstrap-context` — writes `.claude/CLAUDE.md` with correct context imports (also runs automatically on session start); `springboot-api-from-template` — bootstraps a new `api-cp-*` repo from the HMCTS template, with team-ownership and git-access verification; `springboot-service-from-template` — bootstraps a new `service-cp-*` repo from the HMCTS template, chaining to `springboot-api-from-template` if the matching API repo doesn't exist yet, and trimming the new repo's README of generic template boilerplate (demo-project catalogue, inline build/PMD instructions) at scaffold time; `wire-service-deployment` — wires `deploy-dev`/`deploy-sit` CI jobs after Azure provisioning, chaining to `exclude-db-from-priming-clear` when the service owns a database; `exclude-db-from-priming-clear` — detects a service-cp-*'s dedicated Postgres database and raises a PR to `cpp-aks-ops` excluding it from the nonprod priming pipeline's `quick_clear` sweep; `release` — cuts a GitHub release for an `api-cp-*`/`service-cp-*` repo: finds PRs merged since the last tag, filters out dependency/chore/docs noise, computes the next SemVer version, and creates the release with a synthesised functional changelog (the step that triggers Path B's SIT deploy gate) |
| **Context** (`context/`) | `api-spec-shared`, `service-shared`, `shared-code-rules`, `hmcts-standards`, `logging-standards`, `azure-sdk-guide`, `claude-md-standards` |
| **Hooks** (`hooks/`) | `block-pii`, `block-secrets`, `guard-bash`, `guard-paths`, `bootstrap-context` (SessionStart — auto-creates `.claude/CLAUDE.md` in `api-cp-*`/`service-cp-*` repos) |
| **Orchestration** | `CLAUDE.md` — the dual-path, contract-first pipeline |

## Prerequisites

- Claude Code with the [agentic-plugins-marketplace](https://github.com/hmcts/agentic-plugins-marketplace) registered.
- `gh` CLI authenticated (`gh auth status`) — used for PR creation, CI monitoring, and release management.
- Docker — required for `./gradlew dockerTest` (Service Bus emulator + Postgres).

## Installation

```
/plugin install hmcts-apim-sdlc-orchestrator@agentic-plugins-marketplace
```

Context bootstraps **automatically** — the `SessionStart` hook creates the gitignored
`.claude/CLAUDE.md` with the correct `@import` lines every time you open an `api-cp-*`
or `service-cp-*` repo in Claude Code. No manual step needed.

Run `/init` afterwards to generate or refresh the committed `CLAUDE.md` for the repo.

> `/bootstrap-context` is available if you need to force an update manually.

## Usage

```
api-cp-*  →  requirements → apim-architect (design + author OpenAPI)
          →  contract review (Spectral + openapi-spec-reviewer) [gate] → publish
service-cp-* (needs published spec)
          →  requirements → apim-architect → stories → contract-test-engineer [gate]
          →  implementation → code review [gate] → CI → PR → (dev deploys via existing pipeline on merge; SIT via GitHub Release [gate])
```

> "Design the courthouses reference-data API and draft its spec" — invokes `apim-architect`.
> "Review this OpenAPI spec" — invokes `openapi-spec-reviewer`.
> "Scaffold the tests for the approved court-schedule service stories" — invokes `contract-test-engineer`.
> "Is this spec change safe? Who consumes it?" — invokes `contract-compatibility-analyzer`.
> "Check this service for stale feature flags" — invokes `feature-flag-auditor`.

## Roadmap

- ~~`api-dependency-analyzer`~~ — delivered as `contract-compatibility-analyzer` (see Agents above).
- `authentication-auditor` (**TBD**) — APIM authentication/authorization audit
  (`securitySchemes` coverage, OAuth2/OIDC scopes, Spring Security config). Replaces the
  scope pending the in-flight authZ/authN design.
- `slo-observability-reviewer` (**TBD**) — verifies a changed endpoint ships metrics,
  structured logs, trace correlation, and an SLO/alert definition before `code-reviewer`
  approves.
- `legacy-parity-analyst` (**TBD**) — systematic legacy-to-MbD migration comparison, for
  when a `service-cp-*` replaces or wraps an existing `cpp-context-*`/Azure Functions system
  and byte-for-byte behavioural parity (including known legacy quirks) needs an explicit
  replicate-or-diverge decision rather than manual, one-off archaeology.

## Context bootstrap

The `SessionStart` hook (`hooks/bootstrap-context.sh`) runs automatically every time Claude Code
starts in an `api-cp-*` or `service-cp-*` repo. It creates (or verifies) the gitignored
`.claude/CLAUDE.md` with three `@import` lines pointing to this plugin's `context/` files — no
manual step required.

Run `/bootstrap-context` only when you need to force an update or in a repo that hasn't been opened in Claude Code yet.