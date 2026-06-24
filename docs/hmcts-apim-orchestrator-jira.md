# JIRA — `hmcts-apim-sdlc-orchestrator` epic & stories

> Companion to `hmcts-apim-orchestrator-design.md`.

---

## Epic — AMP-569: Build the `hmcts-apim-sdlc-orchestrator` marketplace plugin (API-first SDLC)

**Summary**
Consolidate API-Marketplace Claude tooling into one **fully self-contained** standalone plugin in
`agentic-plugins-marketplace`: build all pipeline agents natively for the APIM stack, migrate the
all API-Marketplace Claude tooling into one plugin.

**Why**
API-Marketplace work (`api-cp-*` + `service-cp-*`) needs its own gated, contract-first pipeline
with agents that carry accurate APIM-specific CI, deploy, and standards knowledge.

**Out of scope**
- Non-API-Marketplace services.
- UI / accessibility (no UI in API Marketplace scope).

**Dependencies**
- AMP-428 (`openapi-spec-reviewer`) — TBD, pending discussion with Samir.

---

## Story 1 — Scaffold plugin & migrate APIM context  *(P0 + P1)* ✅

**As** an APIM engineer, **I want** the `hmcts-apim-sdlc-orchestrator` plugin scaffolded with the
migrated shared context, **so that** the API-Marketplace standards load automatically.

**AC**
- [x] Create `plugins/agents/hmcts-apim-sdlc-orchestrator/` with `.claude-plugin/plugin.json`, `README.md`, `CLAUDE.md`.
- [x] Context files: `api-spec-shared`, `service-shared`, `shared-code-rules`, `claude-md-standards`.
- [x] Copy the 4 guard hooks + `hooks.json`.
- [x] Register the plugin in `marketplace.json` and `CATALOG.md`.
- [x] Plugin installs cleanly; context auto-loads via `SessionStart` hook.

---

## Story 2 — `openapi-spec-reviewer` (AMP-428)  ⏳ TBD — pending discussion with Samir

**AC**
- [ ] Agree scope and approach with Samir.
- [ ] `openapi-spec-reviewer` skill available from the plugin; 4 lenses + readiness score intact.
- [ ] OAS2 rejected; parse errors handled.

---

## Story 3 — Author `apim-architect` agent  ✅

**AC**
- [x] OpenAPI-first design; no domain events.
- [x] Drafts the OpenAPI spec per `context/api-spec-shared.md`.
- [x] Hands off to `openapi-spec-reviewer` for the contract-review gate.
- [x] Produces container + sequence (Mermaid) diagrams and an implementation outline.

---

## Story 4 — Author `contract-test-engineer` agent  ✅

**AC**
- [x] Pact consumer-driven contracts + Spring Boot Test + WireMock/TestContainers.
- [x] No Serenity/UI/viewstore/embedded-Artemis content.
- [x] Test paths and naming follow `context/service-shared.md`.

---

## Story 5 — Author the dual-path pipeline `CLAUDE.md`  ✅

**AC**
- [x] Auto-detects `api-cp-*` vs `service-cp-*` and runs the matching path.
- [x] All pipeline stages use natively-owned APIM agents.
- [x] Enforces contract-first: blocks `service-cp-*` work without a published `api-cp-*` artefact.
- [x] Halts at every human gate (contract review, test specs, code review, SIT deploy).
- [x] PR step uses existing tooling (`gh` + `conventional-commit`) — no bundled PR/release skill.

---

## Story 6 — Build APIM-specific pipeline agents  ✅

**As** an APIM engineer, **I want** pipeline agents that know the APIM stack exactly, **so that**
Claude produces correct CI, deploy, and standards guidance for `api-cp-*`/`service-cp-*` repos.

**AC**
- [x] `requirements-analyst` — Path A vs Path B detection; no accessibility NFRs; blocks service work if spec not published.
- [x] `story-writer` — stories reference specific OpenAPI endpoints; DoD uses PMD/CodeQL not SonarQube/Snyk.
- [x] `implementation` — mapper-first order; generated interface compliance; CJSCPPUID on all CP backend calls; Jakarta EE; T1–T5 feature toggle rules.
- [x] `code-reviewer` — 11-category checklist covering generated interface, layer model, toggle rules, idempotency, TracingFilter, security, PMD compliance.
- [x] `ci-orchestrator` — knows exact workflow files; GHA+ADO hybrid; PMD not SonarQube; CodeQL+DAST not Snyk; no Jenkins; no accessibility.
- [x] `deployer` — monitors ADO pipeline 460 (ACR copy) + 434 (deploy); smoke-checks `/actuator/health/readiness`; SIT via GitHub Release; explicitly does not trigger deployments.

