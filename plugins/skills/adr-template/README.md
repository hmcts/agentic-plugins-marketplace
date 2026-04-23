# ADR Template Skill

Records architecture decisions in a consistent format (context → decision → options → consequences → compliance) so future engineers can understand and, if needed, reverse a past decision.

## Usage

Triggered automatically when you ask Claude to record an architectural decision:

```
Write an ADR for the choice to use Postgres over DynamoDB.
Record an architecture decision about switching from REST to gRPC.
Capture why we're adopting feature flags.
```

## What it produces

A Markdown ADR file at `docs/adrs/NNN-short-title-in-kebab-case.md` using the template:

- **Status** — Proposed / Accepted / Deprecated / Superseded
- **Date** — when the decision was made
- **Context** — the problem or forces at play
- **Decision** — stated positively ("We will use X")
- **Options considered** — with pros/cons
- **Consequences** — trade-offs, follow-up actions
- **Compliance notes** — regulatory or policy considerations

## Process

1. Draft the ADR before implementing the decision
2. Commit it alongside the feature branch it describes
3. Reference the ADR number in the PR description
4. If the decision is significant, surface the ADR for review before merge

## Prerequisites

None — no external tools required.

## Installation

```
/plugin install adr-template@agentic-plugins-marketplace
```
