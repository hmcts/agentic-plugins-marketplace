## What Service Repos Are

`service-cp-*` repos are **runnable Spring Boot 4.0.x microservices**. Each implements one or more generated interfaces from an `api-cp-*` JAR dependency. All services run on port `4550` by default.

Two patterns exist:
- **Stateless proxy**: Controller → Service → HTTP Client to CP backend. No DB. WireMock for API tests.
- **DB-backed**: Adds PostgreSQL + Flyway + JPA entities + Azure Service Bus. Only `service-cp-crime-hearing-results-document-subscription` currently follows this pattern.

## Commands

```bash
# Build
./gradlew clean build                   # full build with tests
./gradlew build -x test                 # skip tests

# Test
./gradlew test                          # unit + integration (Testcontainers starts DB automatically if needed)
./gradlew test --tests '<ClassName>'    # single class
./gradlew check                         # tests + JaCoCo coverage

# API tests (needs Docker)
./gradlew dockerTest                    # full docker-compose stack (WireMock + app, or Service Bus emulator + DB + app)

# Run locally
./gradlew bootRun                       # requires any infrastructure (DB, Service Bus) running locally

# Code quality
./gradlew pmdMain                       # PMD static analysis
./gradlew jacocoTestReport              # coverage report → build/reports/jacoco/

# Code generation (if repo depends on local api-cp-* changes)
./gradlew openApiGenerate               # regenerate from OpenAPI spec — never edit build/generated/ manually
```

## Standard Source Layout

```
src/main/java/uk/gov/hmcts/cp/
  Application.java                        (@SpringBootApplication)
  config/
    AppConfig.java                        (@Configuration — @Bean RestTemplate)
    AppPropertiesBackend.java             (@Service — @Value backend URLs and paths)
  controllers/                            (@RestController — implements generated api-cp-* interface)
  services/                               (business logic; called by controllers)
  clients/                                (RestTemplate HTTP clients to CP backend)
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
- **HTTP clients**: build URLs with `UriComponentsBuilder`; set `CJSCPPUID` header on every backend call.

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
- Naming: `V<VERSION>__<description>.sql`
- Auto-runs on `bootRun` and test startup
- All JPA entities use UUID PKs: `@GeneratedValue(strategy = GenerationType.UUID)`
- PostgreSQL 12+ (Testcontainers handles test DB automatically)

## Docker

- Base image: `eclipse-temurin:25-jre`
- Non-root user `app` — all Dockerfiles create and run as this user
- Entry point: `/app/startup.sh`
- AppInsights agent mounted from `lib/applicationinsights.json`
- WireMock (`wiremock/wiremock:3.6.0`) for API tests
- Testcontainers for DB integration tests (no manual Docker required)

## CI/CD Workflows

| Workflow | Trigger | Purpose |
|---|---|---|
| `ci-draft.yml` | PR / push to main | Build, version, publish draft to ACR |
| `ci-released.yml` | GitHub Release published | Publish release image |
| `code-analysis.yml` | PR | PMD static analysis |
| `codeql.yml` | PR + weekly | GitHub CodeQL security scan |
| `secrets-scanner.yml` / `secret-scanning.yml` | PR + push | Secret detection |

ACR target: `crmdvrepo01.azurecr.io`

## Key Constraints

- **Java 25**, **Spring Boot 4.0.6+** (target; current repos range 4.0.1–4.0.6 — upgrade per cycle)
- **Jakarta EE** (not `javax`)
- `-Werror` — compiler warnings fail the build
- **RestTemplate** for all HTTP clients (RestClient migration is planned but not yet started)
- No direct DB access from controllers; no business logic in MapStruct mappers
- New env vars → document in `.envrc.example` before raising a PR
- `CJSCPPUID` is the standard client identity header for all CP backend calls
