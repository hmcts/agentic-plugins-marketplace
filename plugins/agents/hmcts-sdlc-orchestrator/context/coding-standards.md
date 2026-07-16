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

### Design principles (SOLID, cohesion)
- **Single Responsibility (SRP).** A class has **one reason to change** — one responsibility. A class
  that validates *and* orchestrates *and* persists *and* calls an external API is doing four jobs; split
  them. Signals a class is doing too much: its name needs "and" / `Manager` / `Helper` / `Util`; a unit
  test for it needs many unrelated mocks; you have to scroll to understand it.
- **Encapsulate each responsibility in a dedicated collaborator:**
  - **Validation** → Bean Validation constraints (`@NotNull` / a custom `ConstraintValidator`) or a
    dedicated `*Validator` class — never validation logic scattered inline through a service or controller.
  - **Persistence** → a repository.
  - **External calls** → a client / sender behind an interface (one implementation per provider/channel).
  - **Mapping / translation** → a mapper / transformer.
  - **Orchestration** → a service that *coordinates* the above collaborators and holds no low-level logic
    itself.
- **High cohesion, low coupling.** Everything in a class relates to its single purpose. Depend on
  **abstractions** at seams (inject an interface, resolved by a factory where there are several
  implementations), via constructor injection — not concrete types wired inline.
- **Open/Closed (OCP).** Add behaviour by adding a new implementation behind an existing interface (a new
  provider/channel), not by editing a growing `if`/`switch` in one class.
- **LSP / ISP / DIP.** Subtypes honour their supertype's contract; keep interfaces small and role-specific
  (callers shouldn't depend on methods they don't use); high-level policy depends on abstractions, not on
  concrete low-level classes.
- **Pragmatism, not gold-plating.** Extract a collaborator when a responsibility is *genuinely distinct*
  — do **not** fragment a cohesive class into anemic one-method classes. SRP is about reasons to change,
  not line count.

### Method size
- Methods should do one thing. If a method needs a comment to explain a section, extract that section.
- Target: ≤20 lines per method. Hard limit: 40 lines.

### Comments & Javadoc
- **Never add comments that restate the code.** Self-documenting names and extracted methods replace
  explanatory comments. Do not narrate *what* the code does.
- **Production code — minimise.** The only comment worth keeping is a short, non-obvious **why** a
  reader cannot infer from the code: a workaround, a spec/protocol quirk, or the rationale for a
  non-obvious framework annotation (e.g. why a test uses `@DirtiesContext`, why a bean is `@Primary`).
  When such a rationale is genuinely non-obvious, a one-line comment is correct — silence would be worse.
- **No javadoc on self-explanatory members** — getters/setters, obvious constructors, trivial methods,
  or anything whose name already says it. Reserve javadoc for genuinely non-obvious public API contracts.
- **Tests — zero comments, zero javadoc** (see `skills/test-authoring-conventions/`).
- **Allowed exception:** `build.gradle` dependencies each carry a one-line justification (why added /
  what it replaces) — see § Dependencies.

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
