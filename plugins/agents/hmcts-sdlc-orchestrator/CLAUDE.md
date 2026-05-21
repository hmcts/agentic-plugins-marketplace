# HMCTS SDLC Pipeline — Orchestrator

## Project context
This is an HMCTS engineering project. All work must comply with HMCTS engineering standards,
GDS Service Manual principles, and MOJ security and accessibility requirements.

Always load the following before any pipeline stage:
- `context/tech-stack.md`
- `context/hmcts-standards.md`
- `context/azure-cloud-native.md` — Cloud-Native posture and Shared Responsibility Model on Azure.
- `context/logging-standards.md` — mandatory JSON logging for Spring Boot services.

Load on demand when relevant:
- `context/azure-sdk-guide.md` — when working on any Azure service integration.
- `context/cloud-adoption-rationale.md` — only when lock-in or cloud-cost objections surface, or when an ADR weighs those trade-offs. Do not auto-load.

---

## Pipeline stages

Run stages in order. Do not skip or reorder. Halt at every human gate before proceeding.

| # | Stage          | Agent file                         | Gate   |
|---|----------------|------------------------------------|--------|
| 1 | Requirements   | agents/requirements-analyst.md     | Human  |
| 2 | Architecture & Design | agents/architecture-designer.md | Human|
| 3 | User Story     | agents/story-writer.md             | Human  |
| 4 | Test Specs     | agents/test-engineer.md            | Human  |
| 5 | Code           | agents/implementation.md           | Auto   |
| 6 | Code Review    | agents/code-reviewer.md            | Human  |
| 7 | Build & Test   | agents/ci-orchestrator.md          | Auto   |
| 8 | Deploy Sandbox | agents/deployer.md                 | Human  |

---

## Shared skills (available to all agents)

Skills split across the marketplace and this repo. Install the marketplace plugins once (see the repo README "Prerequisite" section) — the file paths below resolve to pointer stubs or HMCTS overlays that reference the installed plugins.

| Skill file                              | Source                            | Use when                                      |
|-----------------------------------------|-----------------------------------|-----------------------------------------------|
| skills/write-acceptance-criteria.md     | marketplace: `bdd-workflow`       | Deriving testable ACs from any requirement    |
| skills/generate-bdd-specs.md            | marketplace: `bdd-workflow`       | Writing Cucumber/Gherkin feature files        |
| skills/accessibility-check.md           | marketplace: `accessibility-check` + HMCTS overlay | WCAG 2.1 AA review + GOV.UK Frontend guidance |
| skills/review-checklist.md              | marketplace: `review-checklist` + HMCTS overlay    | Code review checklist + Spring Boot / Azure / logging |
| skills/adr-template.md                  | marketplace: `adr-template`       | Recording any architecture decision           |
| skills/springboot-service-from-template/| local (HMCTS-specific)            | Standing up a new Spring Boot service from the HMCTS template |
| skills/springboot-api-from-template/    | local (HMCTS-specific)            | Standing up a new HMCTS Marketplace API spec repo |
| skills/cpp-test-authoring/              | local (HMCTS-specific)            | Writing or extending tests in `cpp-ui-e2e-serenity` (Serenity BDD/Cucumber) or `cpp-apitests` (JUnit 5 + REST Assured) |

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
└── deploy-notes.md
```

---

## Hard rules

- Never proceed past a human gate without explicit confirmation.
- Never invent requirements, ACs, or test data — flag unknowns as open questions.
- Every story must have a linked Jira ticket before the test stage begins.
- All code must pass the review checklist before CI is triggered.
- Accessibility (WCAG 2.1 AA) is non-negotiable for any user-facing output.
- Do not store PII, case data, or court reference numbers in artefacts or prompts.
- If confidence in a decision is low, write an ADR and surface it for review.
- For Spring Boot services: the HMCTS templates (`service-hmcts-crime-springboot-template`, `api-hmcts-crime-template`) are the master source. Use `skills/springboot-service-from-template/` or `skills/springboot-api-from-template/` to adopt them — do not scaffold build files, Dockerfile, or logback config from scratch. Deviations require an ADR.
- JSON logging to stdout is mandatory for Spring Boot services. See `context/logging-standards.md`.
- Azure integrations use the Azure SDK via Managed Identity. Connection strings, SAS tokens, and account keys are not permitted in code, config, env vars, or Helm values. See `context/azure-sdk-guide.md`.
