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

### Hub-and-spoke specialist agents (not gated to a numbered stage)

These plug in ad hoc — invoked whenever their concern is live, not as a fixed pipeline
stage. Each still reports back to whichever numbered stage is currently open.

| Need | Agent | Typically invoked from |
|---|---|---|
| Is this spec change additive or breaking? Which `service-cp-*` consumers pin the old version? | `contract-compatibility-analyzer` | `apim-architect` (design time) and `code-reviewer` (any PR touching `openapi-spec.yml`) |
| Is a `@Value` feature toggle stale (100% rolled out, safe to delete) or violating T1–T5? | `feature-flag-auditor` | `code-reviewer` (pre-merge) or run standalone as a periodic sweep |

Standalone marketplace skills used as-is: `adr-template`, `bdd-workflow`, `review-checklist`,
`conventional-commit`, `code-review`, `explain-codebase`. PRs are raised with `gh` +
`conventional-commit` (no bundled PR skill). Cutting the GitHub Release that triggers Path B's
SIT deploy gate (stage 8, driven by `deployer`) uses the bundled **`release`** skill.

One-time service lifecycle skills (run once per repo, not per feature):

| Skill | When |
|---|---|
| `wire-service-deployment` | After Azure provisioning and `cp-vp-aks-deploy` registration — wires `deploy-dev` and `deploy-sit` CI jobs |

## Pipelines (run stages in order; halt at every human gate)

The orchestrator detects repo type and runs the matching path.
**Contract-first hard rule: a `service-cp-*` build must not start until its `api-cp-*` spec
artefact is published.**

The **MbD stage** column maps each row onto the standard idea-to-production model
(Stage 0 Idea → 1 Shape & examples → 2 Write acceptance test first, red → 3 Implement on
trunk → 4 PR & CI → 5 Build the artefact → 6 GitOps delivery → 7 Release & observe) so
design docs, this file, and engineers' mental model share one vocabulary. Stage *numbers*
in the leftmost column are this plugin's own and are referenced elsewhere (e.g.
`apim-architect`'s "Stage-3 gate") — they are not renumbered to match MbD.

### Path A — `api-cp-*` spec library (spec-only)

| # | Stage | Driver | Gate | MbD stage | Signal to next |
|---|---|---|---|---|---|
| 0 | Bootstrap repo (if new) | `springboot-api-from-template` skill | — | — | Repo scaffolded → requirements-analyst |
| 1 | Requirements | **`requirements-analyst`** | Human | 0–1 | Requirements approved → apim-architect |
| 2 | API design + OpenAPI authoring | **`apim-architect`** | Human | 1 | Spec drafted → contract review |
| 3 | Contract review — Spectral lint + **`openapi-spec-reviewer`** (4 lenses, /100) | skill | **Human** | 1–2 | No unresolved Critical findings → ci-orchestrator |
| 4 | Publish spec artefact (SemVer + media type) | `ci-draft.yml` → **`ci-orchestrator`** | Auto | 5 | Artefact published to GitHub Packages + Azure Artifacts → catalog-publisher |
| 5 | Register / update in AMP catalog | **`catalog-publisher`** | Auto (once per release) | 7 | — |

No code, no deploy. Output of Path A is a published `api-cp-*` artefact registered in the AMP catalog.

### Path B — `service-cp-*` service (requires a published spec)

| # | Stage | Driver | Gate | MbD stage | Signal to next |
|---|---|---|---|---|---|
| 0 | Verify the `api-cp-*` artefact is published | **`requirements-analyst`** check | **Blocks if missing** | — | Confirmed published → continue; missing → halt |
| 0b | Wire deployment CI (one-time, new services only) | **`wire-service-deployment`** skill | Prereq: Azure provisioned + service in `cp-vp-aks-deploy` | — | Jobs wired → requirements-analyst |
| 1 | Requirements | **`requirements-analyst`** | Human | 0–1 | Requirements approved → apim-architect |
| 2 | Service design | **`apim-architect`** | Human | 1 | Design approved → story-writer |
| 3 | User stories | **`story-writer`** | Human | 1 | Stories approved, linked Jira ticket exists → contract-test-engineer |
| 4 | Contract & test specs | **`contract-test-engineer`** (Pact + Spring Boot Test) | **Human** | 2 | Tests committed and confirmed **RED** → implementation |
| 5 | Implementation | **`implementation`** | Auto | 3 | All tests **GREEN**, `pmdMain` clean, PR opened → code-reviewer |
| 6 | Code review | **`code-reviewer`** | **Human** | 4 | PR `claude-approved` + human approval → ci-orchestrator; `changes-requested` → back to implementation |
| 7 | Build, test & publish | **`ci-orchestrator`** (GHA + ADO) | Auto | 5 | Artefact + image published → deployer; failure → back to implementation or escalate |
| 8 | Monitor deploy → dev (pipeline-triggered) / SIT (release) | **`deployer`** | Dev: pipeline; SIT: **Human** | 6–7 | Deployed dark, smoke-checked → feature stays behind its toggle until a human/product decision flips it |
| 9 | Sync AMP catalog if spec metadata changed | **`catalog-publisher`** | Auto (on drift) | 7 | — |
| 10 | Raise PR | `gh` + `conventional-commit` skill | Human | — | — |

