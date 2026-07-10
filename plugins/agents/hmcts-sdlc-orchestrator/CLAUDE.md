# HMCTS SDLC Pipeline — Orchestrator

## Project context
This is an HMCTS engineering project. All work must comply with HMCTS engineering standards,
GDS Service Manual principles, and MOJ security and accessibility requirements.

Always load the following before any pipeline stage:
- `${CLAUDE_PLUGIN_ROOT}/context/tech-stack.md`
- `${CLAUDE_PLUGIN_ROOT}/context/hmcts-standards.md`
- `${CLAUDE_PLUGIN_ROOT}/context/azure-cloud-native.md` — Cloud-Native posture and Shared Responsibility Model on Azure.
- `${CLAUDE_PLUGIN_ROOT}/context/logging-standards.md` — mandatory JSON logging for Spring Boot services.

Load on demand when relevant:
- `${CLAUDE_PLUGIN_ROOT}/context/azure-sdk-guide.md` — when working on any Azure service integration.
- `${CLAUDE_PLUGIN_ROOT}/context/cloud-adoption-rationale.md` — only when lock-in or cloud-cost objections surface, or when an ADR weighs those trade-offs. Do not auto-load.

---

## Pipeline stages

Run stages in order. Do not skip or reorder. Halt at every human gate before proceeding.

| # | Stage          | Agent file                         | Gate   |
|---|----------------|------------------------------------|--------|
| 1 | Requirements   | ${CLAUDE_PLUGIN_ROOT}/agents/requirements-analyst.md     | Human  |
| 2 | Architecture & Design | ${CLAUDE_PLUGIN_ROOT}/agents/architecture-designer.md | Human|
| 3 | User Story     | ${CLAUDE_PLUGIN_ROOT}/agents/story-writer.md             | Human  |
| 4 | Test Specs     | ${CLAUDE_PLUGIN_ROOT}/agents/test-engineer.md            | Human  |
| 5 | Code           | ${CLAUDE_PLUGIN_ROOT}/agents/implementation.md           | Auto   |
| 6 | Code Review    | ${CLAUDE_PLUGIN_ROOT}/agents/code-reviewer.md            | Human  |
| 7 | Build & Test   | ${CLAUDE_PLUGIN_ROOT}/agents/ci-orchestrator.md          | Auto   |
| 8 | Deploy Sandbox | ${CLAUDE_PLUGIN_ROOT}/agents/deployer.md                 | Human  |

### Stage-entry preconditions (ordering is enforced, not advisory)

Before starting any stage N, verify all of the following. If any fails, HALT and tell the user which
prior stage or gate is missing — never silently skip or reorder, even when the next artefact seems
obvious:
1. **Predecessor complete and approved** — the stage N-1 artefact exists at its `docs/pipeline/` path
   and the user has confirmed it past its human gate (Stage 1 has no predecessor).
2. **Handoff manifest read** — stage N-1's artefact ends with a `## Handoff to <next stage>` block;
   read every path it lists before you start. Those listed paths are your guaranteed inputs.
3. **No unresolved stage-gating open question** in this stage's scope (see Hard rules).

### Handoff manifest (carry inputs across the boundary — don't make the next stage guess)

Every stage artefact MUST end with a `## Handoff to <next stage>` section listing, as explicit repo
paths, every input the next stage needs — including sibling reference docs (interface contracts,
golden-masters, ADRs) that live outside the primary artefact. The next stage reads its inputs from
this manifest, not by guessing what exists in the repo. A required file that sits right next to the
artefact but is not named in the manifest is effectively invisible to the next stage.

### Gap back-channel (fix the source, don't carry the assumption forward)

A stage that has to ASSUME a fact, resolve an AMBIGUITY, or work around a MISSING input MUST emit a
**Handoff Gap Report** at the end of its artefact, each item tagged `ASSUMED` / `AMBIGUOUS` /
`MISSING` / `WOULD-HAVE-USED-PRIOR-ARTEFACT`. When an item belongs in an earlier artefact, route it
back: amend that earlier artefact and re-confirm its human gate before proceeding. Prefer fixing the
source over carrying an assumption downstream.

### Run mode — in-loop vs subagent (per stage; overridable)

