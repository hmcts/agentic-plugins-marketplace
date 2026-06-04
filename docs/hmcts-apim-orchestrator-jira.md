# JIRA — `hmcts-apim-orchestrator` epic & stories

> Companion to `hmcts-apim-orchestrator-design.md`. Format mirrors AMP-428.
> Replace `AMP-XXX` with real ticket numbers when raised.

---

## Epic — AMP-569: Build the `hmcts-apim-orchestrator` marketplace plugin (API-first SDLC)

**Summary**
Consolidate API-Marketplace Claude tooling into one standalone plugin in
`agentic-plugins-marketplace`: **reuse** `hmcts-sdlc-orchestrator` by reference, **migrate**
the API-Marketplace-unique assets out of `apim-claude-template`, **build** only the two
missing agents, and **decommission** `apim-claude-template`.

**Why**
Two tooling assets exist with different philosophies: the heavyweight CPP/CQRS
`hmcts-sdlc-orchestrator` (other team — reuse, don't modify) and the lightweight
`apim-claude-template` (this team — to be retired). API-Marketplace work
(`api-cp-*` + `service-cp-*`) needs its own gated, contract-first pipeline that reuses ~72% of
the CPP orchestrator rather than duplicating it.

**Out of scope**
- Modifying `hmcts-sdlc-orchestrator` (referenced only).
- CQRS / `cpp-context-*` work (RAML, Drools, Liquibase, events).
- UI / accessibility.
- Automated PR-time CI orchestration (future).

**Dependencies**
- `hmcts-sdlc-orchestrator` installed (provides referenced agents).
- AMP-428 (`openapi-spec-reviewer`) — already delivered, migrated by Story 2.

---

## Story 1 — Scaffold plugin & migrate APIM context  *(P0 + P1)*

**As** an APIM engineer, **I want** the `hmcts-apim-orchestrator` plugin scaffolded with the
migrated shared context, **so that** the API-Marketplace standards load automatically.

**Tasks/AC**
- [ ] Create `plugins/agents/hmcts-apim-orchestrator/` with `.claude-plugin/plugin.json`, `README.md`, `CLAUDE.md` skeleton.
- [ ] Migrate the 4 `apim-claude-template` templates into `context/` (`api-spec-shared`, `service-shared`, `shared-code-rules`, `claude-md-standards`).
- [ ] Copy the 4 guard hooks + `hooks.json`.
- [ ] Register the plugin in `marketplace.json` and `CATALOG.md`.
- [ ] Plugin installs cleanly; context auto-loads; no `../../apim-claude-template/...` paths remain.

## Story 2 — Migrate `openapi-spec-reviewer` (AMP-428) into the plugin

**Tasks/AC**
- [ ] Move `skills/openapi-spec-reviewer/` (SKILL + 4 knowledge files) into the plugin.
- [ ] Rebase knowledge-file paths from `../../apim-claude-template/...` to plugin-local.
- [ ] `/openapi-spec-reviewer` runs from the plugin; 4 lenses + readiness score intact; OAS2 rejected; parse errors handled.

## Story 3 — Author `apim-architect` agent  *(adapt `architecture-designer`)*

**Tasks/AC**
- [ ] OpenAPI-first / Modern-by-Default rubric; **zero** CQRS/RAML/Drools terms.
- [ ] Drafts the OpenAPI spec per `context/api-spec-shared.md`.
- [ ] Hands off to `openapi-spec-reviewer` for the contract-review gate.
- [ ] Produces container + sequence (Mermaid) diagrams and an implementation outline.

## Story 4 — Author `contract-test-engineer` agent  *(adapt `test-engineer`)*

**Tasks/AC**
- [ ] Pact consumer-driven contracts + Spring Boot Test + WireMock/TestContainers.
- [ ] No Serenity/UI/viewstore/embedded-Artemis content.
- [ ] Test paths and naming follow `context/service-shared.md`.

## Story 5 — Author the dual-path pipeline `CLAUDE.md`

**Tasks/AC**
- [ ] Auto-detects `api-cp-*` vs `service-cp-*` and runs the matching path.
- [ ] References CPP agents by `subagent_type` (`requirements-analyst`, `story-writer`, `implementation`, `code-reviewer`, `ci-orchestrator`, `deployer`, `helm-config-validator`).
- [ ] Enforces contract-first: blocks `service-cp-*` work without a published `api-cp-*` artefact.
- [ ] Halts at every human gate (contract review, test specs, code review, deploy).
- [ ] PR step uses existing tooling (`gh` + `conventional-commit`/`code-review`) — no bundled PR/release skill.
- [ ] Graceful fallback to inline prompts if `hmcts-sdlc-orchestrator` is not installed.

## Story 6 — Decommission `apim-claude-template`

**Tasks/AC**
- [ ] Re-point every `api-cp-*` / `service-cp-*` repo off `apim-claude-template` (`@import` removed; plugin context used instead).
- [ ] Archive `apim-claude-template`; update its README to point at the new plugin.
- [ ] No repo depends on `apim-claude-template`.

## Story 7 — End-to-end validation & docs  *(P4)*

**Tasks/AC**
- [ ] Run both paths on a real `api-cp-*` + `service-cp-*` pair.
- [ ] One clean spec scores well; one deliberately violating spec fails the right lenses.
- [ ] Service path correctly blocks without a published spec.
- [ ] `README.md` + `CATALOG.md` updated; co-install dependency documented.

## Story 8 (optional) — `api-dependency-analyzer`  *(P6)*

**Tasks/AC**
- [ ] Maps which `service-cp-*` consume which `api-cp-*` spec versions.
- [ ] Detects breaking changes between published spec versions.

---

## Suggested delivery order

`Story 1 → 2` (foundation + migration) → `3 → 4` (agents) → `5` (pipeline) →
`7` (validate) → `6` (decommission) → `8` (optional).