# Coding Standards

## Java / Spring Boot

### Naming
- Classes: PascalCase, noun or noun phrase (`HearingService`, `CaseRepository`)
- Methods: camelCase, verb or verb phrase (`submitHearing`, `findByCaseId`)
- Constants: SCREAMING_SNAKE_CASE
- Packages: lowercase, domain-first (`uk.gov.hmcts.[service].[domain]`)
- Test classes: suffix `Test` for unit, `IT` for integration (`HearingServiceTest`, `HearingControllerIT`)

### Structure (per service)
```
src/
├── main/java/uk/gov/hmcts/[service]/
│   ├── [domain]/          # Domain model and business logic
│   ├── service/           # Application services
│   ├── repository/        # Data access
│   ├── controller/        # REST controllers
│   ├── config/            # Spring configuration
│   └── exception/         # Exception types and handlers
└── test/java/uk/gov/hmcts/[service]/
    ├── unit/              # Unit tests
    ├── integration/       # Integration tests
    └── contract/          # Pact contract tests
```

### Method size
- Methods should do one thing. If a method needs a comment to explain a section, extract that section.
- Target: ≤20 lines per method. Hard limit: 40 lines.

### Error handling
- Use typed exceptions (`HearingNotFoundException extends RuntimeException`)
- Map exceptions to HTTP status in a `@ControllerAdvice` handler — not in individual controllers
- Never return a stack trace in an HTTP response body
- Log at WARN for expected business errors, ERROR for unexpected failures

### Logging
- JSON logging to stdout is mandatory for Spring Boot services. The authoritative rules are in `context/logging-standards.md` and the template config at `service-hmcts-crime-springboot-template/src/main/resources/logback.xml`. Do not maintain alternative configs.
- Use SLF4J; `logstash-logback-encoder` as the JSON encoder.
- Populate MDC with `correlationId` and `requestId` on every request.
- Never log: passwords, tokens, JWTs, full request/response bodies, PII, case party names, case reference numbers, dates of birth, Authorization/Cookie headers, or raw stack traces in HTTP responses.

### Dependencies
- Manage versions in `build.gradle` dependency constraints block — not per-dependency
- Use Spring Boot BOM for Spring dependencies — do not override versions without reason
- Every new dependency needs a comment: why it was added and what it replaces (if anything)

### Spring Boot services — template is the master source
- New Spring Boot services and API repos start from the HMCTS templates (see `context/tech-stack.md`). Use `skills/springboot-service-from-template/` and `skills/springboot-api-from-template/`.
- Do not regenerate `build.gradle`, the `gradle/*.gradle` includes, `Dockerfile`, `logback.xml`, or `.github/workflows/` locally — these belong to the template.
- Any deviation from the template's structure requires an ADR.

### Azure integrations
- Authenticate to Azure services with Managed Identity via `DefaultAzureCredential`. No connection strings, SAS tokens, or account keys in code, `application.yaml`, env vars, or Helm values. See `context/azure-sdk-guide.md`.

---

## Commit message format (Conventional Commits)

```
<type>(scope): <short summary>

[optional body — wrap at 72 chars]

[optional footer — Jira ticket, breaking change note]
```

Types: `feat`, `fix`, `test`, `refactor`, `chore`, `docs`, `ci`, `revert`

Example:
```
feat(hearing): add case reference validation on submission

Validates that case references match the expected format before
persisting to the hearing table.

PROJ-123
```

---

## Pull request hygiene
- Title must include the Jira ticket: `[PROJ-123] Add case reference validation`
- Description must include: what changed, why, how to test
- Maximum 400 lines changed per PR — split larger changes
- All conversations resolved before merge
- Branch deleted after merge
