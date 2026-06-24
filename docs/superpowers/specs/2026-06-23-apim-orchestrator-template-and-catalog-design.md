# Design: bootstrap-from-template skills + catalog-publisher realignment for hmcts-apim-sdlc-orchestrator

This supersedes the earlier draft `2026-06-23-apim-template-bootstrap-skills-design.md`
(folded in here as Part 1, extended with git-access closures, plus a new Part 2).

## Problem

`hmcts-apim-sdlc-orchestrator`'s own `CLAUDE.md` references two skills as Stage 0
of its Path A and Path B pipelines, and again in its Hard Rules section:

- `springboot-api-from-template`
- `springboot-service-from-template`

Neither skill exists inside `hmcts-apim-sdlc-orchestrator`. They only exist nested
inside a different plugin, `hmcts-sdlc-orchestrator` (the legacy CQRS/WildFly
orchestrator), at
`plugins/agents/hmcts-sdlc-orchestrator/skills/springboot-api-from-template/` and
`.../springboot-service-from-template/`. A user with only
`hmcts-apim-sdlc-orchestrator` installed cannot run Stage 0 of either pipeline path.

Separately, `hmcts-apim-sdlc-orchestrator`'s `catalog-publisher` agent
(`agents/catalog-publisher.md`) has drifted from the actual canonical process for
publishing an API to the HMCTS API Catalog. That canonical process lives as a
gitignored local skill inside the `amp-catalog` repo itself —
`amp-catalog/.claude/skills/publish-api-to-catalog/SKILL.md` — and is the real
source of truth (it is what the `amp-catalog` maintainers wrote and use). Comparing
the two:

| | `catalog-publisher` (current, this repo) | `publish-api-to-catalog` (canonical, `amp-catalog`) |
|---|---|---|
| Eligibility / public-exposure check | **Missing entirely** | Mandatory Phase 2 — blocks internal-only APIs from being exposed on a world-readable Pages site |
| Per-repo workflow | Assumes `publish-swagger-ui.yml` is referenced directly | Correct: thin caller `publish-api-docs.yml` → reusable `hmcts/amp-catalog/.../publish-swagger-ui.yml@v1` |
| Pages bootstrap gotchas | Not handled | Documents the one-time Pages-enable and tag branch-policy steps that otherwise fail silently |
| Catalog entry PR | Single PR, immediate | Two PRs by design, strict order (API-repo workflow PR first, catalog PR second) |

Missing the eligibility check is a real compliance gap, not just staleness — it
means the agent could currently walk a user through exposing an internal-only API
publicly with no safety check at all.

## Trigger

AMP-684 needs the Stage-0 bootstrap capability for `api-cp-crime-hearing` /
`service-cp-crime-hearing`-style repos. While verifying the catalog flow against a
real example (`api-cp-crime-hearing`, already published), two things surfaced:

1. The published spec's `examples:` blocks were spot-checked by hand (fetched the
   live bundled spec from `hmcts.github.io/api-cp-crime-hearing/openapi-spec.yml`,
   confirmed it has no leftover relative `$ref`s, and validated all 6 example
   `value` blocks against their referenced schemas — types, enums, uuid/date
   formats). **Result: clean, no defect.** This is a one-off verification finding,
   not a design change — captured here for the record, no file changes follow
   from it directly, beyond the new gate below making it a standing check.
2. `api-cp-crime-hearing` is live and publishing correctly but is **absent from
   `amp-catalog/docs/apis.json`** — it was never picked up by `discover_apis.py`
   or manually listed. Action: once Part 2 lands, use the corrected process to
   open the catalog PR for it directly (per user decision).

## Decision — Part 1: fork the two from-template skills

Fork both skills directly into `hmcts-apim-sdlc-orchestrator/skills/`, adapted to
this plugin's actual scope. `hmcts-sdlc-orchestrator` is owned by a different team
and is left untouched — this is a copy, not a move.

