---
name: write-acceptance-criteria
description: Use when the user wants to write, derive, or review acceptance criteria for a requirement or user story. Triggers on phrases like "write ACs for…", "turn this into Given/When/Then", or "what are the acceptance criteria for…".
---

# Write Acceptance Criteria

## Purpose
Produce well-formed, testable acceptance criteria from any requirement or story goal.

## Format
All ACs must use Given/When/Then (GWT) format:
- **Given** — the precondition or context (system state, user state, data present)
- **When** — the action or event that triggers the behaviour
- **Then** — the observable, verifiable outcome

## Rules
1. One AC = one observable outcome. Split compound outcomes into separate ACs.
2. Use concrete values where possible (`status code 200`, `"Invalid date"`, `within 3 seconds`)
   not vague language (`correctly`, `successfully`, `properly`).
3. Write from the actor's perspective — what does the user or system observe?
4. Cover: happy path, key failure modes, boundary values, and any NFR thresholds.
5. Do not reference implementation details (no method names, no CSS selectors, no DB columns).

## Templates

### Standard AC
```
Given [the system/user is in state X]
When [actor performs action Y]
Then [observable outcome Z occurs]
```

### With AND
```
Given [context A]
  And [context B]
When [action]
Then [outcome A]
  And [outcome B]
```

### Negative / failure mode
```
Given [context]
When [action with invalid/missing input]
Then [appropriate error is shown / system rejects / fallback occurs]
  And [no partial state change persists]
```

## Quality check before finalising
- [ ] Is the outcome measurable without ambiguity?
- [ ] Could a developer write an automated test directly from this AC?
- [ ] Does it cover the failure mode as well as the happy path?
- [ ] Are any NFRs (performance, accessibility) reflected where relevant?
