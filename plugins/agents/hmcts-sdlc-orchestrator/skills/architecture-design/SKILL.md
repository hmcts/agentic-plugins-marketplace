---
name: architecture-design
description: Design a new CPP capability or service — choose between CQRS context service and Modern by Default patterns, define bounded contexts, events, APIs, and produce a design proposal with diagrams and trade-offs. Use when the user asks to "design", "architect", "plan the architecture of", or decide "how should we build X" for a CPP feature, service, integration, or cross-context change.
---

# Architecture Design (CPP)

Produces a design proposal for a new CPP capability that fits the platform's CQRS/Event Sourcing context-service pattern **or** the Modern by Default (MbD) Spring Boot pattern, whichever suits best. Delegates deep analysis to the `architecture-designer` agent and hands off to scaffolding skills when the user approves.

## When to Use

Triggers: "design a service for…", "how should we architect…", "what's the right pattern for…", "plan a new context/MbD service", "model this bounded context", "design the event flow for…", "cross-context design for…".

**Do not use** for:
- Implementing an already-agreed design → use `mbd-bootstrap` or `context-scaffold`.
- Reviewing an existing design/PR → use `review-pr` or `code-reviewer`.
- Writing a formal OpenSpec change → use `openspec-propose` (this skill can feed into it).

## Required Input

Ask the user (once, all at once):

1. **Problem statement** — what capability or change is needed, and why.
2. **Users / triggers** — who or what initiates the flow (UI action, external event, scheduled job, another context).
3. **Expected outcome** — what state changes, what events/notifications, what reads the UI needs.
4. **Known constraints** — deadlines, compliance, existing services to integrate with, anything off-limits.
5. **Existing context** — is there already a context service or MbD service this should live in, or is this greenfield?

If the user's message already contains enough of this, skip the questions and proceed. Do not stall on missing details you can reasonably assume — make the assumption explicit in the output.

## Workflow

### Step 1 — Frame the problem
Restate the problem in one paragraph and list your assumptions. This anchors the design and exposes misunderstandings early.

### Step 2 — Survey the platform
Before designing, read the relevant neighbours so the design fits reality:

- `grep` for existing contexts / services mentioned in the problem across `cpp-context-*` and `cpp-mbd-*`.
- Read the closest 1–2 analogous services' top-level structure (`pom.xml` / `build.gradle`, one command handler, one event schema).
- Check `cpp-platform-core-domain` for existing shared schemas you should reuse.
- Check `cp-c4-architecture` if the context is already modelled.

Do this yourself with Read/Grep/Glob for small scopes. For anything non-trivial, delegate to the `architecture-designer` agent with a self-contained brief.

### Step 3 — Apply the pattern selection rubric

| Situation | Pattern |
|---|---|
| New greenfield capability, thin domain, REST/event integration | **MbD service** (`cpp-mbd-*`) — default |
| Extension of an existing context (new command/event/projection) | **Extend context** via `context-scaffold` |
| New bounded context with rich aggregate behaviour, audit/replay critical | **New CQRS context service** — justify explicitly |
| UI-only change | `cpp-ui-*` change only |
| Cross-cutting concern | Extend `cpp-platform-libraries` / `cp-framework-libraries` |
| Shared schema/types | Extend `cpp-platform-core-domain` |

MbD is the default. A new CQRS context service is a high-bar decision — require a written justification.

### Step 4 — Produce the design
Delegate to the `architecture-designer` agent with a prompt that includes:
- The restated problem and assumptions
- The surveyed neighbours (file paths)
- Any hard constraints from the user

Ask for the full design output format defined in the agent (Summary, Pattern & Rationale, Bounded Context, Components, Contracts, Diagrams, Cross-cutting, Deployment, Risks, Alternatives, Implementation Outline, Follow-ups).

### Step 5 — Present and iterate
Show the design to the user. Call out:
- The chosen pattern in one sentence.
- One-way-door decisions.
- Any assumptions that, if wrong, would change the recommendation.

Invite the user to push back before implementation begins.

### Step 6 — Hand off
Once the user approves, recommend the next skill:

- **MbD service** → `mbd-bootstrap`
- **Extending a context** → `context-scaffold`
- **Formal change proposal** → `openspec-propose` (wrap this design as the design artifact)
- **C4 model update** → edit `cp-c4-architecture` LikeC4 sources
- **Terraform/infra** → `terraform-validate` on the relevant module

Do not auto-invoke scaffolding skills — the user confirms first.

## Output Conventions

- **Mermaid** for inline container and sequence diagrams.
- **Repo names** and **module suffixes** spelled exactly (`-command`, `-event`, `-viewstore-liquibase`, etc.).
- **Package names** correct per CLAUDE.md: `uk.gov.hmcts.cp.*` for MbD, `uk.gov.moj.cpp.*` for existing CQRS services, `uk.gov.justice.*` for legacy only.
- **Events** named as past-tense facts; **commands** as imperative present tense.
- Cite file paths with `file:line` when referencing existing code.

## Anti-Patterns to Flag

When reviewing the user's premise, push back on:

- Proposing a new context service for what is really a read-model or integration (should be MbD).
- Cross-context synchronous REST chains instead of events for state propagation.
- Shared databases across contexts.
- Breaking event schema changes (must be additive).
- New code in legacy WildFly/Java EE stacks.
- Missing idempotency on event consumers.
- Command handlers that read from projections (stale-data bugs).

## Example Invocation

User: *"We need to let defence solicitors subscribe to hearing updates for their cases and get notifications when anything changes."*

1. Frame: subscription + notification capability; cross-context (hearing → subscriptions → defence UI).
2. Survey: check `cpp-context-subscriptions`, `cpp-context-hearing`, `cpp-ui-subscriptions`, `cpp-mbd-*` for existing notification plumbing.
3. Pattern: likely **extend `cpp-context-subscriptions`** for subscription state + **new `cpp-mbd-hearing-notifications`** for the notification dispatch pipeline.
4. Delegate to `architecture-designer` for the full design with events (`HearingUpdated` consumed, `HearingNotificationDispatched` emitted), APIs, diagrams, risks.
5. Hand off: `context-scaffold` for the subscription changes; `mbd-bootstrap` for the notification service.
