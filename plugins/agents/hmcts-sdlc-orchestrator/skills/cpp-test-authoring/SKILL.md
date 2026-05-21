---
name: cpp-test-authoring
description: Author or extend automated tests in HMCTS CPP test repos. Use when writing a new Serenity BDD/Cucumber UI scenario in cpp-ui-e2e-serenity, or a new JUnit 5 + REST Assured *IT.java in cpp-apitests, or when extending existing features, step definitions, page objects, or integration tests in those repos.
---

# CPP Test Authoring

Guides contributors through the conventions of the two HMCTS Crime Common Platform test repositories so new tests slot into existing patterns instead of forking them.

Repos covered:
- `cpp-ui-e2e-serenity` — UI end-to-end (Serenity BDD 4.x + Cucumber 6 + Selenium, Java 17, Maven)
- `cpp-apitests` — API integration tests (JUnit 5 + REST Assured, Java 17, Maven)

## When to Use

- User asks to add or extend a UI E2E test, Cucumber feature, step definition, or page object
- User asks to add or extend an API integration test (`*IT.java`)
- User asks "how do I add a test for X" while inside either repo
- Reviewing whether a proposed test follows the established pattern (defer the actual PR review to `review-pr`)

## When NOT to Use

- Authoring unit tests inside a runtime service (`cpp-context-*`, `cpp-mbd-*`) — that's part of the service's own conventions
- Writing or modifying Spring Boot service code — see `springboot-service-from-template`
- Pipeline failures — defer to `pipeline-debug`
- WCAG audits — defer to `accessibility-check`

## Prerequisites

Before writing test code:
1. Story has acceptance criteria — apply `write-acceptance-criteria` if missing
2. For UI scenarios, the Gherkin draft exists — apply `generate-bdd-specs` if missing
3. Jira ticket is linked (hard rule from `claude/CLAUDE.md`)
4. No PII, case data, or court reference numbers in any planned fixture, feature, or assertion (hard rule)

## Step 1 — Identify the Repo and Test Layer

| Repo | Layer | Marker files |
|------|-------|--------------|
| `cpp-ui-e2e-serenity` | UI E2E | `serenity.properties`, `azure-pipelines-dev01_*.yml`, `src/test/resources/features/` |
| `cpp-apitests` | API integration | `apitests-pipeline.yaml`, `api-integration-test/` module, `*IT.java` suffixed tests |

If neither marker is present, stop — you're in the wrong repo.

## Step 2 — UI E2E: Authoring a Serenity / Cucumber Test

### Directory map
```
cpp-ui-e2e-serenity/
├── src/test/java/com/
│   ├── pageobjects/         # One class per page/section; holds locators + interactions
│   ├── stepdefinitions/     # Cucumber glue; extends the relevant page object
│   └── runner/              # TestRunner.java, RetryTestRunner.java
├── src/test/resources/
│   ├── features/<domain>/   # *.feature files (Gherkin)
│   ├── locators/custom-locators.json
│   └── testdata/<domain>/
└── serenity.properties
```

### Authoring checklist
1. **Reuse first** — grep `stepdefinitions/` and `pageobjects/` for the journey before creating new classes. Duplicating a step definition is the single most common review reject.
2. **Place the feature file** under the correct `features/<domain>/` folder. Match the naming style of neighbours (`CPS`, `In-Sprint`, etc.).
3. **Tag scenarios** for the pipeline they belong in. The repo has many runner profiles:
   - `azure-pipelines-dev01_regression.yml` — main regression
   - `azure-pipelines-dev01_BPO_regression.yml` — BPO regression
   - `azure-pipelines-dev01_migration*.yml` — migration suites (vanilla / EDT / nows / ts)
   - `azure-pipeline-cdci-dlrm.yml` — DLRM
   Choose tags consistent with the existing features in the same folder.
4. **Step definitions** must `extends` the page object they exercise. Annotate steps with `@Step`. Do not hold state in static fields — use the Serenity session.
5. **Page objects** own all locator strategy. Register new locators in `src/test/resources/locators/custom-locators.json`; do not hard-code selectors in Java.
6. **Wait correctly** — use Serenity / WebDriverWait conditions. No `Thread.sleep`.
7. **Test data** goes under `src/test/resources/testdata/<domain>/`. No real names, NI numbers, URNs, or court refs — use the existing fake data pattern.
8. **Wire glue** — `TestRunner.java` declares `glue = "com.stepdefinitions"`. If you add a new package, update the runner.
9. **Local run** — `mvn clean verify -P<profile>`. Serenity report lands in `target/site/serenity/index.html`.

