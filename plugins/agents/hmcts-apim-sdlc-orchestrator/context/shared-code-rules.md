Keep replies extremely concise. No filler.

## Code Rules (non-negotiable)

- No comments unless the WHY is genuinely non-obvious (hidden constraint, workaround, surprising invariant). Never explain WHAT the code does.
- No multi-line comment blocks or docstrings.
- No error handling for scenarios that cannot happen. Trust internal code and framework guarantees. Only validate at real system boundaries (user input, external APIs).
- No features, refactoring, or abstractions beyond what the task requires. Three similar lines > premature abstraction.
- No half-finished implementations. No TODOs left in code.
- No feature flags or fallbacks for hypothetical future requirements.
- Bug fix = fix the bug only. Do not clean up surroundings.

## Error handling log levels

- `ERROR` — unexpected failures requiring human attention
- `WARN` — expected business errors, degraded dependencies, retries exhausted
- `INFO` — lifecycle events, state transitions, idempotency skips (mandatory — see `service-shared.md`)
- Never log PII, secrets, JWTs, full request/response bodies, or stack traces in HTTP responses

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
| `HttpServerErrorException` | passthrough | `ERROR` | upstream 5xx via RestTemplate |
| `HttpClientErrorException` | passthrough | `WARN` | upstream 4xx via RestTemplate |
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