Stages are strictly sequential and gated, so there is **no inter-stage parallelism to exploit** — a
subagent's headline advantage does not apply *between* stages (only *within* one, e.g. fanning out
parallel readers/reviewers). What makes a large feature (a rewrite, a modernisation) tractable across
sessions and people is the persisted `docs/pipeline/` artefacts plus the human gates — **each gate is a
natural session / person handoff** — not subagent isolation. So running the interactive front stages
in-loop is cheap: the gate bounds the context, and you checkpoint to an artefact before the next stage.

Choose run mode by the *nature* of the stage:

| Stage | Default run mode | Why |
|-------|------------------|-----|
| 1 Requirements, 2 Architecture & Design | **In-loop (interactive)** | Divergent, judgement-heavy, lots of clarification — a human co-designs turn by turn. Run in the main loop so `AskUserQuestion` / back-and-forth reaches the user. |
| 3 User Story | **In-loop for the slicing decision**; the write-up may be delegated | Re-slicing FRs into INVEST stories is judgement; the file write-up is mechanical. |
| 4 Test, 5 Code | **Subagent** | Convergent/generative against an approved contract; benefits from isolation, tool-scoping, and intra-stage fan-out. |
| 6 Code Review, 7 Build & Test, 8 Deploy | **Subagent + human gate** | Verify / operate; isolatable, low interaction. |

These are defaults, not locks — whoever is driving may override per invocation. **A subagent cannot
talk to the user mid-run** — it runs to completion and returns once. So any stage that needs live
confirmation must either run **in-loop**, or use the **halt-and-resume relay** (subagent returns its
questions as the final message → orchestrator relays them → `SendMessage` resumes it with the answers,
context preserved).

### Clarification gate (don't assume on ambiguity — ask, then finalise)

Human-gated stages (Requirements, Architecture & Design, User Story) MUST NOT resolve an **ambiguous
or unclear** requirement by assuming. Before finalising the artefact, surface every blocking
ambiguity as a numbered clarifying-question list and get answers:
- **In-loop:** ask directly and converge with the user *before* writing the artefact.
- **Subagent:** finish early, returning the questions as the final message; the orchestrator relays
  them and re-invokes with answers (`SendMessage`) before the artefact is written.

Distinguish **must-ask** (ambiguous, unclear, high-blast, or `[STAGE-GATING]`) from **safe default**
(unstated but conventional, low blast): ask the former; for the latter, state the assumption
explicitly in the artefact and let the human gate catch it. Anything still assumed goes in the
**Handoff Gap Report**.

**Answers are revisable — confirm before you commit, and never abort on cancel.** Do not treat the
first set of answers as final. After collecting them (via `AskUserQuestion` in-loop, or the subagent
relay), **echo the resolved decisions back** as a compact "here's what I understood" list and give the
user an explicit chance to **amend before the artefact is written** — "confirm these, or tell me which
to change" — looping until they confirm. If the user **cancels or rejects** the clarifying questions,
treat it as **pause, not abort**: the pipeline stays parked at this gate — re-present the questions
(reworded if that helps, or split into smaller batches) so the user can revisit and resubmit, rather
than proceeding on assumptions or dropping the stage. Never advance past the gate on an unconfirmed or
cancelled clarification. (The native question dialog's Submit/Cancel controls are harness-owned; this
echo-back-and-confirm loop is how the pipeline provides the "revisit and resubmit" affordance.)

---

## Shared skills (available to all agents)

Skills split across the marketplace and this repo. Install the marketplace plugins once (see the plugin README Prerequisites section) — the file paths below resolve to pointer stubs or HMCTS overlays that reference the installed plugins.

