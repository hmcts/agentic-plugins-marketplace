## HMCTS APIM — CLAUDE.md Authoring Standards

These standards apply whenever you generate or update a `CLAUDE.md` file in an `api-cp-*` or `service-cp-*` repo. They are loaded automatically via `.claude/CLAUDE.md` so that `/init` and any manual authoring session already has this context.

---

### Golden rule

`CLAUDE.md` in each repo captures **only what is unique to that repo**. Everything already documented in the shared templates (commands, layering rules, TracingFilter, Docker standard, CI standard set, publishing, observability) must **not** be repeated here. A future reader should be able to read this file and the shared templates together with no duplication.

---

### Repo type detection

| Directory prefix | Repo type | Shared template already loaded |
|---|---|---|
| `api-cp-*` | API spec library | `api-spec-shared.md` |
| `service-cp-*` | Spring Boot service | `service-shared.md` |

---

### Required sections — `api-cp-*` repos

```markdown
## Repo: <repo-name>

<One sentence: business capability this spec serves>

**Pattern**: Pure spec-only | Hybrid (spec + implementation)
**OpenAPI spec version**: x.x.x
**OpenAPI Generator version**: x.x.x
**Spring Boot version**: x.x.x

## API Endpoint(s)

[Exact method + path + response codes from openapi-spec.yml]

## Generated Interfaces & Schema

- Schema file(s): `src/main/resources/openapi/schema/<name>.schema.json`
- Generated API interface(s): `uk.gov.hmcts.cp.openapi.api.<InterfaceName>`
- Generated models: [name — one-line purpose each]

## Domain Models

| Model | Purpose |
|---|---|

## Test Structure

| Class | What it validates |
|---|---|

## Generator Config Notes

[Deviations only — missing @JsonInclude, deprecated inputSpec syntax, non-standard packages. Or "None."]

## CI/CD Deviations

[Workflows that differ from the standard set in api-spec-shared.md. Or "Standard workflow set — no deviations."]

## Repo-Specific Notes

[HMAC security, openspec workflow, compileOnly scope, hybrid layer, multiple interfaces, key docs. Or "None."]
```

---

### Required sections — `service-cp-*` repos

```markdown
## Repo: <repo-name>

<One sentence: what this service does and which api-cp-* contract it implements>

**Pattern**: Stateless proxy | DB-backed
**Spring Boot version**: x.x.x
**Implements**: `api-cp-<name>`

## Infrastructure

| Component | Technology | Purpose |
|---|---|---|

## Source Structure

[Key classes by package — one line each on runtime behaviour only. No generated interface/model names — those live in the api-cp-* repo's CLAUDE.md.]

## Environment Variables

| Variable | Purpose | Default |
|---|---|---|

## Repo-Specific Architecture Rules

[Rules unique to this service — client ID handling, event pipeline, Service Bus toggle, auth filter, multi-backend lookup patterns. Omit rules already stated in service-shared.md.]

## Debugging

| Symptom | Cause / Fix |
|---|---|

## Repo-Specific Notes

[Test deviations, special CI workflows, docs, anything unusual. Or "None."]
```

---

### Technical debt — always flag if present

Check for these in every `api-cp-*` repo and record findings under **Generator Config Notes**:

| Signal | Where to look | What to write |
|---|---|---|
| Missing `@JsonInclude(NON_NULL)` | `gradle/openapi.gradle` → `additionalModelTypeAnnotations` | "Missing `@JsonInclude(NON_NULL)` in additionalModelTypeAnnotations — null fields will appear in JSON responses" |
| Deprecated `inputSpec =` assignment | `gradle/openapi.gradle` | "Uses deprecated `inputSpec =` assignment — migrate to `inputSpec.set(layout.projectDirectory.file(...))`" |
| OpenAPI Generator below 7.22.0 | `gradle/openapi.gradle` or `build.gradle` | "OpenAPI Generator x.x.x — target 7.22.0 per upgrade cycle" |
| Spring Boot below 4.0.6 | `build.gradle` | "Spring Boot x.x.x — target 4.0.6+ per upgrade cycle" |

---

### What not to include

Never write these into a repo `CLAUDE.md` — they are covered by the shared templates:

- Gradle build / test / publish commands
- OpenAPI Generator standard settings (`interfaceOnly`, `useTags`, `useSpringBoot3`, etc.)
- Gradle configuration module descriptions (`java.gradle`, `test.gradle`, etc.)
- Standard CI/CD workflow list and descriptions
- Publishing targets (GitHub Packages, Azure Artifacts)
- Standard source layout (`controllers/`, `services/`, `clients/`, etc.)
- Layering rules (Controller → Service → Client)
- TracingFilter behaviour
- Docker base image and non-root user pattern
- Flyway migration naming convention
- Standard observability setup (AppInsights, Prometheus, MDC)
- Java 25 / Jakarta EE constraint
- `-Werror` compiler flag behaviour

---

### Commit message

After writing or refreshing `CLAUDE.md`, commit with:

```
docs(claude): generate repo context for <repo-name>

Captures repo-specific architecture, endpoints, env vars, and debugging
patterns for Claude Code context. Shared team standards are live-imported
from hmcts-apim-sdlc-orchestrator via .claude/CLAUDE.md — only repo-unique content
lives here.
```