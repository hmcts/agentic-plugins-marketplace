---
name: review-checklist
description: Use when the user wants a structured code review checklist, a pass/fail rubric for a PR, or a consistent review record across correctness, tests, security, quality, dependencies, and docs.
---

# Code Review Checklist

## Purpose
Structured pass/fail checklist for a reviewer (human or agent). Produces a consistent,
auditable review record on every PR.

## Checklist

### Correctness
- [ ] Implementation covers every acceptance criterion in the linked story
- [ ] No obvious logical errors or off-by-one conditions
- [ ] Edge cases identified in the story are handled
- [ ] No dead code paths that are untested

### Test quality
- [ ] All new code covered by at least one test
- [ ] Unit coverage on new code meets the project's threshold
- [ ] Tests assert behaviour, not implementation detail
- [ ] No test that always passes regardless of the code under test
- [ ] No real user data or production identifiers in test data
- [ ] `@wip` / `.skip` / `.only` tags removed before merge

### Security
- [ ] No secrets, API keys, or passwords in code or comments
- [ ] Input validation on all externally supplied values
- [ ] Authentication and authorisation enforced where the story requires them
- [ ] No raw stack traces leaked in HTTP error responses
- [ ] No user-controlled input concatenated into SQL, shell, or template strings
- [ ] Dependencies scanned — no new Critical or High vulnerabilities introduced

### Code quality
- [ ] Methods are small and single-purpose (no god methods)
- [ ] Names reflect domain language from the story
- [ ] No commented-out code
- [ ] No `TODO` without a linked ticket
- [ ] No inline linting suppression without an explanatory comment
- [ ] No hardcoded environment-specific values (URLs, ports, credentials)

### Dependencies
- [ ] No new dependency introduced without a comment explaining why
- [ ] No dependency that duplicates an existing one in the project
- [ ] Licence compatible with the project's policy

### Documentation
- [ ] Public API methods have doc comments
- [ ] README updated if setup or usage steps changed
- [ ] ADR written for any significant architectural decision made (see the `adr-template` plugin)

### Accessibility (for UI changes)
If the PR touches UI, run the `accessibility-check` skill in addition to this checklist. The axe-core assertion and manual check table live there to avoid duplication.

### CP Service Patterns
_Apply only when the diff touches a `service-cp-*` repo. Skip for `api-cp-*`, `cpp-context-*`, or `cpp-apitests`._

| # | Check | Pass / Fail |
|---|-------|-------------|
| T1 | `@Value` toggle fields declared only in orchestrating services — not in controllers, persist services, or domain services | |
| T2 | Toggle check references the `@Value` boolean field directly at call-site — not delegated to a private method returning a sentinel value | |
| T3 | Switch state not inferred from data state — no null/sentinel return used to encode toggle-off; each toggle-guarded branch references the boolean field explicitly | |
| T4 | Persist/domain services are toggle-blind — no `@Value` toggle field in any class that owns a `Repository` | |
| T5 | No `@Value` toggle field declared in a class that never reads it (dead toggle field) | |
| M1 | Mapper owns ALL object construction between layers — no inline `.builder()` calls in service methods | |
| M2 | Each mapper has its own unit test covering field-by-field construction; service tests mock the mapper (no `ArgumentCaptor`) | |
| M3 | Each `Repository` has a `@DataJpaTest` test proving Flyway schema matches JPA entity | |
| V1 | Input validation at entry point (controller or `ServiceBusHandlers`) — not in downstream services | |
| I1 | Idempotency skips (`existsBy…` → return) have an INFO log at the skip site | |
| N1 | All test methods follow `subject_should_doOutcome[_whenCondition]` naming — no mixed styles within a class | |

## Scoring
- Any FAIL in **Security** → **block merge, must fix**
- Any FAIL in **T3 or T4** (CP Service Patterns) → **block merge** — toggle removal safety and domain purity are non-negotiable
- 3+ FAILs in other categories → **changes requested**
- 1–2 FAILs in other categories → **minor changes requested, can merge after fix**
- All PASS → **approved** (a human reviewer is still required for final approval)
