## What Service Repos Are

`service-cp-*` repos are **runnable Spring Boot 4.0.x microservices**. Each implements one or more generated interfaces from an `api-cp-*` JAR dependency. All services run on port `4550` by default.

Two patterns exist:
- **Stateless proxy**: Controller → Service → HTTP Client to CP backend. No DB. WireMock for API tests.
- **DB-backed**: Adds PostgreSQL + Flyway + JPA entities + Azure Service Bus. Only `service-cp-crime-hearing-results-document-subscription` currently follows this pattern.

## Commands

```bash
# Build
./gradlew build                         # full build + unit/integration tests
./gradlew build -x test                 # skip all tests
./gradlew build -x apiTest              # skip API tests only (API tests need Docker; use this for faster local builds)

# Test
./gradlew test                          # unit + integration tests
./gradlew test --tests '<ClassName>'                    # single class
./gradlew test --tests '<ClassName.methodName>'         # single method
./gradlew check                         # tests + JaCoCo coverage

# Run locally (requires any needed infrastructure — DB, Service Bus — already running)
./gradlew bootRun

# Code quality
./gradlew pmdMain                       # PMD static analysis
./gradlew spotlessCheck                 # format check
./gradlew spotlessApply                 # auto-fix formatting
./gradlew jacocoTestReport              # coverage report → build/reports/jacoco/

# Code generation (only if this service depends on a local api-cp-* change)
./gradlew openApiGenerate               # regenerate from OpenAPI spec — never edit build/generated/ manually
```

### API tests

API tests run against a live Docker stack. The mechanism differs by service pattern:

- **Stateless proxy services** — `./gradlew dockerTest` (docker-compose: WireMock + app)
- **DB-backed services** — separate `apiTest/` Gradle project; run via `cd apiTest && ./build-and-run-apitest.sh` (docker-compose: PostgreSQL + Service Bus emulator + app)

Each service's `CLAUDE.md` documents which applies and the exact docker-compose commands needed to start the required infrastructure.

## Standard Source Layout

```
src/main/java/uk/gov/hmcts/cp/
  Application.java                        (@SpringBootApplication)
  config/
    AppConfig.java                        (@Configuration — @Bean RestClient)
    AppPropertiesBackend.java             (@Service — @Value backend URLs and paths)
  controllers/                            (@RestController — implements generated api-cp-* interface)
  services/                               (business logic; called by controllers)
  clients/                                (RestClient HTTP clients to CP backend)
  filters/
    TracingFilter.java                    (OncePerRequestFilter — X-Correlation-Id header)
    [ServiceSpecificFilter.java]          (auth/client-id filters where applicable)
  exceptions/
    GlobalExceptionHandler.java           (@RestControllerAdvice)
  [mappers/]                              (MapStruct — entity ↔ DTO, DB-backed services only)
  [domain/]                               (request/response DTOs)
```

## Architecture Rules

### Layer Model

Each layer has one responsibility and communicates only with the layer directly below it.

| Layer | Responsibility | Constraint |
|---|---|---|
| **Controller** | Receive HTTP; validate thoroughly; delegate to Manager or Service | No business logic; no object construction |
| **Manager** | Orchestrate multiple services; prevent bi-directional service dependencies | No direct repository calls |
| **Service** | Business logic; call clients and repositories via mappers | Never construct objects inline — delegate all construction to a mapper |
| **Mapper** | Convert objects between layers AND create any new objects | Owns all `.builder()` calls; has its own focused unit test covering field-by-field construction |
| **Repository** | JPA entity interactions | Must have a `@DataJpaTest` test proving Flyway schema matches JPA entity |
| **Client** | External HTTP calls | No business logic |

**Mapper-creates-objects rule:** Mappers do not only convert — they also create new objects. A service method must never call `.builder()` directly. This means:
- Service unit tests mock the mapper and verify the call — no `ArgumentCaptor` needed
- All construction logic is tested once in a focused mapper test