---

## Story 7 — Expand context: HMCTS standards + logging + Azure SDK  ✅

**As** an APIM engineer, **I want** Claude to carry HMCTS cross-cutting standards in every
session, **so that** security, logging, and Azure integration guidance is always accurate.

**AC**
- [x] `hmcts-standards.md` — OFFICIAL-SENSITIVE classification, Coding in the Open, repo ownership validation, ADR triggers, DPA 2018/UK GDPR, Conventional Commits, PR hygiene, test pyramid.
- [x] `logging-standards.md` — JSON stdout mandate, MDC fields (`correlationId`, `requestId`, `CLIENT_ID`), "never log" list (passwords, JWTs, full bodies, PII), log-level guidance, PR validation checklist.
- [x] `azure-sdk-guide.md` — `DefaultAzureCredential`, Service Bus at-least-once + idempotency + DLQ, Key Vault caching, App Insights agent, Kubernetes resource limits/probes/graceful shutdown, forbidden patterns.
- [x] `hmcts-standards.md` loaded always; `logging-standards.md` and `azure-sdk-guide.md` loaded on demand.

---

## Story 8 — SessionStart automation (`bootstrap-context.sh`)  ✅

**As** an APIM engineer, **I want** Claude to automatically load the right context when I open any
`api-cp-*` or `service-cp-*` repo, **so that** I never need to run a manual setup step.

**AC**
- [x] `hooks/bootstrap-context.sh` fires on `SessionStart`; detects repo type from directory name.
- [x] Creates `.claude/CLAUDE.md` with 4 `@import` lines pointing to plugin context files.
- [x] Appends `.claude/CLAUDE.md` to `.gitignore`.
- [x] Idempotent — skips if file already contains correct imports.
- [x] Exits cleanly (no-op) for non-APIM repos.
- [x] `bootstrap-context` skill available for manual trigger or force-update.

---

## Story 9 — Re-point all repos to plugin context

**As** an APIM engineer, **I want** all `api-cp-*` and `service-cp-*` repos using this plugin's
context, **so that** the team has one canonical tooling location.

**AC**
- [ ] Every repo's `.claude/CLAUDE.md` imports from `hmcts-apim-sdlc-orchestrator/context/`.
- [ ] `SessionStart` hook verified working on each repo.
- [ ] No repo depends on stale shared template paths.

---

## Story 10 — End-to-end validation & docs

**AC**
- [ ] Run both paths on a real `api-cp-*` + `service-cp-*` pair.
- [ ] One clean spec scores well on `openapi-spec-reviewer`; one deliberately violating spec fails the right lenses.
- [ ] Service path correctly blocks without a published spec.
- [ ] `README.md` + `CATALOG.md` updated; plugin described as fully self-contained.

---

## Story 11 (optional) — `api-dependency-analyzer`  *(P6)*

**AC**
- [ ] Maps which `service-cp-*` consume which `api-cp-*` spec versions.
- [ ] Detects breaking changes between published spec versions.

---

## Story 12 (future, TBD) — `authentication-auditor`

Scope defined once the APIM authZ/authN design lands.

**AC (provisional)**
- [ ] Audit `securitySchemes` coverage and per-operation `security` in `api-cp-*` specs.
- [ ] Audit Spring Security config / OAuth2-OIDC scopes in `service-cp-*` services.
- [ ] Flag unauthenticated operations and scope gaps.

> Blocked on the in-flight authZ/authN discussions — not scheduled yet.

---

## Delivery order

`1 → 2` (foundation + migration) → `3 → 4` (new agents) → `5` (pipeline) →
`6` (APIM pipeline agents) → `7` (context expansion) → `8` (automation) →
`10` (validate) → `9` (decommission) → `11` (optional)