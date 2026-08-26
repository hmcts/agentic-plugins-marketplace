Keep replies extremely concise. No filler.

## Git commit / PR conventions

- Never append a `Co-Authored-By: Claude ...` trailer, a "🤖 Generated with Claude Code" line, or
  any other AI-attribution signature to a commit message or PR description in these repos. Write
  commit messages and PR bodies exactly as a team member would.

## Code Rules (non-negotiable)

- No comments unless the WHY is genuinely non-obvious (hidden constraint, workaround, surprising invariant). Never explain WHAT the code does.
- A comment stays within its own layer's concern. A Flyway migration comment explains why the column/table exists at the schema level (an ADR reference, a type choice) — not the application-layer mechanism that will read or write it (e.g. don't describe a Hibernate listener, an encryption library, or a caching strategy inside a `CREATE TABLE`/`ALTER TABLE` comment). Same principle applies to an OpenAPI spec description explaining a persistence-layer implementation detail. If a comment needs to describe another layer to justify itself, that's a sign it belongs in that other layer (the entity, the ADR, the design doc) instead — cross-reference it by name, don't restate it.
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
- A record/DTO with more than ~4 boolean fields gets a Lombok `@Builder` (works on records too). A
  long positional-boolean constructor call is unreadable and one silent transposition away from a
  real bug — a named `.builder()` call makes each value self-documenting at the call site. Keep the
  canonical constructor too if existing tests already construct it positionally; only the
  production call site needs to migrate.
- Name a class after what its data **is**, not the transport/infra mechanism that happened to
  produce it at one point in the pipeline. A message-body class named after the upstream trigger
  that originally fired it (e.g. a queue-consumed event class named for a pub/sub broker it passed
  through) is wrong once it's a plain queue item by the time your code sees it — name it after the
  domain event, not the infrastructure hop.
- Code that is a faithful, line-for-line port of an external/legacy system's logic must be
  identifiable as ported at three levels, not just one: (1) sub-packaged under a dedicated
  sub-package (e.g. `services/legacy/` or `services/<source-system>/`) so the "ported, not invented
  here" boundary is visible in import statements; (2) the class name itself carries a prefix or
  suffix identifying the source system, matching whatever convention already marks that source's
  data elsewhere in the repo (e.g. DB tables/entities); (3) a design-doc or code comment citing the
  legacy `file:line` it was read from. Missing any one of the three is how "is this copied from
  upstream?" ends up as a review comment instead of being obvious from the diff.
- A method/constructor parameter name must be self-descriptive and greppable, even when the
  wire-level contract uses a short name. A client method taking a date named with 1-2 characters
  (matching an equally short query param) is fine on the wire but wrong as a Java identifier —
  nobody can grep for a two-letter name in an IDE. Rename the Java parameter to something
  descriptive and keep the wire-level query-param name unchanged; they don't have to match.
- A fixed API path segment (the part after the host that never actually varies by environment,
  only the host does) is not environment config — don't put it behind `@Value("${x.path:<literal>}")`
  with a hardcoded default. That duplicates the literal in `application.yaml` AND the Java default,
  with no real configurability benefit and a real drift risk if they diverge. Make it a
  `public static final String` local to the client class that uses it instead; only the host
  (`url`) belongs in `@Value`/`application.yaml`.
- A `RestClient` bean must be built from Spring's autoconfigured `RestClient.Builder` (constructor-
  injected), never `RestClient.builder()` or `RestClient.create()` directly. The static factory
  methods bypass Spring Boot's Jackson autoconfiguration entirely — any `spring.jackson.*` property
  (e.g. `deserialization.fail-on-null-for-primitives`) silently never applies to that client's
  (de)serialization, in production or in WireMock-backed tests that mirror the same construction.
  Verify by checking whether a configured Jackson property actually takes effect in a test that
  exercises the real client construction path, not just in isolation.
