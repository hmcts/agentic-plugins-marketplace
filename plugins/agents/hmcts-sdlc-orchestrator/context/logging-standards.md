# Logging Standards

## Mandate
All Spring Boot services **MUST** emit JSON-formatted log events to stdout.
This is not a preference — it is a requirement so that logs are consumable by
Azure Monitor, Log Analytics, and Application Insights without transformation.

Services that do not comply fail code review.

---

## Canonical configuration

The reference config lives in the template:
`service-hmcts-crime-springboot-template/src/main/resources/logback.xml`.

Key elements (do not invent alternatives):

- Appender: `ch.qos.logback.core.ConsoleAppender` to stdout.
- Encoder: `net.logstash.logback.encoder.LoggingEventCompositeJsonEncoder`.
- Providers, in this order for readability in terminals:
  - `mdc` — contextual fields (correlation id, tenant, user id, domain ids).
  - `timestamp` — ISO-like `yyyy-MM-dd' 'HH:mm:ss.SSS`, field name `timestamp`.
  - `message` — kept near the start for skim-reading.
  - `loggerName`, `threadName`, `logLevel`.
  - `pattern` emitting `{"exception": "%xException{full}"}` for full stack
    traces on errors.

Root log level: `INFO`. Increase per-package only with a reason in the commit
message; never ship DEBUG to production unless via runtime override.

Do not fork this config into a bespoke `logback-spring.xml` unless an ADR
records why.

---

## Required MDC fields

Populated on every request via a servlet filter or Spring interceptor:

- `correlationId` — extracted from inbound `X-Correlation-Id` /
  `traceparent`; generated if absent; propagated on outbound calls.
- `requestId` — per-request identifier (unique even if the correlation id is
  shared across a saga).
- Any domain-specific identifier critical for support (e.g. `caseId` if it is
  already pseudonymised; never a real case reference).

MDC is cleared at the end of the request — the template's `TracingFilter`
demonstrates the pattern.

---

## Never log

- Passwords, tokens, JWTs, API keys, secrets, connection strings.
- Full HTTP request or response bodies.
- Personally identifiable information: names, email addresses, phone numbers,
  dates of birth, addresses.
- Real case reference numbers, hearing dates, or party names.
- Stack traces in outbound HTTP responses (stack traces belong in the log
  stream, not in error payloads returned to callers).
- Contents of Authorization, Cookie, or Set-Cookie headers.

If a debugging scenario tempts you to break one of these, redact or hash the
value before logging.

---

## Levels

- `ERROR` — unexpected failures that require human attention.
- `WARN`  — expected business errors, degraded dependencies, retries exhausted.
- `INFO`  — service lifecycle events, significant state transitions, inbound
            request summary, outbound call summary.
- `DEBUG` — detail useful during local development; gated behind per-package
            level, never on by default in higher environments.
- `TRACE` — off in all shared environments.

---

## Output destination

- stdout only. Kubernetes picks it up via the container runtime and forwards
  it to Log Analytics / Application Insights.
- No file appenders. No syslog. No direct HTTP shipping from the service.
- App Insights agent (if enabled) enriches the JSON with the trace context
  already emitted via OpenTelemetry.

---

## Validating compliance

Before a PR is marked ready:

1. Run the app locally (`./gradlew bootRun` or `docker compose up`).
2. Hit a logged endpoint and inspect stdout.
3. Confirm each line is valid JSON and parseable by `jq`.
4. Confirm `correlationId` and `requestId` appear in the MDC block.
5. Run a failing scenario and confirm the `exception` field contains the full
   stack trace and nothing sensitive.

---

## Related
- Template: `service-hmcts-crime-springboot-template/src/main/resources/logback.xml`.
- Template tracing filter: `service-hmcts-crime-springboot-template/src/main/java/.../TracingFilter.java`.
- `context/azure-cloud-native.md` — why stdout-as-event-stream is the posture.
- `context/coding-standards.md` — broader coding rules; this file is authoritative on logging.
