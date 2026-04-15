# Code Review Skill

Triggers a structured code review of everything on the current branch relative to `main`. Claude checks for security issues, correctness problems, performance concerns, and readability, then gives an overall merge recommendation.

## Usage

After installation, type in Claude Code:

```
/review
```

Or invoke it in natural language:

```
Review the changes on this branch.
```

## What it checks

- **Correctness** — does the logic do what it claims?
- **Security** — injection, XSS, auth bypass, secrets in code
- **Performance** — N+1 queries, blocking calls, memory leaks
- **Readability** — naming, complexity, missing context
- **Tests** — coverage of changed code, likely regressions

## Output format

```
## Must fix
- ...

## Should fix
- ...

## Nits
- ...

## Recommendation
Approve / Request changes / Needs discussion
```

## Installation

```bash
./scripts/install.sh skills/code-review
```