- **A messaging resource name the application depends on** — whether it self-provisions the
  queue/topic (create-if-not-exists, `service-shared.md` Pattern B) or connects to one Terraform
  provisions on a shared Service Bus (`service-shared.md` Pattern C) — is not environment config;
  don't put it behind `@Value("${service-bus.queue-name}")`. Make it a `public static final
  String` constant on the properties/config class instead. Self-provisioned: the app creates the
  resource, so the name must be byte-identical across every environment or provisioning silently
  diverges from what the app connects to. Terraform-owned: the name is an infrastructure
  contract, not something the app controls, so `@Value` with a default just invites the two to
  drift apart. Either way this is the messaging-resource form of the fixed-API-path-segment rule
  above. Found on `service-cp-crime-results-pcr`: the queue name was originally `@Value`-injected
  under the self-provisioned framing; the resulting constant carried through unchanged when the
  service moved to the Terraform-provisioned pattern.
- **Service Bus redelivery/backoff shape**: a small config component holding the list of
  configured retry durations (read from a comma-separated `@Value`, e.g. `2s,4s,10s`, validated
  non-empty and non-negative in the constructor), and a separate retry-computation component
  depending on it plus `ClockService` — established by
  `service-cp-crime-hearing-results-document-subscription`, mirrored by
  `service-cp-crime-results-pcr`. The retry-computation component clamps to the last configured
  delay once the attempt number exceeds the list length, and adds that delay to the current time
  to get the next scheduled-enqueue time — the consumer calls this one method and sets the
  result directly. A domain/ingestion service may still own its own, unrelated backoff for a
  different concern (e.g. a synchronous caller's in-process blocking retry loop) — the rule is
  about not sharing that computation with the queue consumer's rescheduling logic, not banning
  backoff logic from a domain service entirely.
- **Dead-letter a malformed Service Bus message immediately** — catch the deserialization
  exception specifically (e.g. `JacksonException` for Jackson 3) around the parse call only, log
  at `ERROR` with the delivery attempt number, and call `context.deadLetter(new
  DeadLetterOptions().setDeadLetterReason("..."))` naming the payload type, then return without
  processing further. Don't let a parse failure fall through to a generic catch-all that abandons
  the message for native redelivery — every wasted attempt before native `maxDeliveryCount`
  exhaustion just delays landing in the DLQ, with a generic reason instead of naming the actual
  problem.
- Don't downgrade a well-typed field (e.g. a generated model's `LocalDate`) to a weaker type
  (`String`) early in a call chain just because a distant consumer needs the weaker type. Thread
  the real type through every intermediate method/client signature and convert only at the actual
  boundary that needs the weaker form (e.g. building a Redis cache key). Converting early loses
  type safety for every intermediate hop for no benefit — the weaker type doesn't become correct
  just because one downstream caller wants it. Found on `service-cp-crime-results-pcr`: a
  generated model's `LocalDate` field was stringified via `.toString()` right at the
  controller/consumer boundary and passed as `String` through the domain service's whole call
  chain; fixed by keeping `LocalDate` end-to-end and stringifying only at the actual boundary
  that needed it.
- A `@PostConstruct` (or any startup-time) initialisation of infrastructure the service cannot
  function without (a required message-queue consumer, a mandatory external connection) must not
  catch a broad `Exception`, log it, and return normally. Swallowing the failure leaves the app
  reporting healthy (readiness probe passes) with the critical dependency silently never started —
  worse than a failed deployment, since nothing alerts anyone. Let the exception propagate so
  Spring context startup fails and the deployment is visibly broken. Found on
  `service-cp-crime-results-pcr`: a Service Bus consumer's startup initialisation caught
  `Exception` around readiness/provisioning/processor-start and only logged — fixed by removing
  the try/catch so a Service Bus failure fails startup outright.

## PMD ruleset notes

- `AvoidCatchingGenericException`'s category is **PMD-version-dependent** — don't copy a sibling
  repo's `<exclude>` placement without checking. Confirmed under `category/java/errorprone.xml`
  for PMD 7.17.0 (this org's current version); NOT found under `category/java/bestpractices.xml`
  for that version despite older sibling repos placing it there. Placing it in the wrong category
  produces a PMD warning ("Exclude pattern ... did not match any rule in ruleset ...") and the
  exclusion silently doesn't apply — `./gradlew pmdMain` still fails on that rule. Verify placement
  by actually running `pmdMain`, not by matching an existing ruleset file. Found on
  `service-cp-crime-results-pcr`.
- `OnlyOneReturn` (`category/java/codestyle.xml`) tolerates exactly one early return per method,
  not zero — a single early-return guard clause followed by more code is fine, but adding a
  *second* early return to a method that already has one flags the earlier one. When a new guard
  clause would create a second early return, extract the code after the first return into its own
  method instead of accumulating returns in one method — each extracted method then has at most
  one early return again. This is the same "extract instead of adding a section a comment would
  need to explain" principle as the method-size rule in `hmcts-standards.md`, applied to control
  flow rather than length. Found on `service-cp-crime-results-pcr`: adding a
  malformed-payload guard clause to an existing method with one early return triggered this;
  fixed by splitting the deserialization step into its own method.

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
