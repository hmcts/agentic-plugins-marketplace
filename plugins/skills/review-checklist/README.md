# Review Checklist Skill

Structured pass/fail checklist for PR review. Forces a consistent, auditable review record across:

- **Correctness** — ACs covered, edge cases handled
- **Test quality** — coverage, real assertions, no test-only flags left in
- **Security** — no secrets, input validation, auth, no injection, dependency scan
- **Code quality** — method size, naming, TODOs, hardcoded values
- **Dependencies** — justified, deduped, licence-compatible
- **Documentation** — doc comments, README, ADRs

## Usage

Triggered automatically when you ask Claude to review a PR or apply a checklist. Examples:

```
Run the review checklist against this PR.
Apply a structured code review to these changes.
Give me a pass/fail review of the current branch.
```

## Scoring

- Any FAIL in **Security** → **block merge, must fix**
- 3+ FAILs in other categories → **changes requested**
- 1–2 FAILs in other categories → **minor changes requested, can merge after fix**
- All PASS → **approved** (human reviewer still required)

## Composes with

- [`adr-template`](../adr-template/) — referenced from the Documentation section for architectural decisions.
- [`accessibility-check`](../accessibility-check/) — invoked separately for UI changes rather than duplicated here.

## Installation

```
/plugin install review-checklist@agentic-plugins-marketplace
```

## Extending for your organisation

This is intentionally a framework-agnostic baseline. If your organisation has stack-specific checks — Spring Boot template alignment, JSON logging, Azure Managed Identity, Kubernetes probes, specific linters or scanners — layer them in a separate overlay skill in your own `.claude/skills/` directory.
