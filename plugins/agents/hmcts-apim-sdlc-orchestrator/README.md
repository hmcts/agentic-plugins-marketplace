# hmcts-apim-sdlc-orchestrator

Claude Code plugin that ships the **HMCTS API-Marketplace SDLC pipeline** — a fully
self-contained, contract-first, dual-path orchestrator for **OpenAPI-first `api-cp-*` spec
libraries** and **`service-cp-*` Spring Boot services**. All pipeline agents are built
natively for the API-first, Modern by Default stack.

## What's inside

| Component | Items |
|---|---|
| **Agents** (`agents/`) | `requirements-analyst`, `apim-architect`, `story-writer`, `contract-test-engineer`, `implementation`, `code-reviewer`, `ci-orchestrator`, `deployer`, `catalog-publisher` — full self-contained pipeline |
| **Skills** (`skills/`) | `openapi-spec-reviewer` — reviews a spec against 4 lenses (data-sharing/UK-GDPR, infrastructure-SLA/Azure, API standards, security); scored /100; `bootstrap-context` — writes `.claude/CLAUDE.md` with correct context imports (also runs automatically on session start) |
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

## Roadmap

- `api-dependency-analyzer` (optional) — maps which `service-cp-*` consume which `api-cp-*`
  spec versions; breaking-change detection.
- `authentication-auditor` (**TBD**) — APIM authentication/authorization audit
  (`securitySchemes` coverage, OAuth2/OIDC scopes, Spring Security config). Replaces the
  scope pending the in-flight authZ/authN design.

## Context bootstrap

The `SessionStart` hook (`hooks/bootstrap-context.sh`) runs automatically every time Claude Code
starts in an `api-cp-*` or `service-cp-*` repo. It creates (or verifies) the gitignored
`.claude/CLAUDE.md` with three `@import` lines pointing to this plugin's `context/` files — no
manual step required.

Run `/bootstrap-context` only when you need to force an update or in a repo that hasn't been opened in Claude Code yet.