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
