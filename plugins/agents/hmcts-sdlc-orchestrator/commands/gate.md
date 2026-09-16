---
name: gate
description: Record a human-gate decision (approve / edit / reject / skip) for a pipeline stage. Unlocks the next stage and records gate rejection rate per agent.
allowed-tools: Bash(*/record-gate.sh:*)
---

# Record a gate decision

The user is reporting the outcome of a human gate in the SDLC pipeline. Capture it, then
carry on with whatever the pipeline does next.

**Arguments given:** `$ARGUMENTS`

This command does two things: it **unlocks the next pipeline stage** (gate state, read by
the `enforce-gate.sh` hook) and it **records the decision** for the gate rejection metric.
Only the user can invoke it. You must never run `record-gate.sh` yourself to unblock your
own work — that is the whole control, and forging it defeats the point.

## What to do

1. Work out the **stage**, the **decision**, and — if the decision was `edit`, `reject` or
   `skip` — a **reason code**, from the arguments and from what has happened in this session.

   | | Values |
   |---|---|
   | Stage | `requirements` `architecture` `user-story` `test-specs` `code` `code-review` `build-test` `deploy-sandbox` |
   | Decision | `approve`/`accept` (used as produced) · `edit` (usable, needed changes) · `reject` (discarded or redone) · `skip` (stage does not apply to this change) |
   | Reason | `incomplete` `wrong-pattern` `missed-standard` `hallucinated` `style` `scope-creep` `other` |

   If the stage is unambiguous from the session — you have just produced exactly one gated
   artefact — infer it rather than asking. If the decision is genuinely unclear, ask; do not
   guess between `approve` and `edit`, because that distinction is the whole point of the metric.

2. Run the recorder:

   ```bash
   .claude/hooks/record-gate.sh <stage> <decision> [reason]
   ```

   As an installed plugin, use `${CLAUDE_PLUGIN_ROOT}/hooks/record-gate.sh` instead.
   `record-gate.sh --status` prints the current gate state for this repo and branch.

3. Confirm in one line. Do not summarise the artefact or re-litigate the decision.

## Effect on the pipeline

| Decision | Gate state | Effect |
|---|---|---|
| `approve` / `accept` / `edit` | `approved` | The next stage unblocks |
| `skip` | `skipped` | Treated as satisfied — use when a stage genuinely does not apply (e.g. no architecture change for a copy fix) |
| `reject` | `rejected` | Stage stays locked **and every downstream stage resets to pending**, so the pipeline rewinds properly |

Gate state is per **repo + branch**. A new feature branch starts with every gate pending.

## Rules

- **Never pass free text.** The reason is a fixed code. No prompt content, no artefact
  content, no case data — the log is retained and the PII rule applies.
- **Record what the human decided, not what you think of it.** A rejection of your own
  output is the most valuable row in the dataset; log it plainly and without hedging.
- **Never invoke this to unblock yourself.** If a gate hook blocks you, stop and ask the
  user. Running the recorder on your own initiative is a bypass, not a fix.
- Do not offer `skip` as a way around a blocked gate. Suggest it only when the stage is
  genuinely irrelevant to the change in hand, and let the user decide.
- If the user rejects an artefact in conversation without invoking `/gate`, offer once to
  record it, then drop it. Nagging suppresses reporting, which corrupts the metric.