**Other layering rules:**
- **Controllers are thin**: delegate entirely to services or managers; return `ResponseEntity` only.
- **MapStruct mappers** in `src/main/java/.../mappers/` — never edit generated `*Impl` classes.
- **Error handling**: `EntityNotFoundException` for 404s; `ResponseStatusException` for business errors; `GlobalExceptionHandler` (`@RestControllerAdvice`) maps everything else.
- **Input validation**: validate at the earliest boundary — controller (`@Valid`) for HTTP flows, `ServiceBusHandlers` for Service Bus flows. Domain services must not throw `IllegalArgumentException` for input that should have been rejected upstream. Use `org.owasp.encoder.Encode.forJava()` before passing URN or case ID inputs to backend calls.
  - **Case/entity URN path params**: validate against `CASE_URN_REGEX = "^[0-9a-zA-Z]{1,30}$"` in the controller before any backend call — throw `ResponseStatusException(BAD_REQUEST, ...)` on mismatch (caught by the standard `GlobalExceptionHandler`, logged at `WARN` per the log-level rule). See `service-cp-caseadmin-case-urn-mapper`'s `CaseUrnMapperController` and `service-cp-crime-hearing`'s `HearingController` for the working pattern.
- **HTTP clients**: use `RestClient` (Spring 6+) — `RestTemplate` is banned for new code; migrate it on touch. Build URLs with `UriComponentsBuilder`. Declare `CJSCPPUID` as a default header on the `RestClient` `@Bean` in `AppConfig` so every call carries it automatically. `RestClient.retrieve()` throws `HttpClientErrorException` (4xx) and `HttpServerErrorException` (5xx) — same hierarchy as `RestTemplate`, so `GlobalExceptionHandler` handles them identically. See `service-hmcts-springboot-demo/case-urn-mapper-demo` (`CaseUrnMapperConfig`, `CaseUrnMapperClient`) for the canonical wiring pattern.

### Feature Toggle Placement

Feature toggles (`@Value`-injected booleans) are decision-layer concerns. Five rules apply — all exist to ensure that when a toggle is removed, a grep for the property key finds every place to clean up with no hidden data-state remnants.

**T1 — `@Value` toggle fields live only in orchestrating services.**
Persist/domain services and controllers must not declare `@Value` toggle fields.

**T2 — Toggle check is explicit and at call-site.**
Reference the boolean field directly before calling downstream — never delegate to a private method that returns a sentinel value.

**T3 — Switch state must not be inferred from data state.**
Do not return `null` (or any sentinel) to encode toggle-off, then null-check downstream to infer state. When the toggle is removed, null checks in data flow do not appear in a grep and survive as dead code.
```java
// WRONG — null check survives toggle removal invisibly
final UUID id = featureEnabled ? svc.save(p) : null;
if (id != null) { downstreamSvc.save(id); }

// CORRECT — both branches are findable on removal
if (featureEnabled) {
    final UUID id = svc.save(p);
    downstreamSvc.save(id);
}
```

**T4 — Persist/domain services are toggle-blind.**
Any class that owns a `Repository` must not declare any `@Value` toggle field. It does exactly what its method name says, unconditionally.

**T5 — No dead toggle fields.**
If a `@Value` toggle field is declared but never read in that class, remove it.

### Coding Patterns

- **Explicit idempotency**: when a persist method skips a duplicate (`existsBy…` → return), it must log at INFO at the skip site. Silent returns with no trace are not permitted.
- **Test naming**: all test methods follow `subject_should_doOutcome` or `subject_should_doOutcome_whenCondition`. Mixed styles within one class are not permitted.
- **No `inOrder` in unit tests**: use plain `verify` — the transaction rollback is the real safeguard and `inOrder` in one test without applying it consistently across the suite is misleading. Do not introduce it.
- **Delete scenarios belong in integration tests, not API/e2e tests**: when a delete operation needs a test, fix or extend the existing `@SpringBootTest` integration test (insert the record first, then delete) rather than adding a new API/e2e test. API tests cover happy-path flows only; adding delete-specific e2e tests inflates the suite without proportionate value.
- **Time access goes through `ClockService`, never a raw `Clock` bean**: any class needing "now" (timestamps, date comparisons, expiry checks) depends on a `ClockService` wrapper, not `java.time.Clock` directly.
  - `AppConfig` exposes exactly one bean: `ClockService clockService() { return new ClockService(Clock.systemDefaultZone()); }` — do not also expose a `Clock` bean alongside it.
  - `ClockService` itself (in `services/`) wraps a `Clock` and exposes typed accessors — `now()` returning `Instant`, `nowOffsetUTC()` returning `OffsetDateTime`; add further accessors (e.g. a `LocalDate` getter) only when a real call site needs one, following the same wrap-don't-leak pattern.
  - Tests construct `new ClockService(Clock.fixed(...))` for deterministic time — never let a test depend on the real system clock for date/time assertions.
  - Rationale: a raw injected `Clock` lets every call site repeat its own `Instant`/`LocalDate`/`OffsetDateTime` conversion logic; centralising it in one service keeps that conversion consistent and swappable in one place.

