---
name: review-pr
description: Review a pull request for a CP repository. Use when asked to review a PR, check code changes, or provide feedback on a pull request.
---

# PR Review for Common Platform

Reviews pull requests against CP coding standards, architectural patterns, and platform conventions.

## When to Use

- User asks to "review this PR", "check this pull request", "review PR #123"
- User pastes a PR URL or number
- User asks for feedback on changes before creating a PR

## Process

### Step 1: Gather Changes

If given a PR URL or number:
```bash
gh pr view <number> --json title,body,files,additions,deletions,baseRefName,headRefName
gh pr diff <number>
```

If reviewing local changes:
```bash
git diff main...HEAD
git log main..HEAD --oneline
```

### Step 2: Identify Repo Type

Determine the repo type from the directory name and build files:
- `cpp-context-*` with `pom.xml` → Legacy context service (Maven, CQRS, Java EE)
- `cpp-mbd-*` with `build.gradle` → Modern by Default service (Gradle, Spring Boot)
- `cpp-ui-*` with `package.json` → Angular UI application
- `cpp-terraform-*` with `*.tf` → Terraform module
- `cpp-helm-chart` → Helm chart changes
- `cp-c4-architecture` with `.c4` files → Architecture model changes
- `cpp-ui-e2e-serenity` with `serenity.properties` → UI E2E test repo (Serenity BDD + Cucumber)
- `cpp-apitests` with `api-integration-test/` → API integration test repo (JUnit 5 + REST Assured)

### Step 3: Apply Repo-Specific Review Criteria

#### Context Services (Maven/CQRS)
- [ ] Commands produce domain events (not direct state mutation)
- [ ] Queries are read-only (no state changes in query handlers)
- [ ] New viewstore entities have Liquibase migrations with rollback
- [ ] Event handlers are idempotent
- [ ] JSON schemas follow naming convention: `{context}.{type}.{name}.json`
- [ ] RAML API definitions are updated for new/changed endpoints
- [ ] Integration tests cover the new functionality
- [ ] No domain logic in controllers or repositories (belongs in aggregates/handlers)
- [ ] Framework interceptors not bypassed without justification

#### Modern by Default Services (Gradle/Spring Boot)
- [ ] Constructor injection used (no `@Autowired` fields)
- [ ] Java records used for DTOs and event payloads
- [ ] `@Operation` and `@ApiResponse` on controller methods
- [ ] RestClient used for outbound HTTP (not RestTemplate)
- [ ] Structured logging with MDC context (correlationId, eventId)
- [ ] E2E tests with WireMock for external service verification
- [ ] SecurityConfig reviewed for appropriate access controls
- [ ] Service Bus consumers handle poison messages gracefully

#### Angular UI Apps
- [ ] Components follow govuk-frontend design patterns
- [ ] State management uses ngrx (not component-level state for shared data)
- [ ] Tests cover component behavior (not just template rendering)
- [ ] No hardcoded API URLs (use environment configuration)
- [ ] Accessibility: WCAG 2.1 AA compliance (aria labels, keyboard navigation)
- [ ] Lazy loading for feature modules

#### Terraform Modules
- [ ] Variables have descriptions and type constraints
- [ ] Outputs documented
- [ ] State is not stored locally
- [ ] Sensitive values marked as `sensitive = true`
- [ ] Tags applied consistently
- [ ] Pre-commit hooks pass (format, validate, docs)

#### UI E2E Tests (`cpp-ui-e2e-serenity`)
- [ ] Feature file in correct `src/test/resources/features/<domain>/` folder
- [ ] Step definitions extend the relevant page object (no duplicated locators)
- [ ] New locators added to `src/test/resources/locators/custom-locators.json` (not hard-coded in Java)
- [ ] No `Thread.sleep` — explicit waits only
- [ ] Scenarios tagged for the intended pipeline profile (regression / BPO / migration / DLRM)
- [ ] No PII, court refs, or real personal data in `testdata/` or scenario examples
- [ ] `TestRunner` glue covers any new step-def package
- [ ] Steps annotated with `@Step`; cross-step state held in the Serenity session (no static fields)

#### API Integration Tests (`cpp-apitests`)
- [ ] Test class name ends `IT.java` (Failsafe convention — `*Test.java` is silently skipped)
- [ ] Extends the closest abstract base (`AbstractTest` / `ApplicationsAbstractTest` / `AuditAbstractTest` / `AuthorizationAbstractTest`)
- [ ] Reuses existing helpers (`JsonUtil`, `DbUtil`, `ApplicationUtil`, `RestAssuredFileUploadUtil`, domain helpers) and builders rather than adding new ones
- [ ] REST Assured `given().when().then()` with Hamcrest / AssertJ — no raw `assertEquals` on JSON paths
- [ ] JSON fixtures under `src/test/resources/<domain>/`; no inline payload strings
- [ ] No hard-coded bearer tokens, URLs, PII, or court refs
- [ ] Assertions align with the producing service's RAML / OpenAPI contract — see `api-contract-check`

For authoring guidance in either test repo, see `cpp-test-authoring`.

#### Architecture Model (.c4)
- [ ] Relationship titles read as natural language sentences (lowercase first letter)
- [ ] Container-level relationships (not product-level when containers exist)
- [ ] JEE microservices have `[auth]` and `[audit]` relationships
- [ ] Technology metadata present on all components
- [ ] Views updated for new elements
- [ ] `npm run build && npm run test` passes

### Step 4: Cross-Cutting Concerns

Always check regardless of repo type:

- [ ] No secrets, API keys, or credentials in code
- [ ] No hardcoded environment-specific values (use configuration)
- [ ] Breaking changes to APIs are clearly documented
- [ ] Changes are backward compatible (or migration path documented)
- [ ] Test coverage is adequate for the change
- [ ] Commit messages are meaningful

### Step 5: Generate Review

```
## PR Review: [title]

### Summary
One paragraph describing what the PR does and whether it achieves its goal.

### Findings

#### Blocking
- [issue]: description and suggested fix

#### Suggestions
- [improvement]: description and rationale

#### Positive
- [what's good]: acknowledge well-done aspects

### Verdict
APPROVE / REQUEST CHANGES / NEEDS DISCUSSION

### Test Checklist
- [ ] Unit tests pass
- [ ] Integration tests pass (if applicable)
- [ ] Manual verification steps (if applicable)
```
