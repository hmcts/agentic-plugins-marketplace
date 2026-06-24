## Logging Standards

### Mandate

All `service-cp-*` Spring Boot services **must** emit JSON-formatted log events to stdout.
This is a hard requirement — logs must be consumable by Azure Monitor, Log Analytics, and
Application Insights without transformation. Services that do not comply fail code review.

---

### Canonical configuration

Reference config: `service-hmcts-crime-springboot-template/src/main/resources/logback.xml`.

Do not fork this config. If a deviation is needed, an ADR is required.

Key elements (all present in the template — do not replace or omit):
- Appender: `ch.qos.logback.core.ConsoleAppender` to stdout
- Encoder: `net.logstash.logback.encoder.LoggingEventCompositeJsonEncoder`
- Providers (in order): `mdc`, `timestamp` (`yyyy-MM-dd HH:mm:ss.SSS`), `message`,
  `loggerName`, `threadName`, `logLevel`, `pattern` (`{"exception": "%xException{full}"}`)
- Root log level: `INFO`; increase per-package only with a reason in the commit message

---

### Required MDC fields

Populated on every request by the service's filter chain:

| Field | Source | Notes |
|---|---|---|
| `correlationId` | Inbound `X-Correlation-Id`; generated UUID if absent | Propagated on all outbound calls |
| `requestId` | Per-request identifier | Unique even when correlation ID spans a saga |
| `CLIENT_ID` | JWT claim via `ClientIdResolutionFilter` | Mandatory for all DB-backed services |

MDC must be cleared in a `finally` block at end of request — `TracingFilter` demonstrates
the pattern. Never clear MDC early; never let MDC leak between requests.

---

### Log levels

| Level | Use for |
|---|---|
| `ERROR` | Unexpected failures requiring human attention |
| `WARN` | Expected business errors, degraded dependencies, retries exhausted |
| `INFO` | Lifecycle events, significant state transitions, inbound request summary, outbound call summary, **idempotency skips** (explicit skip at INFO is mandatory — see `service-shared.md`) |
| `DEBUG` | Per-package detail for local development; never on by default in shared environments |
| `TRACE` | Off in all shared environments |

---

### Never log

- Passwords, tokens, JWTs, API keys, secrets, connection strings
- Full HTTP request or response bodies
- PII: names, email addresses, phone numbers, dates of birth, addresses
- Real case reference numbers, hearing dates, or party names
- Stack traces in outbound HTTP responses (stack traces belong in the log stream, not error payloads)
- Contents of `Authorization`, `Cookie`, or `Set-Cookie` headers

If a debugging scenario is tempting you to log one of these, redact or hash the value first.

---

### Output destination

stdout only. Kubernetes forwards it to Log Analytics / Application Insights via the
container runtime. No file appenders. No syslog. No direct HTTP shipping from the service.
App Insights agent enriches the JSON with trace context from OpenTelemetry.

---

### Validation checklist (before PR is raised)

1. `./gradlew bootRun` or `docker compose up` — hit a logged endpoint
2. Inspect stdout: each line must be valid JSON parseable by `jq`
3. Confirm `correlationId` and `requestId` appear in the MDC block
4. Confirm `CLIENT_ID` appears for DB-backed services
5. Run a failing scenario — confirm `exception` field has the full stack trace and nothing sensitive