## Service Bus Integration Patterns

Not every `service-cp-*` that touches a Service Bus queue provisions it. Before generating or
reviewing Service Bus code, determine which pattern applies — inspect the service's existing
consumer code and infrastructure (Terraform) rather than assuming ownership. If infrastructure
clearly provisions the queue, treat that as authoritative; don't introduce application-side
provisioning.

**Pattern A — Common platform / query only.** No owned Service Bus resource. Don't introduce
messaging infrastructure just because another service in the estate uses it.

**Pattern B — Application-provisioned queue.** Established by
`service-cp-crime-hearing-results-document-subscription`. The service owns the queue/topic
lifecycle end to end — creation, subscription, processor. Startup-failure handling follows that
service's own established convention; see the `@PostConstruct` rule in `shared-code-rules.md`,
which only mandates fail-fast for a dependency with no fallback (a Pattern B service may
legitimately treat its own self-provisioned queue as best-effort). Implementation shape →
`shared-code-rules.md`.

**Pattern C — Terraform-provisioned shared resource.** Established by
`service-cp-crime-results-pcr`. Infrastructure owns the queue on the shared Service Bus; the
application connects and validates, never creates. There's no app-side fallback if the queue is
missing, so startup fails loudly and immediately instead of retrying past what's really an infra
problem.

| Concern | Infrastructure | Application |
|---|---|---|
| Queue existence & configuration | Owns | Validates; never mutates |
| Queue name | Infrastructure contract | Stable constant |
| Processor, message handling, retry, dead-lettering | — | Owns |

### Universal Service Bus rules (all patterns)

- Redelivery/backoff timing for a rescheduled message is computed by a dedicated
  `servicebus`-package component, never borrowed from a domain/ingestion service method — see
  `shared-code-rules.md` for the canonical shape.
- A malformed/unparseable message is a permanent failure — dead-letter it immediately, don't let
  it flow through business/completeness retry logic. Redelivery can't fix a message that will
  never parse.
- A queue/topic name the application depends on is a stable constant, never `@Value`-injected —
  for Pattern B because self-provisioning needs a byte-identical name across environments; for
  Pattern C because it's an infrastructure contract. Same conclusion, different reason — see
  `shared-code-rules.md`.

## Configuration Standards

- `application.yaml` uses `${VAR:default}` — all new env vars **must** be documented in `.envrc.example`
- Actuator base path: `/actuator`; endpoints exposed: `health`, `info`, `prometheus`
- Port: `4550` (override via `SERVER_PORT` env var)
- Backend URLs injected via `AppPropertiesBackend` — never hardcode in clients

## TracingFilter Standard

All services implement `TracingFilter extends OncePerRequestFilter`:
- Reads `X-Correlation-Id` from inbound request; generates a UUID if absent
- Sets `X-Correlation-Id` on MDC and on the response
- Skips actuator and root (`/`) paths
- Cleans up MDC in `finally` block (prevents MDC leaks between requests)

## Observability

- `@Slf4j` — INFO for business events, DEBUG for tracing details
- Micrometer → Prometheus metrics at `/actuator/prometheus`
- Azure Application Insights via `rpe.AppInsightsInstrumentationKey` env var
- `management.tracing.sampling.probability: 1.0` (100% sampling)

## Flyway Migrations (DB-backed services only)

