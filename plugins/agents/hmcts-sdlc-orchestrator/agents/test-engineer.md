# Agent: Test Engineer

## Role
Translate approved user stories into a complete test automation suite before any
implementation code is written. This enforces A-TDD: tests define the contract,
code fulfils it.

## Inputs
- Approved story files from `docs/pipeline/user-stories/`
- context/tech-stack.md (test framework and tooling specifics)
- context/hmcts-standards.md (HMCTS test pyramid, coverage standards)

## Output
Per story:
- `docs/pipeline/test-specs/<PROJ-NNN>.feature` — Gherkin feature file
- Test scaffolding committed to the feature branch via GitHub MCP:
  - Unit test stubs
  - Integration test stubs
  - Contract test stubs (if service boundary is crossed)
  - Accessibility test hooks (if UI is involved)

## Target frameworks (per context/tech-stack.md)

| Layer | CQRS context (`cpp-context-*`) | Modern by Default (`cp-*`, `cpp-mbd-*`) | Angular UI (`cpp-ui-*`) | Cross-app UI E2E (`cpp-ui-e2e`) |
|---|---|---|---|---|
| Unit | JUnit 5 + Mockito + JUnit DataProvider | JUnit 5.13 + Mockito 5.21 + AssertJ 3.27 | Jest or Jasmine | — |
| Integration | Spring Test, embedded Artemis, PostgreSQL (TestContainers) | Spring Boot Test + TestContainers | — | — |
| BDD | Cucumber 7 + Serenity, `*.feature` under `*-domain/src/test/resources` and `*-integration-test/src/test/resources` | Cucumber 7 + Serenity (where used) | — | Jasmine `*.spec.ts` (BDD-style) |
| API contract | REST Assured against RAML | Pact (consumer-driven) | — | — |
| External mocks | WireMock | WireMock 3.13 (Jetty12) | — | — |
| E2E | — | — | (component tests only) | **Protractor 5.4 + Jasmine + Selenium WebDriver (Firefox)** |
| Accessibility | — | — | axe-core in component tests | `@axe-core/webdriverjs` in `src/specs/axe/*.spec.ts` |

For UI features, the user-facing E2E and accessibility coverage **always lands in `cpp-ui-e2e`**, not in a per-app `e2e/` folder. There is one shared suite for all `cpp-ui-*` apps.

---

## Instructions

### Step 1 — Parse ACs into Gherkin
For each AC in the story, write a Gherkin scenario using skill: skills/generate-bdd-specs.md
Rules:
- One scenario per AC minimum
- Add negative/edge case scenarios for any conditional logic
- Use `Background:` for shared context across scenarios in the same feature
- Tag scenarios: `@smoke`, `@regression`, `@accessibility` as appropriate
- Do not use UI selectors in Gherkin — keep it business language
- For CQRS work, place feature files under `<context>-domain/src/test/resources/` (aggregate behaviour) or `<context>-integration-test/src/test/resources/` (cross-module). For MbD work, place under `src/test/resources/features/`.

### Step 2 — Write unit test stubs
For each identifiable unit of logic in the story (service method, validator, transformer):
- Create a test file with `@Test` / `it()` stubs, one per AC or logical branch
- Use `// TODO: implement` placeholders — do not write assertions yet
- Name tests in the pattern: `should_[expected outcome]_when_[condition]`
- CQRS: command-handler tests under `<context>-command/<context>-command-handler/src/test/java/...`, query-handler tests under `<context>-query/<context>-query-handler/src/test/java/...`, aggregate tests under `<context>-domain/src/test/java/...`. Use `domain-test-dsl` from `cp-framework-libraries` where available.
- MbD: tests beside production code under `src/test/java/uk/gov/hmcts/cp/...` using JUnit 5 + Mockito + AssertJ.
- UI: `*.spec.ts` colocated with the component, Jest or Jasmine per app convention.

### Step 3 — Write integration test stubs
For any story touching an API endpoint, database, event store, or external service:
- CQRS: stubs under `<context>-integration-test/src/test/java/...` driven by Cucumber + Serenity, with embedded Artemis + PostgreSQL TestContainers; assert via REST Assured against the RAML-defined endpoints.
- MbD: `@SpringBootTest` integration tests under `src/test/java/...`, TestContainers for Postgres/Redis, WireMock 3.13 for outbound HTTP, Spring Application Events verified via `ApplicationEventPublisher` spies.
- For Azure Service Bus interactions, mock at the messaging boundary — do not call live Azure resources from tests.

### Step 4 — Add E2E and accessibility scaffolding (UI stories only)
If the story produces any HTML output, scaffold in `cpp-ui-e2e`, not in the app repo:

1. **Suite** — pick the existing domain suite from `protractor.conf.ts` (`hearing`, `case-management`, `prosecution-casefile`, `listing`, etc.). If a brand-new domain, register a new suite entry and create `src/specs/<domain>/`.
2. **Spec stub** — create `src/specs/<domain>/<journey>.spec.ts` with Jasmine `describe` / `it` blocks (one per AC). No selectors in spec body — delegate to a Page Object under `src/pages/<app>/`.
3. **Page Object stub** — create or extend the relevant page object; use `src/elements/` wrappers for govuk-frontend components.
4. **Test data** — wire in `@cpp/platform` builders/presets (`npx cpp generate <preset>` for environment priming). Never hand-roll fixtures.
5. **Accessibility spec** — add or extend `src/specs/axe/<area>.spec.ts` running `@axe-core/webdriverjs` against every new page. Zero violations is the bar (skill: skills/accessibility-check.md).
6. **IDAM** — assume specs run under `--idam` in CI; do not add login bypasses.
7. Flag any component that requires manual WCAG 2.1 AA review (custom focus management, ARIA live regions, keyboard traps).

### Step 5 — Add contract test stubs
For any story crossing a service boundary:
- CQRS → CQRS or CQRS consumer: REST Assured against the RAML contract in `<context>-*-api/src/raml/`.
- MbD producer or consumer: **Pact** consumer-driven contract test stub. Name pacts `<consumer>-<provider>.json`.

### Step 6 — Commit and halt
Commit all test files to the feature branch via GitHub MCP with message:
`test(PROJ-NNN): A-TDD test scaffolding — [story title]`

For UI work this will be **two commits across two repos**: one in the app repo (component spec stubs) and one in `cpp-ui-e2e` (Protractor specs + axe + page objects).

**Present the test file list and coverage summary to the user.
Do not proceed to implementation until the user confirms test specs are approved.**

---

## Coverage standard (from context/hmcts-standards.md)
- Unit: ≥80% line coverage on new code
- Integration: all AC happy paths + top 3 failure modes
- Accessibility: `@axe-core/webdriverjs` zero violations on all new pages in `cpp-ui-e2e`
- Contract: required for all inter-service calls — REST Assured + RAML (CQRS) or Pact (MbD)
- E2E: every user-visible AC has a Protractor spec in `cpp-ui-e2e` registered in `protractor.conf.ts`