The marketplace already has a pattern for *shared, reusable* skills living as
standalone top-level plugins (`adr-template`, `bdd-workflow`, etc.), but that
pattern is rejected here, for the same reason as the canonical-catalog-skill
question below: ownership of `hmcts-sdlc-orchestrator` sits outside this team, and
the two skills diverge once adapted (CP-only naming/context), so they're no longer
byte-identical shared content.

The forked skills keep their original names. `hmcts-apim-sdlc-orchestrator/CLAUDE.md`
already references those exact names — no edits to `CLAUDE.md` are needed.

### Adaptation from the legacy version

- **Naming convention** hardcoded to `api-cp-[case-type]-{entity}` /
  `service-cp-[case-type]-{entity}` — source-system fixed to `cp`. Drop the
  `dcs`/`sscs` examples; keep the `api-cp-refdata-*` variant (still CP-scoped).
- **Master template sources are unchanged**: `hmcts/api-hmcts-crime-template` and
  `hmcts/service-hmcts-crime-springboot-template`.
- **Context references** point at this plugin's own files —
  `context/api-spec-shared.md`, `context/service-shared.md`,
  `context/hmcts-standards.md` — instead of the legacy plugin's
  `context/coding-standards.md`, `context/tech-stack.md`, etc.
- **Cross-skill delegation**: the service skill's Step 2 still delegates to the
  sibling `springboot-api-from-template`, now an in-plugin reference.
- **Drop** legacy-RAML / `cpp-context-*` exclusion notes — not applicable here.

### New: git-access closures (on top of the legacy content)

The legacy skills already grant the owning team `admin` (or `push` for a
secondary team) on the repo immediately after creation (Step 3/4). Three gaps
close around that grant, added to **both** forked skills:

1. **Team-membership verification.** Immediately after the permission grant, check
   the team actually has members:
   ```bash
   gh api /orgs/hmcts/teams/{team-slug}/members --jq '.[].login'
   ```
   If empty, surface a warning: the team has repo access but zero members, so no
   one can push yet — do not treat the grant alone as "done."
2. **Branch-protection sanity check.** After importing
   `.github/rulesets/main-branch-protection.json` (Step 6 / post-template steps),
   read the ruleset back:
   ```bash
   gh api repos/hmcts/{repo-name}/rulesets --jq '.[] | {name, rules: [.rules[] | {type, parameters}]}'
   ```
   Flag if `required_approving_review_count` is greater than or equal to the
   owning team's member count (it would deadlock the team's own PRs), or if no
   bypass actor is configured for the owning team.
3. **New-member setup section.** Add a short "New team member setup" block to
   both skill files (near the quick-check list) and to the generated repo's
   `README.md`: `gh auth login` (or SSH key setup), `git clone
   git@github.com:hmcts/{repo}.git`, and a smoke step — push a throwaway branch
   and confirm it succeeds — before relying on the grant.

Quick-check lists in both skills gain three new line items mirroring 1–3.

## Decision — Part 2: realign `catalog-publisher` + add an examples gate

Rewrite `agents/catalog-publisher.md` so its steps match the canonical
`publish-api-to-catalog` phases, adapted to this agent's event-driven framing
(fires on release, not invoked ad hoc per arbitrary repo):

1. **Phase 0 — eligibility / public-exposure check (new, mandatory, blocking).**
   Before anything else: confirm repo visibility, and require explicit
   confirmation that the API is external (bucket 2b/2c in the canonical skill's
   terms) before any Pages/catalog action proceeds. Internal-only APIs (2a) stop
   here — no exception.
2. **Correct workflow chain.** Verify the repo has the thin caller
   `.github/workflows/publish-api-docs.yml` (pinned `@v1`) rather than assuming a
   direct reference to `publish-swagger-ui.yml`. If absent, this agent's job is to
   flag it (raising the PR to add it is the `publish-api-to-catalog` skill's job,
   run inside the API repo itself — this agent does not duplicate that).
3. **Pages-bootstrap gotchas.** Document (and check for) the two one-time admin
   steps that otherwise fail silently: enabling Pages via `gh api -X POST
   repos/hmcts/{repo}/pages -f build_type=workflow`, and adding the `v*` tag
   branch-policy to the `github-pages` environment.
