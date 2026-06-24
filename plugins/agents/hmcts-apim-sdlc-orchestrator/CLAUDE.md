# HMCTS API-Marketplace SDLC — Orchestrator

## Project context
This is an HMCTS engineering project on the **API Marketplace** delivery model:
**OpenAPI-first `api-cp-*` spec libraries** consumed by **`service-cp-*` Spring Boot
services** (Java 25, Spring Boot 4.0.x, Gradle, Jakarta EE, published to GitHub Packages /
Azure Artifacts). All work complies with HMCTS engineering standards, the GDS Service Manual,
and MOJ security requirements.

This pipeline is **contract-first** and **CQRS-free**. There are no domain events, no RAML, no
Drools, no WildFly. If a request needs an event-sourced context service, redirect to the
`hmcts-sdlc-orchestrator` plugin — do not build one here.

## Context loading

The `SessionStart` hook (`hooks/bootstrap-context.sh`) automatically creates `.claude/CLAUDE.md`
in any `api-cp-*` or `service-cp-*` repo when the developer opens Claude Code — no manual step
needed. That file contains the three `@import` lines below.

Always load:
- `context/shared-code-rules.md` — team-wide code rules and naming conventions.
- `context/hmcts-standards.md` — security classification, Coding in the Open, repo ownership, Conventional Commits, PR hygiene, ADR triggers, data protection, test pyramid.

Load by repo type (detect from the directory name):
- `api-cp-*` → `context/api-spec-shared.md`
- `service-cp-*` → `context/service-shared.md`

Load on demand:
- `context/logging-standards.md` — when reviewing or writing logging code, or checking PR compliance.
- `context/azure-sdk-guide.md` — when the work touches any Azure integration (Service Bus, Key Vault, App Configuration, Blob, observability wiring, Helm/Kubernetes hygiene).
- `context/claude-md-standards.md` — when generating or refreshing a repo's `CLAUDE.md` (`/init`).

## Agents (all owned by this plugin)

All pipeline stages are handled by agents in this plugin. Use **`hmcts-apim-sdlc-orchestrator`**
agents for all `api-cp-*` or `service-cp-*` work — `hmcts-sdlc-orchestrator`'s agents target
a different stack (CQRS/WildFly/Jenkins/SonarQube/Snyk) and will produce incorrect guidance.

| Need | Agent |
|---|---|
| Requirements analysis | `requirements-analyst` |
| API design + OpenAPI authoring | `apim-architect` |
| User stories (Path B only) | `story-writer` |
| Contract tests (A-TDD) | `contract-test-engineer` |
| Implementation | `implementation` |
| Code review | `code-reviewer` |
| CI build/test/publish/deploy | `ci-orchestrator` |
| Deploy monitoring + SIT release | `deployer` |
| AMP catalog registration / update | `catalog-publisher` |

Standalone marketplace skills used as-is: `adr-template`, `bdd-workflow`, `review-checklist`,
`conventional-commit`, `code-review`, `explain-codebase`. PRs are raised with `gh` +
`conventional-commit` (no bundled PR skill). Cutting the GitHub Release that triggers Path B's
SIT deploy gate (stage 8, driven by `deployer`) uses the bundled **`release`** skill.

## Pipelines (run stages in order; halt at every human gate)

The orchestrator detects repo type and runs the matching path.
**Contract-first hard rule: a `service-cp-*` build must not start until its `api-cp-*` spec
artefact is published.**

### Path A — `api-cp-*` spec library (spec-only)

| # | Stage | Driver | Gate |
|---|---|---|---|
| 0 | Bootstrap repo (if new) | `springboot-api-from-template` skill | — |
| 1 | Requirements | **`requirements-analyst`** | Human |
| 2 | API design + OpenAPI authoring | **`apim-architect`** | Human |
| 3 | Contract review — Spectral lint + **`openapi-spec-reviewer`** (4 lenses, /100) | skill | **Human** |
| 4 | Publish spec artefact (SemVer + media type) | `ci-draft.yml` → **`ci-orchestrator`** | Auto |
| 5 | Register / update in AMP catalog | **`catalog-publisher`** | Auto (once per release) |

No code, no deploy. Output of Path A is a published `api-cp-*` artefact registered in the AMP catalog.

### Path B — `service-cp-*` service (requires a published spec)

| # | Stage | Driver | Gate |
|---|---|---|---|
| 0 | Verify the `api-cp-*` artefact is published | **`requirements-analyst`** check | **Blocks if missing** |
| 1 | Requirements | **`requirements-analyst`** | Human |
| 2 | Service design | **`apim-architect`** | Human |
| 3 | User stories | **`story-writer`** | Human |
| 4 | Contract & test specs | **`contract-test-engineer`** (Pact + Spring Boot Test) | **Human** |
| 5 | Implementation | **`implementation`** | Auto |
| 6 | Code review | **`code-reviewer`** | **Human** |
| 7 | Build, test & publish | **`ci-orchestrator`** (GHA + ADO) | Auto |
| 8 | Monitor deploy → dev (pipeline-triggered) / SIT (release) | **`deployer`** | Dev: pipeline; SIT: **Human** |
| 9 | Sync AMP catalog if spec metadata changed | **`catalog-publisher`** | Auto (on drift) |
| 10 | Raise PR | `gh` + `conventional-commit` skill | Human |

## Artefact output convention

```
docs/pipeline/
├── requirements.md
├── user-stories/<story-id>.md
├── test-specs/<story-id>.feature
├── adrs/<NNN>-<title>.md
└── deploy-notes.md
```

## Hard rules

- **Contract-first:** never start `service-cp-*` work before the `api-cp-*` artefact is published.
- Never proceed past a human gate without explicit confirmation.
- Never invent requirements, ACs, or test data — flag unknowns as open questions.
- Every story must have a linked Jira ticket before the test stage begins.
- Stage 3 of Path A must pass the `openapi-spec-reviewer` gate (no unresolved Critical findings) before publish.
- **No CQRS, RAML, Drools, WildFly, or domain-event design** — redirect such requests to `hmcts-sdlc-orchestrator`.
- The HMCTS templates are the master source: use `springboot-api-from-template` /
  `springboot-service-from-template` — do not scaffold build files, Dockerfile, or logback
  config from scratch. Deviations require an ADR.
- OpenAPI **3.1.0** for new specs; media-type + SemVer versioning; additive (backwards-compatible) evolution.
- `@JsonInclude(NON_NULL)` must be present in `additionalModelTypeAnnotations` (see `context/api-spec-shared.md`).
- No internal HMCTS domains in any spec (CI rejects them).
- Do not store PII, case data, or court reference numbers in artefacts or prompts.
- Azure integrations use the Azure SDK via Managed Identity — no connection strings, SAS tokens, or account keys in code, config, env vars, or Helm values.