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

Always load:
- `context/shared-code-rules.md` — team-wide code rules.

Load by repo type (detect from the directory name):
- `api-cp-*` → `context/api-spec-shared.md`
- `service-cp-*` → `context/service-shared.md`

Load on demand:
- `context/claude-md-standards.md` — when generating or refreshing a repo's `CLAUDE.md` (`/init`).

## Reused agents (referenced, not duplicated)

Generic, delivery-model-agnostic stages are driven by the **CPP-owned
`hmcts-sdlc-orchestrator`** plugin — invoke them by `subagent_type`, never modify them:

| Need | Referenced agent |
|---|---|
| Requirements | `hmcts-sdlc-orchestrator:requirements-analyst` |
| User stories | `hmcts-sdlc-orchestrator:story-writer` |
| Service implementation | `hmcts-sdlc-orchestrator:implementation` |
| Code review | `hmcts-sdlc-orchestrator:code-reviewer` |
| CI build/test/publish | `hmcts-sdlc-orchestrator:ci-orchestrator` |
| Deploy to sandbox | `hmcts-sdlc-orchestrator:deployer` |
| Helm validation | `hmcts-sdlc-orchestrator:helm-config-validator` |

**Fallback:** if `hmcts-sdlc-orchestrator` is not installed, run that stage from an inline
prompt using the loaded context docs — do not block the pipeline.

Standalone marketplace skills used as-is: `adr-template`, `bdd-workflow`, `review-checklist`,
`conventional-commit`, `code-review`, `explain-codebase`. PRs are raised with `gh` +
`conventional-commit` (no bundled PR/release skill).

## Pipelines (run stages in order; halt at every human gate)

The orchestrator detects repo type and runs the matching path.
**Contract-first hard rule: a `service-cp-*` build must not start until its `api-cp-*` spec
artefact is published.**

### Path A — `api-cp-*` spec library (spec-only)

| # | Stage | Driver | Gate |
|---|---|---|---|
| 0 | Bootstrap repo (if new) | `springboot-api-from-template` (hmcts-sdlc-orchestrator) | — |
| 1 | Requirements | `requirements-analyst` *(ref)* | Human |
| 2 | API design + OpenAPI authoring | **`apim-architect`** + `context/api-spec-shared.md` | Human |
| 3 | **Contract review** — Spectral lint + **`openapi-spec-reviewer`** (4 lenses, score /100) | `spectral lint` + skill | **Human** |
| 4 | Publish spec artefact (SemVer + media type) | `ci-draft.yml` CI | Auto |

No code, no deploy. Output of Path A is a published `api-cp-*` artefact.

### Path B — `service-cp-*` service (requires a published spec)

| # | Stage | Driver | Gate |
|---|---|---|---|
| 0 | Verify the `api-cp-*` artefact is published | orchestrator check | **Blocks if missing** |
| 1 | Requirements | `requirements-analyst` *(ref)* | Human |
| 2 | Service design | **`apim-architect`** + `context/service-shared.md` | Human |
| 3 | User stories | `story-writer` *(ref)* | Human |
| 4 | Contract & test specs | **`contract-test-engineer`** (Pact + Spring Boot Test) | **Human** |
| 5 | Implementation | `implementation` *(ref)*, per `context/service-shared.md` | Auto |
| 6 | Code review | `code-reviewer` *(ref)* + `review-checklist` + service/code overlay | **Human** |
| 7 | Build, test & publish | `ci-orchestrator` *(ref)* | Auto |
| 8 | Deploy → sandbox | `deployer` *(ref)* + `helm-config-validator` *(ref)* | **Human** |
| 9 | Raise PR | `gh` + `conventional-commit` | Human |

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