## Definition of Ready / Definition of Done

Consolidates checks already scattered across individual agent files into one visible
gate per direction of travel — nothing below is a new tool or process, only a single
place that states what "ready" and "done" mean.

**Definition of Ready** — before `contract-test-engineer` (stage 4) starts:
- Story is INVEST (independent, negotiable, valuable, estimable, small, testable)
- Every AC is Given/When/Then and references a concrete HTTP status + response shape
- No open question blocks this specific slice (unresolved ones are deferred, not guessed)
- The `api-cp-*` artefact version the story references is actually published
- A linked Jira ticket exists

**Definition of Done** — before stage 6 (`code-reviewer`) approves the PR:
- Every AC proven at the layer where it's observable to a consumer (`@SpringBootTest` +
  WireMock/Testcontainers), not only unit-level — see `code-reviewer.md` §J
- `./gradlew build` green (compiles, unit + integration, `-Werror` satisfied)
- `./gradlew pmdMain` — zero violations
- Pact contract verified for every service boundary the change crosses (consumer +
  provider); the published OpenAPI spec is the source of truth — a diverging test is
  wrong, not the contract
- Zero new CodeQL Critical/High findings; zero gitleaks hits
- Backwards-compatible, or a versioned major-bump change with an ADR (see Hard rules)
- Any `@Value` feature toggle follows placement rules T1–T5 (`context/service-shared.md`);
  no dead toggle field left behind
- New env vars documented in `.envrc.example`
- Human PR approval (the one mandatory human gate before CI)

**Definition of Done — before a SIT release (stage 8) is even considered**, on top of
everything above:
- Deployed to dev and smoke-checked (`/actuator/health/readiness` + `/liveness`)

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
- **No implementation ahead of a red test.** `implementation` (stage 5) must confirm a
  committed, failing acceptance/contract test exists for the story and run it to confirm
  RED before writing any production code. No test scaffolding for this story →
  halt and return to `contract-test-engineer`. This is the physical, checkable version of
  "human gate" — not satisfied by an agent's own claim that it planned.
- **No CQRS, RAML, Drools, WildFly, or domain-event design** — redirect such requests to `hmcts-sdlc-orchestrator`.
- The HMCTS templates are the master source: use `springboot-api-from-template` /
  `springboot-service-from-template` — do not scaffold build files, Dockerfile, or logback
  config from scratch.
- **Write an ADR before proceeding whenever any of these is true** (not just template
  deviations):
  - A contract change is anything other than strictly additive (breaking, or the
    versioning call is ambiguous) — see `contract-compatibility-analyzer`
  - A deviation from the reference toolchain: HMCTS templates, generator settings,
    Pact/Testcontainers/WireMock for tests, `RestClient` for HTTP, PMD/CodeQL/gitleaks for
    quality/security
  - A new service-boundary or data-ownership question — would this service read/write
    another service's database or table
  - A `@Value` feature toggle is expected to outlive one release cycle (flag-debt risk —
    see `feature-flag-auditor`)
  - Confidence in the decision is low, for any other reason
- OpenAPI **3.1.0** for new specs; media-type + SemVer versioning; additive (backwards-compatible) evolution.
- `@JsonInclude(NON_NULL)` must be present in `additionalModelTypeAnnotations` (see `context/api-spec-shared.md`).
- No internal HMCTS domains in any spec (CI rejects them).
- Do not store PII, case data, or court reference numbers in artefacts or prompts.
- Azure integrations use the Azure SDK via Managed Identity — no connection strings, SAS tokens, or account keys in code, config, env vars, or Helm values.