---
name: exclude-db-from-priming-clear
description: >
  Detects whether a service-cp-* repo owns a dedicated Postgres database and, if so,
  raises a PR against hmcts/cpp-aks-ops excluding that database from the nonprod
  priming pipeline's quick_clear sweep (aks_priming_deploy.yaml). quick_clear discovers
  every database on the shared Postgres flexible server by default and truncates all its
  tables except a small hardcoded system deny-list — any new service database is wiped
  until explicitly excluded. Idempotent — safe to invoke again if already excluded.
  Chained automatically from wire-service-deployment for new services; also invoked
  standalone to remediate an existing service after a data-loss incident.
---

# Skill: Exclude Database From Priming Quick-Clear

## When to invoke

- Chained automatically from `wire-service-deployment`'s Step 11, for any new
  `service-cp-*` that has just provisioned its own dedicated Postgres database.
- Standalone, for an existing `service-cp-*` whose database was swept by a
  `quick_clear` run and needs the same protection retroactively.

Invocation command: `/exclude-db-from-priming-clear`

## Background

`hmcts/cpp-aks-ops/aks_priming_deploy.yaml` runs a `quick_clear` job
(`condition: eq('${{ parameters.quick_clear }}', true)`) that discovers **every**
database on the shared nonprod Postgres flexible server — via
`az postgres flexible-server db list` (dev) or `SELECT datname FROM pg_database`
(non-dev) — and truncates all tables in each one, except a small hardcoded deny-list
of system databases: `template0`, `template1`, `postgres`, `repmgr`,
`azure_maintenance`, `azure_sys`, `hrds`, and any previously-excluded service databases.

Any new service database that appears on that server is swept by default. `hrds`
already being in the deny-list shows this "add the db name to the deny-list" fix
pattern is established precedent, not a new mechanism this skill invents.

This skill does **not** change that mechanism (see the design doc's rejected
alternative — flipping to an allow-list) — it only keeps the existing deny-list
current for every `service-cp-*`-owned database.

## Step 1 — Detect a dedicated database

Run from the root of the service-cp-* repo:

```bash
python3 - <<'EOF'
import re, os

candidate = None

if os.path.exists("docker-compose.yml"):
    with open("docker-compose.yml") as f:
        m = re.search(r"POSTGRES_DB:[ \t]*(\S+)", f.read())
        if m:
            candidate = m.group(1).strip()

if not candidate and os.path.exists("src/main/resources/application.yaml"):
    with open("src/main/resources/application.yaml") as f:
        text = f.read()
    m = re.search(
        r"datasource:\s*\n\s*url:\s*.*jdbc:postgresql://[^/]+/([a-zA-Z0-9_]+)",
        text,
    )
    if m:
        candidate = m.group(1)

print(f"DB_DETECTED:{candidate}" if candidate else "NO_DB_OWNED")
EOF
```

If `NO_DB_OWNED`: report *"This service has no dedicated database — nothing to
protect from priming quick_clear."* and exit.

## Step 2 — Confirm the real database name with a human

The candidate name comes from **local dev config only** (`docker-compose.yml` /
`application.yaml`). It can diverge from what is actually provisioned on the shared
nonprod Postgres server — confirmed case: `service-cp-crime-results-pcr`'s local
config uses `pcrdb`, but the deployed database that was actually wiped is named `pcr`.

Ask the user directly:

> "I detected a local dev database name of `<candidate>` for this service. Before I
> raise a PR to `cpp-aks-ops`, please confirm the actual database name provisioned on
> the shared nonprod Postgres server (dev/ste/sit) — it may not match the local name."

Do not proceed to Step 3 without an explicit confirmed name from the user. Never
write the unconfirmed local candidate into the PR.

Validate the confirmed name before using it anywhere below — it must be a
plausible Postgres identifier, not arbitrary text:

```bash
DB_NAME=$(cat <<'NAME_EOF'
<confirmed name from Step 2>
NAME_EOF
)
if ! [[ "$DB_NAME" =~ ^[a-z0-9_]+$ ]]; then
  echo "REJECTED: '$DB_NAME' is not a valid Postgres identifier (lowercase letters, digits, underscore only) — ask the user to confirm again."
  exit 1
fi
```

Each step below re-declares `DB_NAME` at the top of its own commands —
do not assume shell state (exported variables) persists between separate
tool invocations of different steps.

## Step 3 — Idempotency check

```bash
if [ -d /tmp/cpp-aks-ops ]; then
  git -C /tmp/cpp-aks-ops fetch origin
  git -C /tmp/cpp-aks-ops checkout -B priming-exclusion-work origin/HEAD
else
  gh repo clone hmcts/cpp-aks-ops /tmp/cpp-aks-ops
  git -C /tmp/cpp-aks-ops checkout -B priming-exclusion-work origin/HEAD
fi
```

```bash
DB_NAME=$(cat <<'NAME_EOF'
<confirmed name from Step 2, validated above>
NAME_EOF
)
[[ "$DB_NAME" =~ ^[a-z0-9_]+$ ]] || { echo "REJECTED: invalid DB_NAME"; exit 1; }
if grep -q "!= \"$DB_NAME\"" /tmp/cpp-aks-ops/aks_priming_deploy.yaml \
   && grep -q "'$DB_NAME'" /tmp/cpp-aks-ops/aks_priming_deploy.yaml; then
  echo "ALREADY_EXCLUDED"
else
  echo "NEEDS_PATCH"
fi
```

