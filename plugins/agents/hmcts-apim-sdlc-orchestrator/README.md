# hmcts-apim-sdlc-orchestrator

Claude Code plugin that ships the **HMCTS API-Marketplace SDLC pipeline** — a contract-first,
dual-path orchestrator for **OpenAPI-first `api-cp-*` spec libraries** and **`service-cp-*`
Spring Boot services**. It is the API-first counterpart to `hmcts-sdlc-orchestrator` (which
targets the CQRS / `cpp-context-*` model) and **reuses that plugin's generic agents by
reference** rather than duplicating them.

## What's inside

| Component | Items |
|---|---|
| **Agents** (`agents/`) | `apim-architect` (OpenAPI-first design + spec authoring), `contract-test-engineer` (Pact + Spring Boot Test, A-TDD) |
| **Skills** (`skills/`) | `openapi-spec-reviewer` — reviews a spec against 4 lenses (data-sharing/UK-GDPR, infrastructure-SLA/Azure, API standards, security); scored /100 |
| **Context** (`context/`) | `api-spec-shared`, `service-shared`, `shared-code-rules`, `claude-md-standards` |
| **Hooks** (`hooks/`) | `block-pii`, `block-secrets`, `guard-bash`, `guard-paths` |
| **Orchestration** | `CLAUDE.md` — the dual-path, contract-first pipeline |

## Reused by reference (not bundled)

The generic stages are driven by the co-installed **`hmcts-sdlc-orchestrator`** plugin:
`requirements-analyst`, `story-writer`, `implementation`, `code-reviewer`, `ci-orchestrator`,
`deployer`, `helm-config-validator`, plus the `springboot-api-from-template` /
`springboot-service-from-template` skills. PRs use `gh` + the `conventional-commit` skill.

## Prerequisites

- Claude Code with the [agentic-plugins-marketplace](https://github.com/hmcts/agentic-plugins-marketplace) registered.
- **`hmcts-sdlc-orchestrator` installed** — provides the referenced generic agents. If it is
  absent, referenced stages fall back to inline prompts (the pipeline does not block).
- `gh` CLI for PR creation; Docker for `./gradlew dockerTest` API tests.

## Installation

```
/plugin install hmcts-apim-sdlc-orchestrator@agentic-plugins-marketplace
```

To enable the pipeline in a repo, copy `CLAUDE.md` into the project root:
```bash
cp ~/.claude/plugins/hmcts-apim-sdlc-orchestrator/CLAUDE.md ./CLAUDE.md
```

## Usage

```
api-cp-*  →  requirements → apim-architect (design + author OpenAPI)
          →  contract review (Spectral + openapi-spec-reviewer) [gate] → publish
service-cp-* (needs published spec)
          →  requirements → apim-architect → stories → contract-test-engineer [gate]
          →  implementation → code review [gate] → CI → deploy [gate] → PR
```

> "Design the courthouses reference-data API and draft its spec" — invokes `apim-architect`.
> "Review this OpenAPI spec" — invokes `openapi-spec-reviewer`.
> "Scaffold the tests for the approved court-schedule service stories" — invokes `contract-test-engineer`.

## Roadmap

- `api-dependency-analyzer` (optional) — maps which `service-cp-*` consume which `api-cp-*`
  spec versions; breaking-change detection.
- `authentication-auditor` (**TBD**) — APIM authentication/authorization audit
  (`securitySchemes` coverage, OAuth2/OIDC scopes, Spring Security config). Replaces the
  CQRS `rbac-auditor`; scope pending the in-flight authZ/authN design.

## Relationship to `apim-claude-template`

This plugin supersedes `apim-claude-template`: the four shared templates moved to `context/`
and the `openapi-spec-reviewer` skill moved to `skills/`. Once consumer repos are re-pointed,
`apim-claude-template` is decommissioned.