| Skill file                              | Source                            | Use when                                      |
|-----------------------------------------|-----------------------------------|-----------------------------------------------|
| ${CLAUDE_PLUGIN_ROOT}/skills/write-acceptance-criteria.md     | marketplace: `bdd-workflow`       | Deriving testable ACs from any requirement    |
| ${CLAUDE_PLUGIN_ROOT}/skills/generate-bdd-specs.md            | marketplace: `bdd-workflow`       | Writing Cucumber/Gherkin feature files        |
| ${CLAUDE_PLUGIN_ROOT}/skills/accessibility-check.md           | marketplace: `accessibility-check` + HMCTS overlay | WCAG 2.1 AA review + GOV.UK Frontend guidance |
| ${CLAUDE_PLUGIN_ROOT}/skills/review-checklist.md              | marketplace: `review-checklist` + HMCTS overlay    | Code review checklist + Spring Boot / Azure / logging |
| ${CLAUDE_PLUGIN_ROOT}/skills/adr-template.md                  | marketplace: `adr-template`       | Recording any architecture decision           |
| ${CLAUDE_PLUGIN_ROOT}/skills/springboot-service-from-template/| local (HMCTS-specific)            | Standing up a new Spring Boot service from the HMCTS template |
| ${CLAUDE_PLUGIN_ROOT}/skills/springboot-api-from-template/    | local (HMCTS-specific)            | Standing up a new HMCTS Marketplace API spec repo |
| ${CLAUDE_PLUGIN_ROOT}/skills/cpp-test-authoring/              | local (HMCTS-specific)            | Writing or extending tests in `cpp-ui-e2e-serenity` (Serenity BDD/Cucumber) or `cpp-apitests` (JUnit 5 + REST Assured) |
| ${CLAUDE_PLUGIN_ROOT}/skills/export-design-artifact/          | local (HMCTS-specific)            | Exporting a self-contained HTML artifact (plan / decision / design-gap / comparison) from the bundled template gallery — **mandatory** for the implementation plan before Stage 5 |

---

## Artefact output convention

All pipeline artefacts are written to `/docs/pipeline/` in the repo:

```
docs/pipeline/
├── requirements.md
├── user-stories/
│   └── <story-id>.md
├── test-specs/
│   └── <story-id>.feature
├── adrs/
│   └── <NNN>-<title>.md
├── artifacts/
│   └── <NNN>-<slug>.html   # HTML artifacts (plan, decision, design-gap, comparison)
└── deploy-notes.md
```

HTML artifacts are produced via `${CLAUDE_PLUGIN_ROOT}/skills/export-design-artifact/` from the bundled template gallery.
Each keeps its `<!-- claude-artifact: ... -->` marker (line 1 of `<head>`) so it is indexable, and
must be surfaced at the relevant human gate. An **implementation-plan** artifact is mandatory before
Stage 5 — see the Hard rules.

---

## Hard rules

- Never proceed past a human gate without explicit confirmation.
- Never invent requirements, ACs, or test data — flag unknowns as open questions.
- **Stage-gating open questions block the gate.** An open question tagged `[STAGE-GATING: <stage>]`
  must be resolved before that stage's gate can pass; a stage must never be reported complete on an
  assumption for a stage-gating question — halt and escalate. Security, data-retention / UK-GDPR, and
  platform-baseline-compatibility unknowns are stage-gating by default.
- Every story must have a linked Jira ticket before the test stage begins.
- All code must pass the review checklist before CI is triggered.
- Accessibility (WCAG 2.1 AA) is non-negotiable for any user-facing output.
- Do not store PII, case data, or court reference numbers in artefacts or prompts.
- If confidence in a decision is low, write an ADR and surface it for review.
- **Export an HTML artifact** (via `${CLAUDE_PLUGIN_ROOT}/skills/export-design-artifact/`) whenever a decision must be made,
  a plan needs improving, or a design gap is discovered — and **always export an implementation-plan
  artifact before Stage 5 (Code) begins**, even when the design is clean. No plan artifact at
  `docs/pipeline/artifacts/` → do not start coding.
- **Integration tests for new endpoints (backend features & bugfixes).** Any PR that adds or changes
  a REST endpoint / `@Handles` action / message-driven entry point MUST add **at least one integration
  test per new endpoint**, and the integration-test suite MUST be green when run locally — via
  `mvn clean && ./runIntegrationTests.sh` when that script exists at the repo root, otherwise the
  repo's documented IT command. Never weaken or skip an IT to go green.
- For Spring Boot services: the HMCTS templates (`service-hmcts-crime-springboot-template`, `api-hmcts-crime-template`) are the master source. Use `${CLAUDE_PLUGIN_ROOT}/skills/springboot-service-from-template/` or `${CLAUDE_PLUGIN_ROOT}/skills/springboot-api-from-template/` to adopt them — do not scaffold build files, Dockerfile, or logback config from scratch. Deviations require an ADR.
- JSON logging to stdout is mandatory for Spring Boot services. See `${CLAUDE_PLUGIN_ROOT}/context/logging-standards.md`.
- Azure integrations use the Azure SDK via Managed Identity. Connection strings, SAS tokens, and account keys are not permitted in code, config, env vars, or Helm values. See `${CLAUDE_PLUGIN_ROOT}/context/azure-sdk-guide.md`.
