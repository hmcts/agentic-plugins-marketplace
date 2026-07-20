---
name: bdd-test-strategy
description: |
  BDD test strategy and anti-patterns for the CPP pipeline — decide whether a user story warrants
  acceptance (BDD) scenarios, what belongs in Gherkin versus integration/unit tests, how to organise
  feature files, and the anti-patterns to avoid (technical scenarios, end-to-end tests outside BDD,
  anemic feature files, shared-stub bleed). Use when authoring or reviewing `.feature` files, deciding
  BDD scope for a story, or setting up the MbD Cucumber harness. Consumed by the test-engineer and
  code-reviewer agents (read by path) and invokable directly.
---

# BDD test strategy (CPP)

Acceptance (BDD) tests are **orthogonal to the unit/integration pyramid — they are not a pyramid
layer.** They assert business-observable behaviour end-to-end; the pyramid asserts units and boundaries.
This skill is the single source of truth for *when* a story gets BDD, *what* goes in Gherkin, and the
*anti-patterns* that keep the two from colliding.

---

## 1. Decide BDD at the STORY level, not AC by AC

Ask one question of the story **as a whole**: does it deliver business value — any outcome observable to
a user, a calling system, or the business?

- **Yes → it MUST have at least one acceptance scenario** (happy **or** negative — whichever expresses
  that value), even when its ACs individually read as technical. A backend / messaging / integration
  story still has a business outcome (e.g. "the notification is delivered and recorded as SENT", or "an
  invalid request is rejected and nothing is persisted").
- **No externally-observable behaviour** (pure enabler / scaffold — schema-or-migration-only, build/CI
  wiring) → it may have **zero** scenarios. State that explicitly in the output.

Never conclude "no BDD" just because each AC looks like plumbing — judge the story's purpose as a whole.
Defaulting to "no BDD" on an ambiguous story is exactly the failure this rule prevents.

**If in doubt whether a story warrants BDD scenarios, HALT and ask the user — do not assume either way.**

---

## 2. What to express in Gherkin vs elsewhere

Once BDD is warranted, split by nature of the AC:

| AC nature | Home |
|---|---|
| Business-observable behaviour (delivered / rejected / recorded / routed) | **Gherkin scenario** |
| Purely technical / infrastructure (migration applies, context loads, bean wired, container starts, atomicity / transaction rollback, message settlement/ack, retry timings) | **Integration or unit test — never Gherkin** |

Business-observable → `.feature`; technical/infra → the wiring/sanity test or a boundary test.

---

## 3. Anti-patterns (do not do these)

1. **Technical scenarios in Gherkin.** No "migration applies", "context loads", "bean wired", "container
   starts", "message acked", "transaction rolls back" as scenarios. Those are integration/unit concerns.
2. **End-to-end tests outside BDD.** End-to-end behaviour is expressed **only** as BDD scenarios. Do
   **not** write a JUnit `@SpringBootTest` "end-to-end" test that boots the whole stack and drives a
   command through to its final outcome — that duplicates (or silently diverges from) a BDD scenario. The
   only non-BDD integration tests are (a) the **single** wiring/sanity test and (b) **boundary** tests
   (one per boundary, minimal dependencies). If you find yourself writing an `…EndToEndIntegrationTest`,
   it belongs in a `.feature` instead. A negative end-to-end outcome (e.g. "a missing attachment fails
   the notification and no email is sent") is a **negative BDD scenario**, not a JUnit E2E test.
3. **Anemic feature organisation.** No one-scenario-per-file fragments and no one-file-per-story. Feature
   files are **cohesive by business capability**: one file holds all scenarios for that capability,
   grouped meaningfully. Fold related ACs into one scenario with several `Then/And` steps rather than one
   scenario per AC.
4. **Duplicating boundary/unit coverage at the acceptance level.** Acceptance is orthogonal, but don't
   re-assert at the BDD level what a boundary or unit test already proves. (Overlap between a unit test
   and a BDD scenario is fine and expected — measure unit-test *duplication* only against boundary tests.)
5. **Technical language in steps.** Business language only — no UI selectors, no HTTP status codes, no
   bean/queue/table names in the Gherkin. Mechanics live in the step definitions (the glue), not the
   scenario text.
6. **Generic provider/actor naming.** Name the real collaborator so scenarios stay truthful when a second
   path is introduced — e.g. "the email is sent via **the Gov.UK Notify provider**", not "via the
   provider", so an Office 365 path later reads as a distinct scenario rather than silently overloading
   the same words.
7. **Shared-stub bleed between scenarios.** Cucumber has its own hook lifecycle — a JUnit `@BeforeEach`
   on the Spring base class does **not** fire between Cucumber scenarios. JVM-singleton stubs (WireMock
   request journal, emulator queues, DB rows) therefore leak one scenario's state into the next. Reset
   shared stub/broker state in a Cucumber `@Before`/`@After` hook (via the stub-support class's reset
   method), not a JUnit lifecycle hook. Symptom of getting this wrong: a "no X happened" assertion sees
   the *previous* scenario's X.

---

## 4. Feature-file organisation

- **Cohesive by business capability** — each file encapsulates all scenarios for that capability.
- **Enhance before you fork — read the existing feature files before creating a new one.** A story that
  extends a business flow already covered (adds an outcome, a variant, or a gate to an existing
  capability) ENHANCES that capability's file; it does **not** get a parallel file. Concretely: if a new
  scenario would repeat an existing scenario's `Given`/`When` and only add `Then`/`And` assertions, add
  those assertions to the existing scenario — and add a *new* scenario only for the genuinely new path
  (typically the negative / gated case). A new `.feature` file is warranted only for a genuinely new
  business capability. When it is arguable whether the work is a new capability or an extension of an
  existing one, **HALT and ask — do not default to a new file.** (Forking a near-duplicate feature file
  per story is anti-pattern 3.)
- Fold related ACs into one scenario with `Then/And` steps; add **negative/edge** scenarios for
  conditional business logic.
- `Background:` for shared context; tag `@smoke` / `@regression` as appropriate.
- **If feature-file or scenario organisation is at all unclear, HALT and ask the user to finalise it —
  do not guess.**

---

## 5. MbD Cucumber harness (setup)

For Modern-by-Default (`cp-*`, `cpp-mbd-*`) services: **plain Cucumber on JUnit Platform + `cucumber-spring`
— not Serenity** (validated on Spring Boot 4.1 / Java 25 with Cucumber 7.20.x). The HMCTS Spring Boot
template ships this harness — use it as-is; on an older template that lacks it, add it per below and raise
an ADR.

- **Dependencies** (`build.gradle`, `testImplementation`): `io.cucumber:cucumber-bom` + `cucumber-java`,
  `cucumber-junit-platform-engine`, `cucumber-spring`, and `org.junit.platform:junit-platform-suite`.
- **Layout** (single `test` source set): all BDD code in an `…/acceptance/` package — the JUnit-Platform
  runner and the Spring glue at the package root, step definitions in an `…/acceptance/steps/`
  sub-package; feature files under `src/test/resources/features/<capability>.feature`.
- **Runner (required for Gradle):** a `@Suite` named **`AcceptanceTest`** (`*Test` suffix so the `test`
  task discovers it under any name filter) — `@Suite`, `@IncludeEngines("cucumber")`,
  `@SelectClasspathResource("features")`. Gradle discovers tests by class, so without this suite the
  Cucumber engine never runs (features are silently skipped). One suite runs every feature once — do not
  add a second runner (the double-execution caveat is a Maven concern, not Gradle).
- **Glue config:** `src/test/resources/junit-platform.properties` →
  `cucumber.glue=uk.gov.hmcts.cp.….acceptance` (+ `cucumber.plugin=pretty, summary`). Glue scanning is
  recursive, so a single `…acceptance` entry covers the `…acceptance.steps` sub-package.
- **Spring glue:** one `@CucumberContextConfiguration` class sharing the **same** base config as the
  wiring/sanity test (`@ActiveProfiles("test")`, same Testcontainer/emulator wiring), so BDD and sanity
  boot identically. Reset shared stubs per scenario in a Cucumber `@Before` hook (see anti-pattern 7).

For **CQRS** context services (`cpp-context-*`): Cucumber 7 + Serenity, features under
`<context>-domain/src/test/resources/` or `<context>-integration-test/src/test/resources/`.

---

## 6. Step-definition glue (writing the steps)

Most Cucumber maintenance pain comes from poorly-structured glue. When authoring step definitions (in
the `…/acceptance/steps/` package):

- **No 1:1 feature→step-def class.** Organise step defs by **domain concept / capability** and **reuse**
  them across features — Cucumber resolves steps globally from the glue package. Duplicate /
  near-duplicate steps cause ambiguous-step failures and are the top maintenance cost. When a story
  extends an existing capability (§4 "enhance before you fork"), add its steps to that capability's
  existing step class and reuse its `Given`/`When`/recording steps — never spin up a parallel `…Steps`
  class, and never re-declare a step that already exists under different wording.
- **Group step classes by boundary/collaborator OR by capability — both are valid; by *feature* is the
  anti-pattern.** Because Cucumber resolves steps globally, physical layout is only for human cohesion.
  Organise each step class around the collaborator a step drives or verifies — e.g. `CommandSteps`
  (inbound message send/arrange), `GovNotifySteps` (provider verification), `NotificationRecordSteps`
  (DB assertions via a `TestRepository`), `ResultEventSteps` (result-queue assertions) — or around a
  domain capability, whichever keeps steps reusable and duplication-free. Keep boundary knowledge in the
  fluent stub services (skill: `test-stub-dsl`), so a step class stays thin even when it arranges another
  boundary. Do NOT over-fragment: a single small one-theme capability stays one class.
- **Thin, low-complexity steps.** A step delegates to a helper / fixture / stub service / the app under
  test — **no `if`/`else`/`switch`/loops or scenario logic inside step defs**. Push logic into plain
  helpers or the app.
- **Share state across step classes via a single scenario-scoped context bean**, never static fields
  (statics leak across scenarios and break parallelism). When steps are split by boundary (above), the
  shared arrange/act state (ids, the built command, the reply queue, provider references) moves into one
  `@Component @ScenarioScope` holder — this is the enabler that *makes* the split clean; each step class
  `@Autowired`s it and cucumber-spring gives them the same per-scenario instance (its default scoped
  proxy keeps the shared full-app context starting cleanly for non-Cucumber `@SpringBootTest`s). Name it
  **`ScenarioContext`** for a single-bounded-context service, or `<Domain>ScenarioState` when several
  coexist. Reset shared external stubs and drain queues in a Cucumber `@Before`/`@After` hook class
  (anti-pattern 7), not a JUnit lifecycle hook.
- **Declarative Gherkin, imperative glue** — the API/DB/messaging translation lives in the glue, not the
  `.feature`. Drive stubbed boundaries through the fluent stub services (skill: `test-stub-dsl`), not raw
  WireMock/SDK calls.
- Prefer **parameter types / data tables** over regex-heavy patterns; avoid conjunction ("And"-laden)
  mega-steps — one concern per step (`Given`/`When` arrange/act, `Then` asserts).
- **Acceptance tests drive inputs and assert outputs from hard-coded JSON fixtures, not builders/factories.**
  The command/message the scenario sends and the expected outbound payload both load from
  `src/test/resources/fixtures/…` (with `${token}` substitution for the few volatile ids). Send the raw
  fixture JSON to the boundary (e.g. the ASB queue) rather than serialising a factory-built object, and
  assert the captured request against an expected fixture with **json-unit** (`test-stub-dsl` §4b). The
  fixtures then *are* the contract the AT pins. Factories/builders remain the norm for unit and
  boundary-integration tests — this fixtures-not-factories rule is specific to acceptance (BDD) tests,
  whose whole point is to document the external contract literally.

## Relationship to the other BDD skills

- **This skill** = strategy (when/what/anti-patterns/organisation/harness).
- **`generate-bdd-specs`** (marketplace `bdd-workflow`) = mechanically turning approved ACs into Gherkin.
- **`write-acceptance-criteria`** (marketplace `bdd-workflow`) = deriving testable ACs from a requirement.

Decide scope with this skill first, then generate the Gherkin.
