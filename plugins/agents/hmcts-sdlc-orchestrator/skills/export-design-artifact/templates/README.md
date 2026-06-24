# Artifact Theme Gallery

Eleven self-contained, **night-friendly** HTML artifact themes — one per common job. Open `index.html` for the
visual gallery; this file is the text-only selection guide.

> All files inline their own CSS/SVG/fonts (no build step) and carry the `<!-- claude-artifact: ... -->` marker
> on the first line of `<head>` so they're indexed by `mymds`. No white backgrounds anywhere.

## The themes

| # | File | Use case | Theme | Hero design element |
|---|------|----------|-------|---------------------|
| 01 | `01-pr-review-audit-console.html` | **PR review / code audit** | Audit Console (slate + traffic-light) | Severity diff-rows, verdict scorecard, reviewer callouts |
| 02 | `02-concept-explainer-aurora.html` | **Teaching a concept** | Aurora (violet/cyan glow) | Orbit concept-viz (SVG), glossary tooltips, analogy panels |
| 03 | `03-implementation-plan-roadmap.html` | **Implementation / delivery plan** | Roadmap (teal) | Phase timeline, task checklists, gantt-style effort bars |
| 04 | `04-investigation-dossier.html` | **Debug / forensics / RCA** | Dossier (case-file charcoal) | Evidence timeline, annotated log blocks, hypothesis tree |
| 05 | `05-journey-flow-swimlane.html` | **User / process flow** | Journey (magenta→violet) | Animated flow connectors, decision diamonds, swimlanes, emotion curve |
| 06 | `06-migration-runbook.html` | **Migration / cutover** | Runbook (amber industrial) | Before→after split, numbered gates, rollback callout, risk matrix |
| 07 | `07-decision-record-adr.html` | **Decision making (3+ options)** | Decision Record (slate blue) | Options matrix, weighted score stacks, pros/cons, verdict banner |
| 08 | `08-architecture-blueprint.html` | **Architecture / system map** | Blueprint (cyan/magenta schematic) | SVG component diagram, layer bands, animated data-flow wires |
| 09 | `09-status-mission-control.html` | **Status / progress dashboard** | Mission Control (neon on near-black) | KPI cards, sparklines, progress rings, pulsing status grid |
| 10 | `10-comparison-versus.html` | **Two-way trade-off** | Versus (blue vs orange) | Contender headers, mirrored attribute bars, verdict tally |
| 11 | `11-event-flow-signal-trace.html` | **Event / API sequence** | Signal Trace (signal cyan/magenta) | Sequence lifelines, activation bars, flowing wires, traveling pulses |

## Which one — decision shortcuts

- **Reviewing code?** → Audit Console. Severity + diff is the shared review language.
- **Explaining *why* something works?** → Aurora. Spacious, visual, built to read slowly.
- **Planning a build?** → Roadmap. Phases answer "where are we".
- **Explaining *what broke*?** → Dossier. Evidence → hypothesis → verdict.
- **Showing a flow a *human* walks through?** → Journey (UX/process) — swimlanes + feelings.
- **Showing a flow *messages* travel through?** → Signal Trace (sequence) — order + async hops.
- **Moving/replacing a system safely?** → Runbook. Gates + rollback + risk.
- **Choosing between options?** → 2 options: Versus. 3+ or weighted: Decision Record.
- **Drawing the system itself?** → Blueprint (static structure).
- **Reporting state/progress?** → Mission Control (KPIs, rings, health).

### Easy mix-ups
| You might reach for… | But use… | When |
|---|---|---|
| Roadmap | **Runbook** | The work is a *reversible cutover*, not feature delivery |
| Blueprint | **Signal Trace** | You care about *order of messages*, not box layout |
| Decision Record | **Versus** | There are exactly *two* options |
| Journey | **Signal Trace** | The "actors" are services, not people |

## Reusing a template

1. Copy the file, rename it for your topic.
2. Update the `claude-artifact:` marker line: set `created=<today>`, `kind=` (`report`/`investigation`/`dashboard`/`mockup`), keep `project=`.
3. Replace the sample content (currently CPP-flavoured) — the CSS and hero components stay as-is.
4. Each theme's accent palette lives in the `:root { --... }` block at the top — change a few variables to re-tint without touching markup.

## Design conventions shared across all themes

- **Dark-first contrast:** hierarchy comes from accent saturation + glow (`text-shadow`, accent borders), not drop-shadows.
- **Animation encodes meaning** — direction of flow, completion of progress, a live pulse — never decoration for its own sake. All animations are CSS/SMIL and loop gently or run once on load.
- **One hero component per theme** so each is recognisable in a second.
- **No external assets** beyond a Google Fonts `<link>`; everything else is inline and works offline if the font fails to load (system-ui fallback).
