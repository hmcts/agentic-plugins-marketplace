---
name: wire-azure-dashboard
description: >
  Onboards a service-cp-*'s dashboard-worthy KQL (support/dashboard-kql/*.kql, produced by the
  wire-alerting-monitoring skill's Step 4) into the shared cp-amp-terraform-az-dashboard repo:
  creates or extends that repo's configs/<name>.json tile layout and queries/<name>/*.kql,
  adding a repo-local support/sync-dashboard-to-terraform.sh if one doesn't exist yet, and raises
  a PR. Generic across every service-cp-* repo — nothing in this skill's naming, layout, or sync
  logic is specific to any one service; the only precedent is cited in context/alerting-monitoring.md,
  never depended on as a value. Idempotent — never duplicates an existing dashboard, tile, or
  query for the same service; only adds what's newly detected.
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

Invocation command: `/wire-azure-dashboard`

**Read `context/alerting-monitoring.md`'s "Dashboard onboarding" mechanism bullet before anything
below** — dimension knowledge (which signals are dashboard-worthy) lives there; this file is only
the onboarding procedure once those `.kql` files already exist.

---

## Step 1 — Confirm there's something to onboard

```bash
ls support/dashboard-kql/*.kql 2>/dev/null
```

If empty or missing, stop here — nothing to wire. Do not invent dashboard-worthy content; that
judgment belongs to `wire-alerting-monitoring` / `context/alerting-monitoring.md`.

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

## Step 7 — Idempotency check before writing any file

Never overwrite an existing `configs/<name>.json` or `queries/<name>/*.kql` file silently. If new
content would differ from what's already there for a file this skill didn't just create, show the
diff and ask before replacing — same posture as `wire-alerting-monitoring`'s Step 5.

---

## Step 8 — Raise the `cp-amp-terraform-az-dashboard` PR

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

## Step 9 — Cross-link

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
  dashboard content inline — that's `wire-alerting-monitoring`'s job, not this skill's.