### Common rejects to avoid
- New page object that duplicates locators from an existing one
- Hard-coded XPath in a step definition
- `Thread.sleep(...)` instead of an explicit wait
- Feature file in the wrong domain folder so it isn't picked up by the intended pipeline tag
- Real defendant / officer / court data in `testdata/`

## Step 3 — API: Authoring a `*IT.java`

### Directory map
```
cpp-apitests/api-integration-test/src/test/
├── java/uk/gov/moj/
│   ├── AbstractTest.java                 # Root base
│   ├── ApplicationsAbstractTest.java
│   ├── AuditAbstractTest.java
│   ├── AuthorizationAbstractTest.java
│   └── test/                              # *IT.java live here
└── resources/<domain>/                    # JSON fixtures, payloads
```

### Authoring checklist
1. **File naming is load-bearing** — must end `IT.java`. Failsafe only picks up that suffix; `*Test.java` will not run in CI.
2. **Extend the closest abstract base**:
   - General API → `AbstractTest`
   - Audit assertions → `AuditAbstractTest`
   - Authorization flows → `AuthorizationAbstractTest`
   - Applications API → `ApplicationsAbstractTest`
   The base wires `@ExtendWith(TestHook.class)` and shared setup. Do not re-declare hooks.
3. **Reuse helpers and builders** before creating new ones — grep for the domain you're testing:
   - `JsonUtil`, `DbUtil`, `ApplicationUtil`, `RestAssuredFileUploadUtil`
   - Domain helpers, e.g. `CpsUnifiedSearchHelper`
   - Builders, e.g. `CpsCaseIngestionData.Builder`
4. **REST Assured pattern** — use `given().when().then()` with Hamcrest matchers or AssertJ. Avoid raw `assertEquals` on JSON paths.
5. **Fixtures** live under `src/test/resources/<domain>/`. Load via `JsonUtil`. No PII / court refs.
6. **Contract alignment** — when asserting a response shape, cross-check it against the producing service's RAML / OpenAPI. Apply `api-contract-check` if the response surface is changing.
7. **Local run** — `mvn clean verify` (Failsafe phase). Single class: `mvn verify -Dit.test=MyEndpointIT -pl api-integration-test`.

### Common rejects to avoid
- File named `*Test.java` (Failsafe skips it)
- Extending `AbstractTest` when a more specific base exists
- Inline JSON payload strings instead of resource fixtures + `JsonUtil`
- New helper class that duplicates an existing util
- Hard-coded bearer tokens or URLs — use the configured environment

## Step 4 — Pre-Commit Checklist (both repos)

- [ ] No PII / case data / court reference numbers anywhere in the diff
- [ ] Existing page objects / step defs / helpers / builders were reused, not duplicated — apply `simplify` if unsure
- [ ] (UI only) Journey passes a11y check — apply `accessibility-check`
- [ ] (API only) Assertions match the producing service's contract — apply `api-contract-check`
- [ ] ADR raised for any deviation from the patterns above — apply `adr-template`
- [ ] Test runs green locally
- [ ] Test runs green on the targeted pipeline profile

## Step 5 — When CI Fails

Defer to `pipeline-debug`. Identify the failing YAML first:
- UI: one of the `azure-pipelines*.yml` variants in `cpp-ui-e2e-serenity`
- API: `apitests-pipeline.yaml` or `azure-pipelines.yaml` in `cpp-apitests`

## Step 6 — Raising the PR

When the test is ready:
1. Run `review-pr` against the diff first — it has a section for these two repos
2. If it surfaces blocking issues, fix before raising
3. Open the PR; reviewer runs `review-pr` again as part of the merge gate

## Related Skills

- `write-acceptance-criteria` — derive ACs from the story (run first)
- `generate-bdd-specs` — author the Gherkin feature (UI only)
- `accessibility-check` — WCAG 2.1 AA on user-facing journeys
- `api-contract-check` — RAML / OpenAPI alignment for `*IT.java`
- `review-pr` — PR review checklist (includes a test-repo section)
- `pipeline-debug` — CI failure diagnosis
- `simplify` — reuse and dedupe pass before commit
- `adr-template` — record any deviation from the patterns above
- `security-review` — required if touching auth, session, tokens, or PII handling