4. **Two-PR sequencing, preserved.** Keep the existing additive-only `apis.json`
   update and PR-raising steps, but make explicit that the API-repo docs PR (if
   ever missing) must merge and publish *before* the catalog PR — never the
   reverse.
5. **New — examples validation gate.** Before registering a new entry or updating
   a drifted one, fetch the live bundled spec from
   `https://hmcts.github.io/{repo}/openapi-spec.yml` and validate every
   `examples:` block: for each response/request `examples` map, check the
   `value` against its sibling `schema` (or `items` for array responses) —
   required structural shape, enum membership, and basic format checks
   (`uuid`, `date`). This reuses the inline-Python style already used elsewhere
   in this agent file (no new shared module). Add a new **Hard rule**:
   *"Examples must validate against their schemas before an entry is registered
   or updated — if validation fails, stop and report the mismatch instead of
   registering."*

`amp-catalog`'s own skill is left untouched — different repo, different
ownership, same "fork & adapt, don't move" precedent as Part 1.

Stays an **agent**, not a skill — the orchestrator already models every pipeline
stage as an agent; introducing a second abstraction here for one stage would be
inconsistent without a reason. `amp-catalog`'s version is correctly a skill
because it's invoked ad hoc by any repo maintainer; here it's a fixed,
release-triggered pipeline stage.

### Immediate follow-up (not a design change, an action)

Once Part 2 lands, run the corrected `catalog-publisher` flow once, by hand,
against `api-cp-crime-hearing` to open the missing catalog PR (per user decision
— register now rather than wait for `discover_apis.py`).

## Files affected

| File | Change |
|---|---|
| `plugins/agents/hmcts-apim-sdlc-orchestrator/skills/springboot-api-from-template/SKILL.md` | New (forked + adapted + git-access closures) |
| `plugins/agents/hmcts-apim-sdlc-orchestrator/skills/springboot-service-from-template/SKILL.md` | New (forked + adapted + git-access closures) |
| `plugins/agents/hmcts-apim-sdlc-orchestrator/agents/catalog-publisher.md` | Rewritten — canonical phases, eligibility gate, examples gate |
| `plugins/agents/hmcts-apim-sdlc-orchestrator/README.md` | Add both new skills to "What's inside"; update `catalog-publisher` one-liner |
| `plugins/agents/hmcts-apim-sdlc-orchestrator/.claude-plugin/plugin.json` | Bump `1.0.0` → `1.1.0`; description mentions the two new skills + realigned catalog flow |
| `.claude-plugin/marketplace.json` | Bump the `hmcts-apim-sdlc-orchestrator` entry's `version` to `1.1.0`; sync description |

No changes to `hmcts-sdlc-orchestrator` or `amp-catalog`.

## Out of scope

- Any change to `hmcts-sdlc-orchestrator` or its skills (different ownership).
- Any change to `amp-catalog`'s own `.claude/skills/publish-api-to-catalog`
  (different repo, different ownership; read as reference only).
- Extracting either workstream to a standalone shared marketplace skill
  (rejected — see Decision sections).
- Fixing anything in `api-cp-crime-hearing`'s spec/examples — verified clean, no
  fix needed.

## Verification

Per this repo's own plugin-testing convention:

1. `code-review:review` on the branch — fix all findings.
2. `/reload-plugins` — confirm the skill count increases by 2 and the
   `catalog-publisher` agent reloads with no errors.
3. `/doctor` — expect clean.
4. Smoke test bootstrap: ask Claude to bootstrap a new `api-cp-crime-hearing`-style
   repo and confirm `springboot-api-from-template` fires (dry-run the trigger
   only — no destructive `gh repo create`).
5. Smoke test catalog: ask Claude to register `api-cp-crime-hearing` in the
   catalog and confirm the rewritten `catalog-publisher` runs the eligibility
   check first, finds the existing `publish-api-docs.yml`, and the examples gate
   passes (it already does, per the manual check above) before raising the PR.