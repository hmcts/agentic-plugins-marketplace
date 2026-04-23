---
name: adr-template
description: Use when the user wants to record an architecture decision, document a design choice, write an ADR, or capture why a significant technical choice was made.
---

# ADR Template (Architecture Decision Record)

## Purpose
Record a significant architectural, technology, or design decision. Creates a permanent,
reviewable audit trail so a future engineer can understand — or reverse — the decision.

## When to write an ADR
- Introducing a new dependency or framework
- Choosing between two viable architectural patterns
- Deviating from an existing tech stack or coding standard
- Making a security or data-handling decision with no clear prior precedent
- Any decision a future engineer would need context to understand or reverse

## File naming
`docs/adrs/NNN-short-title-in-kebab-case.md`
NNN = three-digit sequence, starting from 001.

## Template

```markdown
# ADR-NNN: [Short title]

## Status
[Proposed | Accepted | Deprecated | Superseded by ADR-NNN]

## Date
[YYYY-MM-DD]

## Context
[What situation, constraint, or requirement prompted this decision?
What forces are at play? What is the problem being solved?]

## Decision
[What was decided? State it clearly and positively.
"We will use X" not "We considered X".]

## Options considered
| Option | Pros | Cons |
|--------|------|------|
| ...    | ...  | ...  |

## Consequences
[What are the expected outcomes — positive and negative?
What does this make easier? What does it make harder?
Any follow-up actions or tickets created?]

## Compliance notes
[Any compliance or regulatory considerations relevant to this decision.]
```

## Process
1. Draft the ADR before implementing the decision
2. Commit it to the feature branch alongside the code it describes
3. Reference the ADR number in the PR description
4. If the decision is significant, surface it for review before merge