If `ALREADY_EXCLUDED`: report *"`$DB_NAME` is already excluded from quick_clear.
Nothing to do."* and exit.

## Step 4 — Patch both deny-lists

Both edits are inside the single `runQuickClear` task
(`condition: eq('${{ parameters.quick_clear }}', true)`) — nothing in
`priming_enable`/`restore_dataset` logic is touched.

```bash
DB_NAME=$(cat <<'NAME_EOF'
<confirmed name from Step 2, validated above>
NAME_EOF
)
[[ "$DB_NAME" =~ ^[a-z0-9_]+$ ]] || { echo "REJECTED: invalid DB_NAME"; exit 1; }
export DB_NAME
python3 - <<'EOF'
import os

path = "/tmp/cpp-aks-ops/aks_priming_deploy.yaml"
db_name = os.environ["DB_NAME"]

with open(path) as f:
    text = f.read()

jq_old = 'and . != "hrds"'
jq_new = f'and . != "hrds" and . != "{db_name}"'
assert jq_old in text, "jq deny-list anchor not found — file may have changed upstream"
assert text.count(jq_old) == 1, "jq deny-list anchor appears more than once — ambiguous patch target"
text = text.replace(jq_old, jq_new, 1)

sql_old = "'azure_sys', 'hrds'"
sql_new = f"'azure_sys', 'hrds', '{db_name}'"
assert sql_old in text, "psql NOT IN anchor not found — file may have changed upstream"
assert text.count(sql_old) == 1, "psql NOT IN anchor appears more than once — ambiguous patch target"
text = text.replace(sql_old, sql_new, 1)

with open(path, "w") as f:
    f.write(text)

print("PATCHED")
EOF
```

If either `assert` fails, **stop** — the upstream file has changed shape since this
skill was written. Report the mismatch to the user rather than patching blind.

## Step 5 — Raise a PR against `cpp-aks-ops`

Check for an existing open PR first:

```bash
DB_NAME=$(cat <<'NAME_EOF'
<confirmed name from Step 2, validated above>
NAME_EOF
)
[[ "$DB_NAME" =~ ^[a-z0-9_]+$ ]] || { echo "REJECTED: invalid DB_NAME"; exit 1; }
gh pr list --repo hmcts/cpp-aks-ops --head "chore/exclude-$DB_NAME-from-priming-quick-clear" --state open
```

If an open PR is found, report its URL to the user and stop — do not raise a duplicate.

If none exists:

```bash
DB_NAME=$(cat <<'NAME_EOF'
<confirmed name from Step 2, validated above>
NAME_EOF
)
[[ "$DB_NAME" =~ ^[a-z0-9_]+$ ]] || { echo "REJECTED: invalid DB_NAME"; exit 1; }
cd /tmp/cpp-aks-ops
BRANCH="chore/exclude-$DB_NAME-from-priming-quick-clear"
git checkout -B "$BRANCH"
git add aks_priming_deploy.yaml
git commit -m "chore(priming): exclude $DB_NAME from quick_clear sweep

$DB_NAME is a dedicated service-owned Postgres database (service-cp-*),
not a legacy shared schema. quick_clear discovers every database on the
server by default (system deny-list only) and truncates all its tables,
which wiped $DB_NAME during a routine priming run. Adds it to both
discovery deny-lists (dev az-cli path and non-dev psql path), following
the same pattern already used for hrds."
git push -u origin "$BRANCH"

gh pr create \
  --repo hmcts/cpp-aks-ops \
  --title "chore(priming): exclude $DB_NAME from quick_clear sweep" \
  --body "$(cat <<BODY
## Summary

Excludes the \`$DB_NAME\` database from the priming pipeline's \`quick_clear\`
step. \`quick_clear\` enumerates every database on the shared nonprod Postgres
server and truncates all its tables except a small system deny-list
(\`template0\`, \`template1\`, \`postgres\`, \`repmgr\`, \`azure_maintenance\`,
\`azure_sys\`, \`hrds\`, and any previously-excluded service databases). \`$DB_NAME\` is owned by a service-cp-* Spring Boot
service with its own dedicated datastore, not a legacy shared schema, and
should not be swept by this job.

## Change

Adds \`$DB_NAME\` to both database-discovery deny-lists inside the
quick_clear-gated task only — no change to \`priming_enable\` or
\`restore_dataset\` behaviour.

## Verification needed before merge

- [ ] Confirm \`$DB_NAME\` is the correct database name in every environment
      this pipeline targets (dev/ste/sit) — instance naming can vary per
      environment.
BODY
)"
```

Never auto-merge. Report the PR URL to the user and stop — a human on the
`cpp-aks-ops` side must review and merge.

## Rules

- **Never patch without a human-confirmed database name** (Step 2) — local dev
  config can diverge from the deployed name.
- **Never auto-merge the PR.** `cpp-aks-ops` is a shared ops repo outside this
  plugin's owned repos — always a human gate, same posture as
  `wire-service-deployment`'s PR to `cp-vp-aks-deploy`.
- **Only touch the two deny-lists inside the `quick_clear`-gated task.** Never
  edit `priming_enable`/`restore_dataset` logic.
- **Idempotent** — check both deny-lists (Step 3) before patching; skip if the
  name is already present in both.
- If `gh repo clone`/`git push` fails on permissions, tell the user directly
  rather than silently failing.
- If either `assert` in Step 4 fails, stop and report — do not attempt a
  fuzzy/partial patch.