- Location: `src/main/resources/db/migration/`
- **Naming: `V<major>.<NNN>__<description>.sql`** (e.g. `V1.001__initial_schema.sql`,
  `V1.002__add_client_table.sql`) — not flat `V1__`/`V2__`. Matches the convention already used
  by `service-cp-crime-hearing-results-document-subscription` and the
  `postgres-encrypt-demo`/`postgres-lock`/`postgres-springboot4` demos. The dotted `<NNN>` gives
  room to insert migrations later without renumbering everything already shipped; a flat
  sequence doesn't. Caught in review on `service-cp-crime-results-pcr` after 8 migrations had
  already shipped flat — renaming was still safe there only because nothing had deployed them
  to a real environment yet (no `flyway_schema_history` anywhere had those version numbers
  recorded). Don't rely on that safety net once a migration has actually run somewhere real.
- **Table/column naming reflects data provenance, not just this service's own name.** If the
  persisted data represents a shared Common Platform domain concept (case/hearing/defendant
  data sourced from CP generally), prefix tables/columns `cp_*`, not a service-specific prefix
  like the API's own name — e.g. `cp_version`/`cp_offence`, not `pcr_version`/`pcr_offence`,
  because that data is CP's, not invented by the PCR API specifically. A service-invented
  concept with no CP-wide equivalent (e.g. a subscription/client table this service alone owns)
  can still use a service-specific prefix.
- Auto-runs on `bootRun` and test startup
- All JPA entities use UUID PKs: `@GeneratedValue(strategy = GenerationType.UUID)`
- PostgreSQL 12+

### Required dependencies (DB-backed services)

`spring-boot-starter-flyway` is required alongside the raw Flyway libraries — depending on
`org.flywaydb:flyway-core`/`flyway-database-postgresql` alone compiles fine but never wires
`FlywayAutoConfiguration` into a Spring Boot 4 app, so migrations silently never run, in
production or in tests. All three go together:

```groovy
implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
implementation 'org.postgresql:postgresql'
implementation 'org.springframework.boot:spring-boot-starter-flyway'
implementation 'org.flywaydb:flyway-core'
implementation 'org.flywaydb:flyway-database-postgresql'
```

Discovered on `service-cp-crime-results-pcr`: repository tests failed with
`relation "..." does not exist` despite `spring.flyway.enabled: true` and correct migration
files — `spring-boot-starter-flyway` was simply missing.

### Database integration test pattern

**Standard: full `@SpringBootTest` + a `PostgresInitialise`-style `ApplicationContextInitializer`
against a real, externally-started Postgres — not `@DataJpaTest`/Testcontainers.** This is
`service-cp-crime-hearing-results-document-subscription`'s established pattern; adopt it rather
than reaching for `@DataJpaTest` slice tests, even though the latter is the more commonly-seen
Spring Boot idiom for this scenario elsewhere. `@DataJpaTest` was tried on
`service-cp-crime-results-pcr` and abandoned — it needs Spring Boot 4-specific test-slice
modules (`spring-boot-starter-data-jpa-test`, `spring-boot-starter-flyway-test`) this org's
services don't otherwise depend on, for no benefit over the simpler established pattern.

- `PostgresInitialise implements ApplicationContextInitializer<ConfigurableApplicationContext>`
  (test source, e.g. `integration/config/PostgresInitialise.java`): asserts a real Postgres is
  reachable at a fixed local URL (`jdbc:postgresql://localhost:5432/<dbname>`, `postgres`/`postgres`)
  before the context boots, throwing a clear `IllegalStateException` with setup instructions if
  not; then applies `TestPropertyValues` overriding `spring.datasource.*` and capping
  `spring.datasource.hikari.maximum-pool-size` (small — each cached Spring test context keeps
  its own Hikari pool open, and the default size exhausts Postgres `max_connections` once
  several contexts are cached).
- A shared abstract `IntegrationTestBase` (or a narrower `RepositoryIntegrationTestBase` for
  persistence-only tests) carries `@SpringBootTest` + `@ContextConfiguration(initializers = PostgresInitialise.class)`;
  concrete test classes extend it.
- Repository tests use `@Transactional` per test method (not per class) for automatic rollback
  — no explicit `flush()`/`clear()` needed; matches the existing test suite's convention exactly.
