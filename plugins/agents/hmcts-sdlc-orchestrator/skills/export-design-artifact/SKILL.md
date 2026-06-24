---
name: export-design-artifact
description: |
  Export a self-contained, night-friendly HTML artifact for a CPP pipeline stage — using the right
  template from the bundled gallery. Use whenever a decision must be made, a plan needs improving,
  or a design gap is discovered — AND always to export the implementation plan before any code is
  written. Picks the template that fits the scenario (plan, decision, comparison, architecture,
  investigation, status) and writes it to docs/pipeline/artifacts/.

  <example>
  user: "We've finished the design — get ready to implement the booking engine."
  assistant: "Before implementation starts I'll use export-design-artifact to export the implementation
  plan (template 03) to docs/pipeline/artifacts/ and surface it at the Stage 4 gate."
  </example>

  <example>
  user: "Should the move-to-past action be a new endpoint or extend the existing one?"
  assistant: "That's a decision — I'll use export-design-artifact to produce a decision record
  (template 07) weighing the options before we commit."
  </example>

  <example>
  user: "The design doesn't say how redeliveries are handled — there's a gap."
  assistant: "I'll use export-design-artifact to capture the gap as an architecture blueprint
  (template 08) / investigation dossier (template 04) and surface it for review."
  </example>
---

# Skill: Export Design Artifact

Turn a pipeline decision, plan, design gap, or comparison into a **self-contained HTML artifact**
built from a vetted template. Every CPP pipeline stage uses this skill instead of describing a
plan/decision only in chat — the artifact is the durable, reviewable record.

This is a **shared skill**: the architecture-designer, requirements-analyst, story-writer and
implementation agents all call it. It owns one job — *pick the right template and produce the file*.

---

## When you MUST export an artifact

1. **Before implementation (mandatory).** An **implementation-plan** artifact (template `03`) MUST
   exist and be surfaced at the Stage 4 human gate **before Stage 5 (Code) begins** — even when the
   design is clean and nothing is contentious. No plan artifact → do not start coding.
2. **A decision needs to be made** — any fork with consequences (pattern choice, new-vs-extend
   endpoint, schema shape, threshold). Export a decision record / comparison.
3. **A plan needs improving** — when review, a gate, or new information changes the plan, re-export
   the updated plan artifact (same file, bump the version in the marker).
4. **A design gap is discovered** — a missing contract, an unhandled failure mode, an ownership
   ambiguity. Capture it (architecture blueprint or investigation dossier) and surface it; do not
   silently proceed.

Exporting an artifact never replaces the human gate — it is what the human reviews **at** the gate.

---

## Pick the template

The gallery lives in `templates/` (bundled with this skill). Full selection guide:
`templates/README.md`. Visual index: `templates/index.html`.

| Scenario | Template file | `kind=` |
|---|---|---|
| **Implementation / delivery plan** (the mandatory pre-code artifact) | `03-implementation-plan-roadmap.html` | `report` |
| **Decision, 3+ options or weighted** | `07-decision-record-adr.html` | `report` |
| **Decision, exactly 2 options** (trade-off) | `10-comparison-versus.html` | `report` |
| **Design gap / system structure** (drawing the architecture) | `08-architecture-blueprint.html` | `report` |
| **Design gap found via debugging / RCA** (evidence → hypothesis) | `04-investigation-dossier.html` | `investigation` |
| **Event / API sequence** (order of messages across services) | `11-event-flow-signal-trace.html` | `report` |
| **User / process flow** (a human walks through it) | `05-journey-flow-swimlane.html` | `report` |
| **Migration / reversible cutover** (gates + rollback) | `06-migration-runbook.html` | `report` |
| **Status / progress dashboard** | `09-status-mission-control.html` | `dashboard` |
| **Teaching a concept** | `02-concept-explainer-aurora.html` | `report` |
| **PR review / code audit** | `01-pr-review-audit-console.html` | `report` |

Easy mix-ups (see `templates/README.md`): Decision Record vs Versus → 3+ vs exactly 2 options;
Blueprint vs Signal Trace → box layout vs order of messages; Journey vs Signal Trace → people vs
services. When two fit, prefer the one whose **hero component** answers the reader's first question.

---

## Produce the artifact

1. **Copy** the chosen template into `docs/pipeline/artifacts/` in the repo, named
   `<NNN>-<slug>.html` (e.g. `001-booking-engine-plan.html`, `002-new-vs-extend-endpoint.html`).
   Create `docs/pipeline/artifacts/` if it does not exist.
2. **Update the marker** on the first line of `<head>`: keep `<!-- claude-artifact: ... -->`, set
   `created=<today>`, `kind=` (from the table), and `project=<repo or PROJ-NNN>`. This marker is what
   `mymds` and the watcher index — do not drop it.
3. **Replace the sample content** with the real plan/decision/gap. Keep the CSS, `:root` palette and
   hero component as-is (re-tint via the `:root { --... }` variables only — never white backgrounds).
   The file must stay self-contained: no external assets beyond the template's existing font `<link>`.
4. **Surface it** — tell the user the path and, at a human gate, that this artifact is what they are
   approving. For a plan that changed, re-export to the **same** file and note the bumped version.

---

## Hard rules
- Never start Stage 5 (Code) without an implementation-plan artifact at `docs/pipeline/artifacts/`.
- Never store PII, case data, or court reference numbers in an artifact (same rule as all artefacts).
- Keep the `claude-artifact:` marker on line 1 of `<head>` so the artifact is indexable.
- Do not hand-roll a bespoke theme — start from a bundled template so artifacts stay consistent and
  offline-safe. A genuinely new scenario with no matching template is itself worth surfacing.
