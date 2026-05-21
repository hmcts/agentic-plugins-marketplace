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

### Layer Architecture & Patterns
_Apply to any layered service (HTTP or message-driven). Skip for library/spec-only repos with no runtime logic._

- [ ] (T1) Feature toggle fields declared only in the orchestrating/decision layer — not in controllers, persistence services, or domain services
- [ ] (T2) Toggle check is explicit at call-site — references the toggle field directly, not delegated to a method that returns a sentinel value
- [ ] (T3) Toggle state not encoded in data state — no null or sentinel value used to represent toggle-off; downstream code checks the toggle field directly
- [ ] (T4) Persistence and domain services are toggle-blind — no feature toggle field in any class that owns a repository or performs data access
- [ ] (T5) No feature toggle field declared in a class that never reads it
- [ ] (M1) Object construction between layers is owned by a dedicated factory or mapper — no inline builder calls in service or business logic methods
- [ ] (M2) Each factory/mapper has its own unit test covering field-by-field construction — service tests mock the factory, not its internals
- [ ] (M3) Each repository or data-access component has an integration test proving the schema matches the entity/model definition
- [ ] (V1) Input validation happens at the earliest processing boundary (controller, message handler) — not in domain or business services
- [ ] (I1) Idempotency skips (duplicate detection → early return) are visible — each skip site includes a log statement
- [ ] (N1) Test method names follow a consistent `subject_should_outcome[_when_condition]` convention — no mixed naming styles within a class

## Scoring
- Any FAIL in **Security** → **block merge, must fix**
- Any FAIL in **T3 or T4** (Layer Architecture & Patterns) → **block merge, changes requested** — toggle removal safety and domain purity are non-negotiable
- 3+ FAILs in other categories → **changes requested**
- 1–2 FAILs in other categories → **minor changes requested, can merge after fix**
- All PASS → **approved** (a human reviewer is still required for final approval)