- `docker-compose.yml` needs a `postgres` service (`postgres:18-alpine`, fixed `POSTGRES_DB`/
  `POSTGRES_USER`/`POSTGRES_PASSWORD`, port `5432:5432`) so `docker compose up -d postgres` is
  the standard local bootstrap command — there's no self-contained fallback, unlike Testcontainers.

## Docker

- Base image: `eclipse-temurin:25-jre`
- Non-root user `app` — all Dockerfiles create and run as this user
- Entry point: `/app/startup.sh`
- AppInsights agent mounted from `lib/applicationinsights.json`
- WireMock (`wiremock/wiremock:3.6.0`) for API tests
- Real Postgres for DB integration tests — see "Database integration test pattern" above; not
  Testcontainers

## CI/CD Workflows

### Workflow files

| Workflow | Trigger | Purpose |
|---|---|---|
| `ci-draft.yml` | PR + push to main | Calls `ci-build-publish.yml`; on PR: build + tests + API tests; on push: also publish JAR + Docker + deploy to dev |
| `ci-released.yml` | GitHub Release published | Same reusable workflow; `is_release: true`; deploys to SIT (not dev) |
| `ci-build-publish.yml` | Called by draft/released | Reusable: version → build (with `composeUp`/`composeDown`) → publish JAR → push to GHCR → ACR copy (ADO 460) → deploy (ADO 434) |
| `code-analysis.yml` | PR | PMD via `pmd/pmd-github-action@v2` against `.github/pmd-ruleset.xml`; fails on any violation |
| `codeql.yml` | PR + weekly (Thu) | GitHub CodeQL (`security-extended`, Java) + OWASP ZAP DAST scan + CycloneDX SBOM |
| `secrets-scanner.yml` | PR + push + weekly (Thu) | `hmcts/secrets-scanner@main` (gitleaks + custom regex) |
| `auto-merge-dependabot.yml` | Any PR | Auto-approves and merges Dependabot PRs on minor/patch bumps |

### Build mechanics in CI

The build job wraps all tests with docker-compose:
```
./gradlew composeUp
./gradlew build -DARTEFACT_VERSION=<version>   # runs unit + integration tests against live compose stack
./gradlew composeDown
```
API tests (`apiTest/build-and-run-apitest.sh`) run as a separate job after the build passes.

### Deployment pipeline (push to main / release)

```
GitHub Actions (GHA)
  ├─ Build + test (Gradle + docker-compose)
  ├─ Publish JAR → GitHub Packages + Azure Artifacts
  ├─ Build + push Docker image → GHCR (ghcr.io/<repo>:<version>)
  └─ Trigger ADO pipeline 460 (hmcts/trigger-ado-pipeline@v2)
       └─ Copies GHCR image → ACR (crmdvrepo01.azurecr.io)
            └─ ADO pipeline 434 (hmcts/action-ado-deploy@v1)
                 └─ Commits image tag to hmcts/cp-vp-aks-deploy
                      ├─ push to main  → env/dev branch  → K8-DEV-CS01-CL02
                      └─ release       → env/sit branch  → K8-SIT-CS01-CL02
```

Deployment target repo: `hmcts/cp-vp-aks-deploy`, values file: `vp-config/services_values.yml`.
Dev deployment is automatic on every push to main. SIT deployment triggers only on GitHub Release publish.

### Required secrets

`AZURE_DEVOPS_ARTIFACT_USERNAME`, `AZURE_DEVOPS_ARTIFACT_TOKEN`, `HMCTS_ADO_PAT`,
`DEPLOYMENT_APP_ID`, `DEPLOYMENT_APP_PRIVATE_KEY`, `GITLEAKS_LICENSE`, `HMCTS_CP_GITLEAKS_REGEX_INTERNAL_URL`

## Key Constraints

- **Java 25**, **Spring Boot 4.0.6+** (target; current repos range 4.0.1–4.0.6 — upgrade per cycle)
- **Jakarta EE** (not `javax`)
- `-Werror` — compiler warnings fail the build
- **RestClient** for all HTTP clients — `RestTemplate` is banned for new code; existing usages must be migrated on touch
- No direct DB access from controllers; no business logic in MapStruct mappers
- New env vars → document in `.envrc.example` before raising a PR
- `CJSCPPUID` is the standard client identity header for all CP backend calls
