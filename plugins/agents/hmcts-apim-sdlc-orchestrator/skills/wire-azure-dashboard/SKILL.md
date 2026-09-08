---
name: wire-azure-dashboard
description: >
  Onboards a service-cp-*'s dashboard-worthy KQL (support/dashboard-kql/*.kql, produced by the
  wire-alerting-monitoring skill's Step 4, or expanded to match another service's baseline tile
  set per context/alerting-monitoring.md) into the shared cp-amp-terraform-az-dashboard repo:
  creates or extends that repo's configs/<name>.json tile layout and queries/<name>/*.kql,
  adding a repo-local support/sync-dashboard-to-terraform.sh if one doesn't exist yet, verifying
  every query against real data before shipping, and raises a PR. Generic across every
  service-cp-* repo — nothing in this skill's naming, layout, or sync logic is specific to any
  one service; the only precedent is cited in context/alerting-monitoring.md, never depended on
  as a value. Idempotent — never duplicates an existing dashboard, tile, or query for the same
  service; only adds what's newly detected.
---

# Skill: Wire Azure Dashboard

## When to invoke

- After `wire-alerting-monitoring` has generated `support/dashboard-kql/*.kql` for a service
  (either from the same PR's run or a prior one) — this skill's job starts where that one's
  Step 4 stops. If `support/dashboard-kql/` doesn't exist yet or is empty, **stop and say so**:
  run `wire-alerting-monitoring` first, this skill has nothing to onboard.
- Standalone, to retroactively onboard an existing repo's already-present `support/dashboard-kql/`
  into `cp-amp-terraform-az-dashboard` for the first time.
- Standalone, to add new tiles for dashboard-worthy KQL added since the last onboarding.
- Standalone, to expand an existing dashboard to match another service's baseline tile set (see
  `context/alerting-monitoring.md`'s "Baseline dashboard tiles" section). This mode *generates*
  new `support/dashboard-kql/*.kql` in the app repo first — treat every tile in the precedent
  service's dashboard as a **candidate, not a mandate**: check that candidate's own detection
  test (a specific log line existing, a metrics table having real data, a controller having the
  pattern at all) against this repo before creating KQL for it. A candidate with no real
  detection match in this repo is left out, with the reason stated, not silently invented.

Invocation command: `/wire-azure-dashboard`

**Read `context/alerting-monitoring.md`'s "Dashboard onboarding" mechanism bullet before anything
below** — dimension knowledge (which signals are dashboard-worthy) lives there; this file is only
the onboarding procedure once those `.kql` files already exist.

---

## Step 1 — Confirm there's something to onboard

```bash
ls support/dashboard-kql/*.kql 2>/dev/null
```

If empty or missing **and** this isn't the "expand to match precedent" mode from "When to
invoke," stop here — nothing to wire. Do not invent dashboard-worthy content; that judgment
belongs to `wire-alerting-monitoring` / `context/alerting-monitoring.md`.

In the "expand to match precedent" mode, this step instead means: for each candidate tile from
the precedent service's dashboard, run its detection test against this repo (a specific log line
existing in the source, a controller having the analogous pattern, real data existing in the
relevant metrics/App Insights table — see `context/alerting-monitoring.md`'s "Baseline dashboard
tiles"). Write `support/dashboard-kql/<name>.kql` only for candidates that pass their detection
test; state the reason for each one left out. Once this step produces at least one `.kql` file,
continue with Step 2 as normal.

---

## Step 2 — Determine the dashboard name

Clone or refresh `cp-amp-terraform-az-dashboard` first (see Step 4 for the clone command), then
check whether this service already has a dashboard there before choosing a name:

```bash
ls /tmp/cp-amp-terraform-az-dashboard/configs/*.json 2>/dev/null
ls /tmp/cp-amp-terraform-az-dashboard/queries/ 2>/dev/null
```

- If a `configs/<name>.json` / `queries/<name>/` pair already exists for this service (matched by
  repo name or by the `PodName startswith` prefix already used in this repo's own
  `support/alerts-kql/*.kql`), **reuse that exact name** — never create a second dashboard for the
  same service under a different name.
- If none exists, derive a short, human-readable name consistent with how this repo already
  names itself elsewhere (its `support/alerts-kql/*.kql` `PodName startswith` prefix is usually
  the right choice, since that's already the confirmed real pod name). If genuinely ambiguous,
  ask the user rather than guessing — this name is hard to rename later without breaking the
  Azure dashboard resource's identity.

---

## Step 3 — Ensure the app repo has a sync script

```bash
[ -f support/sync-dashboard-to-terraform.sh ] && echo "EXISTS" || echo "MISSING"
```

If missing, create it, mirroring the shape already proven in
`service-cp-crime-hearing-results-document-subscription/support/sync-dashboard-to-terraform.sh`
exactly (same structure: resolve both repos by relative path from the script's own location,
diff-before-copy each `.kql`, report added/updated/unchanged, print the next-steps reminder) —
only the destination folder name (Step 2's dashboard name) is repo-specific. Never invent a
different sync mechanism (e.g. writing directly into the Terraform repo's queries from this
skill without a reusable script) — the script is what a developer reaches for on every later
query change, not just this one onboarding run.

Make it executable (`chmod +x`) and commit it alongside the app-repo side of this change if it
didn't already exist.

---

## Step 4 — Clone/refresh `cp-amp-terraform-az-dashboard`

```bash
if [ -d /tmp/cp-amp-terraform-az-dashboard ]; then
  git -C /tmp/cp-amp-terraform-az-dashboard fetch origin
  git -C /tmp/cp-amp-terraform-az-dashboard checkout -B dashboard-onboarding-<name> origin/HEAD
else
  gh repo clone hmcts/cp-amp-terraform-az-dashboard /tmp/cp-amp-terraform-az-dashboard
  git -C /tmp/cp-amp-terraform-az-dashboard checkout -B dashboard-onboarding-<name> origin/HEAD
fi
```

---

## Step 5 — Sync the KQL

Run the app repo's `support/sync-dashboard-to-terraform.sh` (Step 3) pointed at the cloned repo
from Step 4. It already diffs before copying and reports added/updated/unchanged — trust its
idempotency, don't re-implement it here.

**Never touch `queries-prod/`** in `cp-amp-terraform-az-dashboard` — it's an orphaned, pre-JSON-config
convention no longer read by `dashboards.tf` (confirm with `grep -r "queries-prod" *.tf` coming
up empty before assuming otherwise on a future repo state). Don't add to it and don't "fix" it
as part of this skill's run; that's a separate, explicit cleanup if anyone ever asks for one.

---

## Step 6 — Create or extend `configs/<name>.json`

If `configs/<name>.json` doesn't exist yet, create it: one tile per synced query file, laid out
on the 12-column grid. Default shape per query, inferred from its own KQL shape — never guess a
chart the query doesn't support:

- A query whose final `summarize`/`make-series` produces one numeric series over time → a
  6-wide/4-tall tile with `chart: "Line"` or `"StackedColumn"` (match whichever this repo's other
  time-bucketed tiles already use for a similar cadence) and `metric` set to that series' name.
- A query with no `summarize`/aggregation (a raw/filtered log listing, e.g. "recent errors",
  "all logs") → a 12-wide/4-tall tile with no `chart`/`metric` (renders as a table).
- Stack tiles top-to-bottom in the order the KQL files were introduced; pair two 6-wide tiles
  side by side where they share a natural pairing (e.g. "by day" / "by hour" variants of the same
  metric), matching the layout convention already visible in any existing `configs/*.json` in the
  repo.

If `configs/<name>.json` already exists, **only append tiles for queries with no existing tile**
— resolve by the tile's `query` field already referencing that filename. Never reorder, resize,
or restyle an existing tile as a side effect of adding new ones.

---

## Step 7 — Verify every tile's query against real data before shipping

A query that only "looks right" is not enough — run it against the real target data source
before committing anything. This is where blind-copied precedent silently produces a wrong or
permanently-empty tile.

- For a log-based query: resolve the target Log Analytics workspace and query it directly —
  `az monitor log-analytics workspace show` for the workspace ID, then
  `az monitor log-analytics query -w <workspaceId> --analytics-query "..."`.
- For an App Insights-based query (`use_appinsights: true`): resolve that component's *backing*
  workspace — `az monitor app-insights component show --app <name> --query workspaceResourceId`
  — and query **that workspace directly**, using the workspace-native table name (`AppRequests`,
  not `requests` — `requests` is a classic-API-only alias that Azure resolves automatically
  *inside a deployed dashboard tile*, but does not resolve when queried this way).
  - **Never verify with `az monitor app-insights query --app <appId>`.** That command uses the
    legacy classic Application Insights REST API, which silently returns incomplete data for
    workspace-based App Insights components — the modern default for every new component, so
    assume this applies unless proven otherwise. A near-zero result from that command is *not*
    proof the tile will be empty; it may just be the wrong verification tool. Confirmed case: a
    query that returned ~2 rows via the legacy API returned the correct ~10,000+ rows once
    queried via the underlying workspace directly, matching APIM's own native
    `reports/byApi` call count almost exactly.
  - The KQL *file* itself should still be written using the classic name (`requests`, not
    `AppRequests`) — that's what the deployed dashboard tile's `use_appinsights: true` context
    expects and resolves correctly on its own. Only the *verification* method needs the
    workspace-direct form.
- A query that genuinely returns 0 rows against real data is fine to ship — an empty tile can be
  the correct, healthy state (e.g. no downstream failures yet). Say so explicitly in the PR
  description so a reviewer doesn't mistake it for a broken query.
- A query returning data that looks anomalous (an unexplained spike, a sustained gap, a count
  wildly different from a related metric) is a genuine finding — name it in the PR description
  as something for the team to look into, separate from the dashboard-onboarding work itself.
  Don't silently ship a tile without flagging what looks odd about its own data.

---

## Step 8 — Idempotency check before writing any file

Never overwrite an existing `configs/<name>.json` or `queries/<name>/*.kql` file silently. If new
content would differ from what's already there for a file this skill didn't just create, show the
diff and ask before replacing — same posture as `wire-alerting-monitoring`'s Step 5.

---

## Step 9 — Raise the `cp-amp-terraform-az-dashboard` PR

```bash
cd /tmp/cp-amp-terraform-az-dashboard
git add configs queries
git commit -m "chore(dashboard): onboard <service> dashboard-worthy KQL

<one line per new tile: what it shows, why>"
git push -u origin dashboard-onboarding-<name>

gh pr create \
  --repo hmcts/cp-amp-terraform-az-dashboard \
  --title "chore(dashboard): onboard <service> dashboard-worthy KQL" \
  --body "..."
```

**Never trigger the Terraform pipeline** — deployment there is a manual, human-approved ADO run
per that repo's own README (`azure-pipelines.yml`, Plan then Apply, both gated). This skill only
raises the PR.

Mention in the PR description that the new tiles can be previewed locally, before merge, using
that repo's own bundled `.claude/skills/dashboard-preview` skill (a static HTML mockup from
`configs/<name>.json` — no Azure access needed) — don't reimplement that preview here, just point
to it.

---

## Step 10 — Cross-link

If the app-repo side of this change (Step 3's new sync script, or the `support/dashboard-kql/`
files themselves) is still an open PR, link the `cp-amp-terraform-az-dashboard` PR from it and
vice versa, same as `wire-alerting-monitoring`'s Step 8 does for `cp-amp-terraform-alerts`.

---

## Rules

- **Never hardcode a specific service's dashboard name, query names, or tile layout into this
  skill's own logic** — Step 2 derives the name from the target repo/service at run time;
  precedent (`hearing-results-document-subscription`) is cited only in
  `context/alerting-monitoring.md`'s prose, never depended on as a value here.
- **One dashboard name per service, forever** — always check for an existing
  `configs/<name>.json`/`queries/<name>/` pair before minting a new name (Step 2).
- **Never write into `queries-prod/`** — it is unread by `dashboards.tf`; perpetuating it is a
  known trap, not a convention to follow.
- **Never guess a chart type a query's own shape doesn't support** — no `chart`/`metric` on a
  query with no `summarize`/`make-series` aggregation.
- **Never resize, reorder, or restyle an existing tile** when only adding new ones.
- **Never auto-apply Terraform or trigger the ADO pipeline** — always a human-reviewed PR, then a
  manual pipeline run by whoever owns that environment, same posture as `wire-alerting-monitoring`
  and `wire-service-deployment`.
- **Idempotent** — check before writing every file; skip or diff-and-ask, never silently
  overwrite.
- If `support/dashboard-kql/` doesn't exist yet, **stop and say so** rather than generating
  dashboard content inline — that's `wire-alerting-monitoring`'s job, not this skill's — unless
  running in the explicit "expand to match precedent" mode, where generating it is the point.
- **Every precedent tile is a candidate, never a mandate** — when matching another service's
  dashboard, verify each candidate's detection test against this repo before creating its KQL;
  a service missing the underlying pattern genuinely doesn't get that tile.
- **Never verify an `use_appinsights: true` query with the legacy classic API**
  (`az monitor app-insights query --app <appId>`) — it silently under-reports for workspace-based
  components. Resolve and query the backing Log Analytics workspace directly instead (Step 7).
- **An empty or anomalous result is data, not failure** — ship a genuinely-empty tile with a note
  that empty is expected; flag genuinely anomalous data as a finding for the team, not something
  to quietly bury inside a dashboard-onboarding PR.
