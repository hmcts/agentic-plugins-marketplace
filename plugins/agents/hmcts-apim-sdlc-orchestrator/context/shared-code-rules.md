Keep replies extremely concise. No filler.

## Code Rules (non-negotiable)

- No comments unless the WHY is genuinely non-obvious (hidden constraint, workaround, surprising invariant). Never explain WHAT the code does.
- No multi-line comment blocks or docstrings.
- No error handling for scenarios that cannot happen. Trust internal code and framework guarantees. Only validate at real system boundaries (user input, external APIs).
- No features, refactoring, or abstractions beyond what the task requires. Three similar lines > premature abstraction.
- No repository query methods (e.g. `findByX`, `findByY`) unless a service or test actively calls them. JpaRepository's built-ins (`save`, `findById`, `count`, `deleteAll`) are sufficient until a real use case demands more.
- When testing a `@Component` that has injected dependencies, prefer `@Spy` + `@InjectMocks` over manual constructor calls. Use `@Spy` for real collaborators where you need controlled state (e.g. `ClockService` with a fixed `Clock`), and `@InjectMocks` for the class under test — Mockito injects the spy automatically:
  ```java
  @Spy
  private ClockService clockService = new ClockService(Clock.fixed(FIXED_NOW, ZoneOffset.UTC));

  @InjectMocks
  private OnboardingMapper mapper;
  ```
  Never write `new OnboardingMapper(new ClockService(...))` inline — it couples the test to the constructor signature and bypasses Mockito's injection mechanism.
- Prefer `@Mock` field annotations over inline `mock(Foo.class)` calls inside test methods. Annotations are consistent, keep all collaborators visible at the top of the class, and reduce test method size — the test body should contain only the `when`, the call under test, and the assertion.
- Order fields in a test class chronologically: dependencies of the class under test (`@Mock`) first, then `@InjectMocks`, then any additional mocks used only as test data. This makes the injection boundary immediately visible.
- One test per code branch. A method with no conditional logic needs exactly one test — multiple tests for the same linear path add noise without adding coverage. Only add a second test when there is a second branch (e.g. null input, exception path, different return value).
- Don't add `verify(mock).method(...)` after a `when(...).thenReturn(...)` chain that already drives the final assertion. If the return value of a stub is what the test asserts on, the stub being called is already proven — an extra `verify` is redundant noise. Reserve `verify` for void methods or side-effects with no observable return value.
- Don't populate entity/object fields in tests unless the test actually asserts on them. A service-layer test verifying delegation only needs `Entity.builder().build()` (or `.id(X).build()`) — populating every field swells the test without adding signal. Full field population belongs in mapper tests where every mapping is explicitly asserted.
- Don't add a test that is already implicitly proven by another. If the Spring context starts and a round-trip save/findById passes, Flyway alignment and schema correctness are already verified — a separate "column alignment" test adds noise without adding coverage.
- No half-finished implementations. No TODOs left in code.
- No feature flags or fallbacks for hypothetical future requirements.
- Bug fix = fix the bug only. Do not clean up surroundings.

## Error handling log levels

- `ERROR` — unexpected failures requiring human attention
- `WARN` — expected business errors, degraded dependencies
- `INFO` — lifecycle events, state transitions, idempotency skips (mandatory — see `service-shared.md`)
- Never log PII, secrets, JWTs, full request/response bodies, or stack traces in HTTP responses. PII includes names, email addresses, phone numbers, dates of birth, addresses, and any other personal identifiers — when in doubt, don't log it. Safe to log: IDs, enums, organisation names, environment, API names, counts.

## Logging guidelines

- Never log anything that may contain PII or secrets
- Log non sensitive volatile environment variables at app startup to assist debugging unexpected behaviours
- Log entry points to endpoints - To ensure we can trace inbound calls if required
- Use TracingFilter to propagate X-Correlation-Id
- Use OutboundTracingInterceptor to add X-Correlation-Id on outbound client api calls
- Log outgoing client api calls - they are increased risk of failure
- Log outgoing interactions with other services such as Azure service
- Better to add logging prior to production issues rather than struggle to diagnose tricky production issues with little information

## Dependencies

- Every new dependency needs a comment in `build.gradle`: why it was added and what it replaces (if anything)
- Use the Spring Boot BOM for Spring dependencies — do not override versions without a reason
- Manage versions in the dependency constraints block, not per-dependency

## Standard GlobalExceptionHandler

Every `service-cp-*` must have `src/main/java/.../exceptions/GlobalExceptionHandler.java`
(`@RestControllerAdvice @Slf4j @AllArgsConstructor`, with `io.micrometer.tracing.Tracer` and
`ClockService` injected) on day one — not added later once an upstream error is found to leak
Spring's default error body instead of the contract's `ErrorResponse`.

Baseline handler set (stateless-proxy services) — log expected business errors (4xx) at `WARN`,
genuine failures (5xx, unhandled exceptions) at `ERROR`, per the log-level rule above:

| Exception | Status | Log level | Source |
|---|---|---|---|
| `ResponseStatusException` | passthrough | `WARN` if 4xx, else `ERROR` | explicit business-error throws |
| `HttpServerErrorException` | passthrough | `ERROR` | upstream 5xx via RestClient |
| `HttpClientErrorException` | passthrough | `WARN` | upstream 4xx via RestClient |
| `NoResourceFoundException` / `NoHandlerFoundException` | 404 | `WARN` | invalid route on this service |
| `Exception` (catch-all) | 500 | `ERROR` | anything unhandled |

Each handler builds the `ErrorResponse` via:

```java
private ErrorResponse buildErrorResponse(final String message) {
    return ErrorResponse.builder()
            .message(message)
            .timestamp(clockService.now())
            .traceId(Objects.requireNonNull(tracer.currentSpan()).context().traceId())
            .build();
}
```

Use `clockService.now()`, never raw `Instant.now()` — see the `ClockService` rule in `service-shared.md`.

Add on top only where the service actually needs it — do not pre-add unused handlers:
- Bean-validation handlers (`ConstraintViolationException`, `MethodArgumentTypeMismatchException`,
  `MethodArgumentNotValidException`, `HttpMessageNotReadableException` → 400) once any endpoint
  has a `@Valid`/constrained parameter.
- `EntityNotFoundException` → 404 for DB-backed services with a `Repository` layer.
- Custom error-code constants (`error` field values) only if the consuming team has agreed a
  machine-readable code taxonomy — otherwise leave `error`/`details` unset on `ErrorResponse`.

Every `api-cp-*` spec must declare the same `ErrorResponse` schema (`error`, `message`, `details`,
`timestamp`, `traceId`) so this handler can serve every service uniformly.

## Standard Integration Test Suite (stateless-proxy `service-cp-*`)

Every stateless-proxy `service-cp-*` must have these under `src/test/java/.../integration/` on
day one, mirroring the working pattern already in `service-cp-crime-prosecution-case-details`
and `service-cp-refdata-courthearing-courthouses` — not added later once a regression in tracing
or logging goes unnoticed for lack of a test:

| File | Verifies |
|---|---|
| `IntegrationTestBase` (abstract) | `@SpringBootTest @AutoConfigureMockMvc`, exposes `appProperties` and `mockMvc` to subclasses |
| `SpringLoggingIntegrationTest` | the JSON log line shape (`timestamp`, `logger_name`, `thread_name`, `level`, `message`, MDC fields) under a real Spring context, not just the plain-JUnit logging test |
| `TracingIntegrationTest` | `TracingFilter` propagates `traceId`/`spanId` from request headers to MDC and response headers, against whichever controller logs on receipt — **adapt the target endpoint to what the repo actually has**: don't port the literal `mockMvc.perform(get("/"))` against a `RootController` if the repo has no `RootController` (several `service-cp-*` repos don't) |
| `<Controller>IntegrationTest` | the real controller→service→client→`RestClient` stack against an in-process `WireMockServer` (port matching `CP_BACKEND_URL`'s default, typically 8081) — happy path, and a 404 from each upstream hop |

`TracingFilter` (`filters/tracing/TracingFilter.java`, `@Component extends OncePerRequestFilter`)
is a prerequisite — `TracingIntegrationTest` verifies a filter that must already exist. If a repo
is missing it (check before assuming it's there), port it alongside these tests; it's the same
class across every sibling repo.

`org.wiremock:wiremock-standalone` is the test dependency (`testImplementation`) — check the
repo's actual Jackson generation (`com.fasterxml.jackson.*` vs `tools.jackson.*`, Jackson 2 vs 3)
before copying import statements from a sibling; don't assume both repos are on the same Jackson
major version.

## Test fixture data

- Never use `UUID.randomUUID()` for test fixtures. Use fixed, deterministic `UUID.fromString(...)`
  constants — failed-assertion output stays readable and stable across reruns. Simple,
  distinguishable literals are fine (e.g. `00000000-0000-0000-0000-000000000001`,
  `99999999-9999-9999-9999-999999999999`) — no need for realistic-looking random hex.
- Don't reach for `lenient()` to silence Mockito's strict-stubbing check without first tracing
  whether the stub is genuinely exercised by the code path under test. If it is, plain `when(...)`
  is correct and `lenient()` is just hiding that the stub isn't actually unnecessary.
- Use contract-realistic fixture values for fields with a defined format, not arbitrary
  placeholders — e.g. a `caseURN` fixture should match the OpenAPI spec's example format
  (alphanumeric, no separators), not `"test-case-urn"`. A bad-form placeholder that only happens
  to pass because nothing validates it yet is a landmine for whenever input validation is added.
- Replace `ArgumentCaptor.forClass(SomeClass.class)` (raw type) with a `@Captor`-annotated field.
  Mockito infers the generic type from the field declaration, eliminating the unchecked cast and
  removing the `@SuppressWarnings("unchecked")` that was masking the compiler warning:
  ```java
  // Before — raw type, unchecked cast, suppressed warning
  @SuppressWarnings("unchecked")
  ArgumentCaptor<HttpEntity<MyRequest>> captor =
          (ArgumentCaptor<HttpEntity<MyRequest>>) ArgumentCaptor.forClass(HttpEntity.class);

  // After — type-safe, no suppression needed
  @Captor
  ArgumentCaptor<HttpEntity<MyRequest>> captor;
  ```
