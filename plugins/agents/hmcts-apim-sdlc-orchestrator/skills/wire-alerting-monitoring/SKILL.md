---
name: wire-alerting-monitoring
description: >
  Detects which alerting/monitoring dimensions (downstream HTTP client, Service Bus
  Pattern B, Service Bus Pattern C) a service-cp-* repo's current PR diff introduces or
  changes, and wires up the corresponding alert + dashboard KQL, a drift-safety contract
  test, and onboarding into cp-amp-terraform-alerts. Generic across every service-cp-*
  repo — nothing in this skill's detection or templates is specific to any one service;
  dimension knowledge lives in context/alerting-monitoring.md, not here. Invoked from
  code-reviewer's Definition of Done gate whenever a PR's diff touches a known dimension;
  also runnable standalone for retroactive coverage on an existing repo. Idempotent and
  incremental — only adds alerts for newly-detected signals, never duplicates existing ones.
---

# Skill: Wire Alerting & Monitoring

## When to invoke

- From `code-reviewer`'s Definition of Done check (stage 6), on every PR — run Step 1 first;
  if the diff touches none of the dimensions in `context/alerting-monitoring.md`, this is a
  fast no-op: report "no alerting-relevant dimension touched" and exit.
- Standalone, to retroactively add coverage to an existing `service-cp-*` repo that predates
  this skill (scope Step 1 to the whole repo instead of one PR's diff).

Invocation command: `/wire-alerting-monitoring`

**Read `context/alerting-monitoring.md` before anything else below.** It defines every
dimension's detection test and signal catalogue. This file contains only the *procedure* — the
*dimension knowledge* lives there so either can evolve independently. A new dimension is added
to that doc, never invented inline here.

---

## Step 1 — Determine scope: diff-only or whole-repo

```bash
if [ -n "$PR_NUMBER" ]; then
  SCOPED_FILES=$(gh pr diff "$PR_NUMBER" --name-only | grep '\.java$')
else
  SCOPED_FILES=$(git ls-files -- 'src/main/java/**/*.java')
fi
echo "$SCOPED_FILES"
```

When invoked from `code-reviewer`, scope to the current PR's changed Java files only. When
invoked standalone, scope to the whole `src/main/java` tree.

---

## Step 2 — Detect dimensions present in scope

Run each dimension's detection test from `context/alerting-monitoring.md` against the scoped
files. Detection is generic — grep for the *shape* the doc describes, never a specific repo's
class or package name:

```bash
# Downstream HTTP client dimension
echo "$SCOPED_FILES" | xargs grep -l "RestClient\|StringRedisTemplate" 2>/dev/null

# Service Bus — confirm the dependency exists at all before looking for sub-pattern
grep -q "azure-messaging-servicebus" build.gradle && echo "SERVICEBUS_PRESENT"

# Distinguish Pattern B vs Pattern C — find the provisioning/admin-client class
PROVISIONING_FILE=$(grep -rl "ServiceBusAdministrationClient\|ServiceBusAdministrationAsyncClient" src/main/java 2>/dev/null)
if [ -n "$PROVISIONING_FILE" ]; then
  grep -q "\.createQueue(" "$PROVISIONING_FILE" && echo "PATTERN_B" || echo "PATTERN_C"
fi
```

Report which dimension(s) were found in scope. **If none, stop here** — nothing to wire for
this PR/repo.

If something Service-Bus-shaped is found but it matches neither Pattern B's nor Pattern C's
test, **stop and flag it** to the user as a possible new dimension for
`context/alerting-monitoring.md` — do not guess at its signal catalogue.

---

## Step 3 — For each detected dimension, find its candidate alert-worthy log literal(s)

```bash
echo "$SCOPED_FILES" | xargs grep -n "log\.error(\|log\.warn(" 2>/dev/null
```

Apply the judgment criteria from that dimension's entry in `context/alerting-monitoring.md` — a
genuine unrecoverable failure a human should act on, not:

- an expected business-outcome skip (e.g. a generation-gate "not required" skip)
- a per-attempt/transient retry log that fires before the retry budget is exhausted

For the Service Bus dimensions, prioritize log statements immediately preceding a
`.deadLetter(` / `.abandon(` call.

**If a dimension's failure has no distinguishable log literal yet** — e.g. a downstream
client's failure is only ever wrapped in a generic catch-all with no dimension-specific
message — add one now, at the point that failure becomes final, following this repo's existing
logging conventions (`context/logging-standards.md`). This is the one point where the skill
changes application code rather than only adding infra/test files.

---

## Step 4 — Generate/update repo-local KQL

Resolve the real pod name first — never write a placeholder into a file destined for a
Terraform PR:

```bash
gh api "repos/hmcts/cp-vp-aks-deploy/contents/vp-config/services_values.yml" \
  --jq '.content' | base64 -d | grep -A5 "$(gh repo view --json name -q '.name')"
```

If this service has no entry there yet, **stop and ask the user** to confirm the pod name
rather than guessing.

For each confirmed alert-worthy signal from Step 3, write
`support/alerts-kql/<descriptive-name>.kql`:

```kql
ContainerLogV2
| where PodName startswith "<REAL_PODNAME>"
| where ContainerName == "springboot-app"
| extend LogMessage = parse_json(LogMessage)
| where LogMessage.message contains "<literal from Step 3>"
| extend CorrId = tostring(LogMessage.mdc.["X-Correlation-Id"])
| project TimeGenerated, LogMessage.level, CorrId, LogMessage.message
```

For each dimension's dashboard-worthy signals (per `context/alerting-monitoring.md`), write the
equivalent `support/dashboard-kql/<name>.kql` — querying `AzureMetrics` or aggregating
`ContainerLogV2` as that dimension's entry describes. Skip this if the dimension's catalogue
entry defines no dashboard-worthy signals.

For Pattern C's native queue-metric alert specifically: write the `AzureMetrics`-based KQL, but
flag in the PR description that it depends on the Service Bus namespace's diagnostic settings
already forwarding metrics to the shared workspace — this skill cannot verify or provision that
from the app repo; name it as an open dependency, don't block on it.

---

## Step 5 — Idempotency check before writing any file

```bash
[ -f "support/alerts-kql/<name>.kql" ] && echo "ALREADY_EXISTS" || echo "NEW"
```

Never overwrite an existing `.kql` file silently. If new content would differ from what's
already there, show the diff and ask before replacing.

---

## Step 6 — Add/update the contract test

Ensure `src/test/java/.../alerts/AlertKqlLogMessageContractTest.java` exists — create it,
following this repo's existing test package layout, if this is the first alert ever added here.
For each new `.kql` file, add an assertion that its `contains "..."` literal exists in the Java
source file it's cited against. Mirror the *structure* of any contract test already present in
this repo or elsewhere in the workspace — never its literal content.

---

## Step 7 — Onboard into `cp-amp-terraform-alerts`

```bash
if [ -d /tmp/cp-amp-terraform-alerts ]; then
  git -C /tmp/cp-amp-terraform-alerts fetch origin
  git -C /tmp/cp-amp-terraform-alerts checkout -B alerting-onboarding origin/HEAD
else
  gh repo clone hmcts/cp-amp-terraform-alerts /tmp/cp-amp-terraform-alerts
  git -C /tmp/cp-amp-terraform-alerts checkout -B alerting-onboarding origin/HEAD
fi
```

- Copy each new `support/alerts-kql/*.kql` into `queries/`.
- Check whether an entry already exists in `vars/*.tfvars` for this alert name per environment
  — skip if present (idempotent).
- Append a new alert object per environment, reusing the existing action groups
  (`developer-emails` / `developer-emails-and-sms` / `full`) — never create a new action group.
  Match the severity/action-group choice already used by comparable alerts in the same file; if
  genuinely ambiguous, ask the user rather than guessing.
- Raise a PR — **never auto-apply**, matching this repo's existing per-environment
  human-approval pipeline.

---

## Step 8 — Raise the app-repo PR

```bash
git checkout -b chore/wire-alerting-monitoring
git add support/alerts-kql support/dashboard-kql \
        src/test/java/**/AlertKqlLogMessageContractTest.java
# plus any new log.error/log.warn statement added in Step 3
git commit -m "chore(observability): add alerting/monitoring for <dimension(s)>

<one line per dimension: what signal, why it matters>"
git push -u origin chore/wire-alerting-monitoring

gh pr create \
  --title "chore(observability): add alerting/monitoring for <dimension(s)>" \
  --body "..."
```

Link the `cp-amp-terraform-alerts` PR from Step 7 in this PR's description.

---

## Rules

- **Never hardcode a specific repo's names, queue names, or log literals into this skill's own
  detection or template logic** — everything comes from Step 2/3's introspection of the target
  repo. `context/alerting-monitoring.md` may cite real precedent in prose; this file must never
  depend on it.
- **Never write a placeholder pod name into a file destined for `cp-amp-terraform-alerts`** —
  stop and ask if it can't be resolved from `cp-vp-aks-deploy`.
- **Never auto-apply Terraform** — always a human-reviewed PR, same posture as
  `wire-service-deployment`.
- **Idempotent** — check before writing every file; skip or diff-and-ask, never silently
  overwrite.
- **A PR touching none of the dimensions in `context/alerting-monitoring.md` is a fast no-op** —
  do not force an alert onto unrelated changes.
- **A new dimension is added to `context/alerting-monitoring.md`, never invented inline in this
  file** — keeps detection knowledge and procedure separately reviewable.
- If a genuinely new integration style shows up that matches no dimension in
  `context/alerting-monitoring.md`, **stop and flag it** rather than silently skipping it or
  guessing at its signal catalogue — that's a gap in the doc, not something to invent standalone.
