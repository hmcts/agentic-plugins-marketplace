# APIM Template-Bootstrap Skills + Catalog-Publisher Realignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `hmcts-apim-sdlc-orchestrator` self-contained for its own Stage-0 references (`springboot-api-from-template`, `springboot-service-from-template`), close three git-access gaps in those skills, and realign `catalog-publisher` with the canonical `amp-catalog` publishing process plus a new examples-validation gate — then sync all docs/versions and register the one real backlog item (`api-cp-crime-hearing`) in the catalog.

**Architecture:** Two skill files and one agent file are markdown prompt documents, not executable code — there is no unit-test runner for them. "Testing" here means: (a) structural validation (YAML frontmatter parses, required sections present) via small shell/python checks, and (b) the repo's own documented plugin-testing convention (`/reload-plugins`, `/doctor`, `code-review:review`). Each task ends with a concrete, runnable verification command and an expected result — there are no unverifiable "looks right" steps.

**Tech Stack:** Markdown + YAML frontmatter (Claude Code skill/agent format), `gh` CLI, `git`, Python 3 + PyYAML (already used elsewhere in `catalog-publisher.md`), `jq`.

## Global Constraints

- Fork, don't move: `hmcts-sdlc-orchestrator` is untouched by every task in this plan.
- `amp-catalog`'s own `.claude/skills/publish-api-to-catalog/SKILL.md` is untouched — read-only reference.
- New/forked skills are scoped to `cp` (Common Platform) only — no `dcs`/`sscs` naming examples.
- Repo visibility for any repo created by the forked skills is **public**, never private, no exception without an ADR.
- A repo must never be created without an owning GitHub team validated first (`gh api /orgs/hmcts/teams/{slug}`).
- `catalog-publisher`'s eligibility check (Task 3, Step 1) is mandatory and blocking — never skipped.
- `catalog-publisher`'s examples-validation gate (Task 3, Step 9) must pass before any `apis.json` write.
- Spec doc of record: `docs/superpowers/specs/2026-06-23-apim-orchestrator-template-and-catalog-design.md`.

---

### Task 1: Fork `springboot-api-from-template` into `hmcts-apim-sdlc-orchestrator`

**Files:**
- Create: `plugins/agents/hmcts-apim-sdlc-orchestrator/skills/springboot-api-from-template/SKILL.md`

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces: a skill named `springboot-api-from-template`, discoverable by `hmcts-apim-sdlc-orchestrator`'s own `CLAUDE.md` Stage-0 references (Path A/B tables, Hard Rules) — no edits needed there since it already names this skill.

- [ ] **Step 1: Write the skill file**

```markdown
---
name: springboot-api-from-template
description: Start a new HMCTS API-Marketplace API specification repo using the canonical HMCTS template (api-hmcts-crime-template) as master source. Use when creating a new api-cp-* repo (OpenAPI-first, spec-only) distinct from a runtime service-cp-* service.
---

# HMCTS API-Marketplace API from Template

This skill stands up a new OpenAPI specification repository from the HMCTS
template. API spec repos are distinct from runtime services:

- **api-cp-\*** repos contain the OpenAPI spec, validation tooling, generators,
  and publishing workflows. They produce the spec artefact consumed by
  services.
- **service-cp-\*** repos contain the runtime Spring Boot implementation and
  consume one or more api-cp-* artefacts. Use `springboot-service-from-template`
  for those.

Do not mix runtime code into an api-cp-* repo.

## API-first — why this skill runs before `springboot-service-from-template`

Every `service-cp-*` has a matching `api-cp-*`, and this skill produces that
API repo. It is intended to run **before** the service skill — ideally with
time in between to review the contract with consumers.

The split is deliberate:

- The contract has its own cadence of change, driven by consumer needs and
  cross-team agreement — not by the implementation team's sprint.
- Engineering teams naturally want to jump into code when they should still
  be designing the API. This separation makes jumping ahead awkward by
  design: the service cannot build without an API artefact to depend on.
- Collapsing API and service into one repo couples contract design to service
  delivery and produces whatever API the service happened to ship, not the
  API the consumers actually need.

Repo-pair naming convention shares the suffix so the link is obvious:

- API repo: `api-cp-[case-type]-{business-domain}-{entity}`
- Service repo: `service-cp-[case-type]-{business-domain}-{entity}`

If a user jumps straight to `springboot-service-from-template` without an
API repo in place, redirect them here first.

## Master source

**GitHub:** https://github.com/hmcts/api-hmcts-crime-template

Everything under `build.gradle`, `gradle/`, `.github/workflows/`, and the
validation tooling belongs to the template. This skill must not inline those
files.

## Context to pull in

- `context/api-spec-shared.md` — OpenAPI authoring rules, naming, `@JsonInclude(NON_NULL)`.
- `context/hmcts-standards.md` — Coding in the Open, repo ownership, Conventional Commits, ADR triggers, data protection.

For design decisions made during the API work, invoke the `adr-template` skill.

## When to use

- User says "create a new HMCTS API", "new API marketplace repo",
  "scaffold an OpenAPI spec repo".
- The work is specification-only: no runtime code, no database, no controllers.
- A new entity, reference-data resource, or business-domain API needs a repo.

## Do **not** use this skill for

- Runtime Spring Boot services — use `springboot-service-from-template`.
- Anything CQRS, RAML, Drools, or WildFly — out of scope for this plugin
  entirely. Redirect to `hmcts-sdlc-orchestrator`.

---

## Required input

Ask the user (one question at a time is fine; batch if they've already volunteered some):

1. **Repo name** — must follow HMCTS Marketplace naming conventions:
   - Standard APIs: `api-cp-[case-type]-{business-domain}-{name-of-entity}`.
   - Reference data APIs: `api-cp-refdata-{product-domain}-{name-of-entity}`
     (`product-domain` is **required** for reference data — global ownership
     means no ownership).
   - `case-type` (optional): `civil` | `crime` | `family` | `tribunal`.
   - `business-domain` examples: `caseingestion`, `casematerial`, `caseadmin`,
     `casehearing`, `schedulingandlisting`.
   - **Forbidden tokens:** `common`, `core`, `base`, `utils`, `helpers`,
     `misc`, `shared`.
2. **Owning GitHub team slug** — the team that will own the repo. **Prerequisite** — the repo will not be created without one. The team must already exist in the `hmcts` org; if it does not, stop and ask the org admins to create the team first. Optional: a secondary team slug plus its permission (usually `push`).
3. **Short description** — one-line summary used on the GitHub repo and in the new `README.md`.
4. **Owning product team context** — the human product team name, on-call/support model, and escalation path (used to populate `README.md`; distinct from the GitHub team slug above).
5. **API version** — SemVer baseline + media type per
   `docs/API-VERSIONING-STRATEGY.md` in the template.
6. **Primary consumers** — which `service-cp-*` repos will consume this spec.

If any are unknown, stop and surface as an open question. **A repo without an owning GitHub team must not be created** — ownership-before-creation is a hard rule.

**GitHub owner is not a user input.** The default owner is `hmcts`; use it without asking.

**Repo visibility is not a user input.** HMCTS operates under "Coding in the Open" — new API spec repos are created **public**. Do not ask, do not offer a private option, do not pass `--private`. The only exception is an ADR explicitly approved by the tech lead citing a legal/classification constraint.

---

## Process

### Step 1 — Validate the owning GitHub team exists

**Do not skip this step and do not proceed to repo creation until it passes.**

```bash
gh api /orgs/hmcts/teams/{team-slug} --jq '.slug, .name'
```

- Returns the slug/name → proceed.
- Returns `Not Found` → stop. Ask an `hmcts` org owner to create the team first.
- Repeat for the optional secondary team, if supplied.

### Step 2 — Create the repo from the template (via GitHub API)

```bash
gh repo create hmcts/{api-name} \
  --template hmcts/api-hmcts-crime-template \
  --public \
  --description "{short description}" \
  --clone
```

`--public` is mandatory. `cd` into the clone before continuing.

### Step 3 — Grant the owning team access

```bash
gh api --method PUT \
  /orgs/hmcts/teams/{team-slug}/repos/hmcts/{api-name} \
  -f permission=admin
```

If a secondary team was supplied, grant it `push` (or the user's chosen level):

```bash
gh api --method PUT \
  /orgs/hmcts/teams/{secondary-team-slug}/repos/hmcts/{api-name} \
  -f permission=push
```

**Verify:**

```bash
gh api /repos/hmcts/{api-name}/teams --jq '.[] | {slug, permission}'
```

### Step 3.5 — Verify the team actually has members (new)

A team can hold `admin` on a repo and still have nobody who can push it, if
the team itself is empty. Check:

```bash
gh api /orgs/hmcts/teams/{team-slug}/members --jq '.[].login'
```

- If this prints one or more logins, proceed.
- If it prints nothing, **surface a warning** to the user: "`{team-slug}` has
  admin access to `{api-name}` but has zero members — no one can push until
  someone is added to the team." Do not block repo creation on this (the team
  may be staffed shortly after), but never skip surfacing it.

### Step 4 — Post-creation bookkeeping

```bash
gh repo view hmcts/{api-name} --json visibility,templateRepository
```

Expected: `visibility: "PUBLIC"`, `templateRepository.name: "api-hmcts-crime-template"`.

### Step 5 — Read the template supporting docs

Read in full before editing anything:

- `README.md`, `docs/API-VERSIONING-STRATEGY.md`, `docs/OPENAPI-FILE-CONVENTIONS.md`,
  `docs/OPENAPI-SPEC-VERSIONING.md`, `docs/CHAIN_OF_CUSTODY.md`,
  `docs/DATA-PRODUCTS.md`, `docs/GITHUB-ACTIONS.md`.

Align any open questions against `https://hmcts.github.io/restful-api-standards/`.

### Step 6 — Post-template manual steps

1. Settings → General → enable "Automatically delete head branches".
2. Import `.github/rulesets/main-branch-protection.json` into repo rulesets,
   then delete that JSON from the new repo.
3. Delete files only meaningful in the template: `./docs/*` (replace with
   repo-specific docs), `./src/main/resources/openapi/deleteme`.
4. Rewrite `README.md` for the new API, naming the owning team from Step 1
   (not a generic handle), and add the "New team member setup" section below.

### Step 6.5 — Check the ruleset doesn't deadlock the owning team (new)

After importing the ruleset in Step 6, read it back:

```bash
gh api repos/hmcts/{api-name}/rulesets \
  --jq '.[] | {name, rules: [.rules[] | select(.type=="pull_request") | .parameters.required_approving_review_count]}'
```

Compare the `required_approving_review_count` against the team member count
from Step 3.5. If the required count is **greater than or equal to** the
team's member count, flag it to the user: the team cannot approve its own
PRs without an outside reviewer. Do not silently edit the ruleset — it is
owned by the org security policy; surface the conflict and let the user
decide (add a reviewer outside the team, or accept the friction).

### Step 7 — Write the OpenAPI spec

- Location: `src/main/resources/openapi/openapi-spec.yml`.
- Structure per `docs/OPENAPI-FILE-CONVENTIONS.md`.
- Conform to `https://hmcts.github.io/restful-api-standards/`.
- Every endpoint documents: auth, error responses, pagination, media type, version.

### Step 8 — Versioning

- Media-type versioning: `Accept: application/vnd.hmcts.<resource>.v1+json`.
- SemVer on the published artefact. Breaking changes require a new major
  version and an ADR in consumer services.

### Step 9 — Configure GitHub Actions

- Add the secrets/variables in `docs/GITHUB-ACTIONS.md`.
- Enable repo rulesets.
- Do not fork the workflows locally — open a PR against the template instead.

### Step 10 — Publish the spec artefact

The template's publish workflow emits the spec as a Maven artefact consumers
depend on (`apiSpec "uk.gov.hmcts.cp:api-{...}:X.Y.Z"`).

---

## New team member setup

Anyone newly added to the owning team needs to do this once before
contributing, to catch any gap between "team has repo access" and "this
person can actually push":

```bash
gh auth login                                       # if not already authenticated
git clone git@github.com:hmcts/{api-name}.git
cd {api-name}
git checkout -b smoke/access-check
git commit --allow-empty -m "chore: verify push access"
git push -u origin smoke/access-check
git push origin --delete smoke/access-check          # clean up the throwaway branch
```

If the push is rejected with a permissions error, re-check Step 3 (team
grant) and Step 3.5 (team membership) — don't assume it's a tooling problem.

---

## Quick-check before marking "done"

- [ ] Owning GitHub team was validated **before** the repo was created.
- [ ] Repo created via `gh repo create ... --template ... --public`.
- [ ] `gh repo view --json visibility` returns `"PUBLIC"`.
- [ ] Owning team granted `admin` on the repo.
- [ ] Team membership checked (Step 3.5) — not empty, or the gap was explicitly surfaced.
- [ ] Branch-protection required-reviewer count checked against team size (Step 6.5) — no deadlock risk, or explicitly flagged.
- [ ] New-member setup steps (above) documented in the new repo's `README.md`.
- [ ] Repo name follows naming convention and avoids forbidden tokens.
- [ ] Template `docs/*` rewritten or removed; `deleteme` sample removed.
- [ ] `openapi-spec.yml` conforms to `https://hmcts.github.io/restful-api-standards/`.
- [ ] Versioning strategy stated (media type + SemVer).
- [ ] Required GitHub secrets/variables configured.
- [ ] Main branch ruleset imported and the source JSON deleted from the new repo.
- [ ] No runtime Java code introduced.

## Divergence policy

The template owns validation tooling, publishing workflow, and naming.
Propose changes upstream rather than forking locally.
```

- [ ] **Step 2: Verify the frontmatter parses and required sections exist**

```bash
python3 - <<'EOF'
import yaml, re

path = "plugins/agents/hmcts-apim-sdlc-orchestrator/skills/springboot-api-from-template/SKILL.md"
with open(path) as f:
    text = f.read()

m = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
assert m, "no YAML frontmatter found"
front = yaml.safe_load(m.group(1))
assert front["name"] == "springboot-api-from-template", front
assert "description" in front and len(front["description"]) > 20

for required in ["## Required input", "## Process", "### Step 3.5", "### Step 6.5", "## New team member setup", "## Quick-check before marking \"done\""]:
    assert required in text, f"missing section: {required}"

print("OK: frontmatter valid, all required sections present")
EOF
```

Expected: `OK: frontmatter valid, all required sections present`

- [ ] **Step 3: Commit**

```bash
git add plugins/agents/hmcts-apim-sdlc-orchestrator/skills/springboot-api-from-template/SKILL.md
git commit -m "AMP-569: fork springboot-api-from-template into hmcts-apim-sdlc-orchestrator"
```

---

### Task 2: Fork `springboot-service-from-template` into `hmcts-apim-sdlc-orchestrator`

**Files:**
- Create: `plugins/agents/hmcts-apim-sdlc-orchestrator/skills/springboot-service-from-template/SKILL.md`

**Interfaces:**
- Consumes: the skill name `springboot-api-from-template` (Task 1) — referenced by name in Step 2's delegation step; both are skills, invoked by name, no shared code/types.
- Produces: a skill named `springboot-service-from-template`.

- [ ] **Step 1: Write the skill file**

```markdown
---
name: springboot-service-from-template
description: Stand up a new HMCTS API-Marketplace service-cp-* using the canonical HMCTS template (service-hmcts-crime-springboot-template) as master source. Use when creating a new Spring Boot service for the Common Platform.
---

# Spring Boot Service from HMCTS Template

This skill does **not** generate a Spring Boot app from scratch. It guides
the team through adopting the HMCTS template so the new service stays aligned
with every update that lands in the template over time.

## Master source

**GitHub:** https://github.com/hmcts/service-hmcts-crime-springboot-template

Everything under `build.gradle`, `gradle/`, `Dockerfile`, `docker/`,
`src/main/resources/logback.xml`, `src/main/resources/application.yaml`, and
`.github/workflows/` belongs to the template. This skill **must not** inline
copies of those files — they change, and inline copies rot.

If the template is not already available locally, clone it fresh before
running through the steps below:

```bash
git clone https://github.com/hmcts/service-hmcts-crime-springboot-template.git
```

## Context to pull in

Before walking a user through this skill, load these context files:

- `context/service-shared.md` — Spring Boot layering, controllers/services/clients/mappers conventions.
- `context/azure-sdk-guide.md` — Managed Identity, Key Vault, Service Bus.
- `context/logging-standards.md` — mandatory JSON logging.
- `context/hmcts-standards.md` — Coding in the Open, ADR triggers, data protection.

## When to use

- User says "create a new HMCTS Spring Boot service", "bootstrap a microservice",
  "spin up a new backend" for the Common Platform.
- User is about to start a new `service-cp-*` repo.
- User has a repo created from the GitHub template and needs to tailor it.

## Do **not** use this skill for

- API specification repos — use `springboot-api-from-template` instead.
- Anything CQRS, RAML, Drools, or WildFly — out of scope for this plugin
  entirely. Redirect to `hmcts-sdlc-orchestrator`.

## API-first — handled inline in Step 2

Every `service-cp-*` has a matching `api-cp-*`, and the API repo comes first.
This skill enforces that operationally in **Step 2** — it asks for the API
repo name, offers to derive it from the service name by convention, checks
the repo exists, and if it doesn't, delegates to `springboot-api-from-template`
to create it before the service repo is ever touched.

- Pair convention: if the service is `service-cp-crime-caseadmin-hearings`,
  the API repo is `api-cp-crime-caseadmin-hearings` — same suffix.
- The service consumes the API via the `apiSpec` configuration in
  `build.gradle` — see Step 8 below.

The rationale is captured in `context/hmcts-standards.md` → "API-first
design". Do not collapse contract and implementation into one repo.

---

## Required input

Ask the user (one question at a time is fine; batch if they've already volunteered some):

1. **Service name** — must follow `service-cp-[case-type]-{business-domain}-{name-of-entity}`.
   - `case-type` (optional): `civil` | `crime` | `family` | `tribunal`.
   - `business-domain`: e.g., `caseingestion`, `caseadmin`, `casehearing`, `schedulingandlisting`.
   - **Forbidden tokens:** `common`, `core`, `base`, `utils`, `helpers`, `misc`, `shared`.
2. **Owning GitHub team slug** — the team that will own the repo. **Prerequisite** — the repo will not be created without one. The team must already exist in the `hmcts` org; if it does not, stop and ask the org admins to create the team first. Optional: a secondary team slug plus its permission (usually `push`).
3. **Short description** — one-line summary used on the GitHub repo and in the new `README.md`.
4. **Java package root** — `uk.gov.hmcts.cp.{business-domain}.{entity}`.
5. **Upstream / downstream** — which services does this call, and which call it?
6. **Stateful?** — does it need Postgres? (Flyway + Testcontainers wiring is already in the template.)
7. **Azure integrations expected** — Service Bus topics/queues, Key Vault references, App Configuration usage. Trigger `azure-sdk-guide.md` if any are planned.
8. **Ownership context** — on-call rota, support model, escalation path.

The **matching API repo name and published artefact version** are captured
interactively in Step 2 — do not ask for them here.

**GitHub owner is not a user input.** Default `hmcts`.

**Repo visibility is not a user input.** Public, per "Coding in the Open" — no exception without an ADR.

---

## Process

### Step 1 — Validate the owning GitHub team exists

```bash
gh api /orgs/hmcts/teams/{team-slug} --jq '.slug, .name'
```

Stop if `Not Found` — do not fall back to creating the repo with only a user as admin.

### Step 2 — Confirm (or create) the matching API repo

1. Ask: **"What's the API repo name for this service?"** Offer the derived
   default (`service-` → `api-` prefix swap). Capture as `{api-name}`.
2. Check existence:
   ```bash
   gh repo view hmcts/{api-name} --json name,visibility,isTemplate 2>/dev/null
   ```
3. **Exists** → ask for the published SemVer artefact version to depend on.
   Record `uk.gov.hmcts.cp:{api-name}:{version}` for Step 8.
4. **Not found** → halt this skill's flow and invoke `springboot-api-from-template`
   with `{api-name}`, passing through owning team/owner/description already
   collected. After it completes (repo exists, spec drafted, first version
   published), resume here with the new coordinate. If it cannot complete
   (team doesn't exist yet, consumer review still open), surface the blocker
   — do not create the service repo and do not wire a placeholder coordinate.

**Important** — never fall back to the template's own placeholder coordinate
(`uk.gov.hmcts.cp:api-hmcts-crime-template:X.Y.Z`); it is not a valid
production dependency.

### Step 3 — Create the repo from the template (via GitHub API)

```bash
gh repo create hmcts/{service-name} \
  --template hmcts/service-hmcts-crime-springboot-template \
  --public \
  --description "{short description}" \
  --clone
```

### Step 4 — Grant the owning team access

```bash
gh api --method PUT \
  /orgs/hmcts/teams/{team-slug}/repos/hmcts/{service-name} \
  -f permission=admin
```

Secondary team (if any) gets `push`:

```bash
gh api --method PUT \
  /orgs/hmcts/teams/{secondary-team-slug}/repos/hmcts/{service-name} \
  -f permission=push
```

**Verify:**

```bash
gh api /repos/hmcts/{service-name}/teams --jq '.[] | {slug, permission}'
```

### Step 4.5 — Verify the team actually has members (new)

```bash
gh api /orgs/hmcts/teams/{team-slug}/members --jq '.[].login'
```

If empty, surface a warning: "`{team-slug}` has admin access to
`{service-name}` but has zero members — no one can push until someone is
added to the team." Don't block creation on it, but always surface it.

### Step 5 — Post-creation bookkeeping

```bash
gh repo view hmcts/{service-name} --json visibility,templateRepository
```

Enable "Automatically delete head branches" and import the main-branch
ruleset (same as the API skill's Step 6).

### Step 5.5 — Check the ruleset doesn't deadlock the owning team (new)

```bash
gh api repos/hmcts/{service-name}/rulesets \
  --jq '.[] | {name, rules: [.rules[] | select(.type=="pull_request") | .parameters.required_approving_review_count]}'
```

Compare against the Step 4.5 member count; flag (don't silently fix) if the
required review count would deadlock the team's own PRs.

### Step 6 — Read what the template already gives you

Read, in this order — do not modify yet: `README.md`, `build.gradle` +
`gradle/*.gradle`, `src/main/resources/application.yaml`,
`src/main/resources/logback.xml`, `Dockerfile`, `.github/workflows/`,
`docs/SpringUpgradev4.md`, `docs/EnvironmentVariables.md`, `docs/JWTFilter.md`,
`docs/Logging.md`, `docs/PIPELINE.md`.

### Step 7 — Service identity

1. `settings.gradle` — `rootProject.name` → the service name.
2. `application.yaml` — `spring.application.name` and
   `management.metrics.tags.service` → the real name.
3. Rename the Java base package to `uk.gov.hmcts.cp.{business-domain}.{entity}`.
4. Rename `Application.java` references accordingly.
5. Delete `Example*` sample code and tests. Keep `GlobalExceptionHandler`,
   `RootController`, filters, config.
6. Update `README.md` — purpose, owners, runbook link, escalation, and add
   the "New team member setup" section below.

Do **not** change the `build.gradle` plugin block, `apply from:` list,
`logback.xml` encoder/providers, or the Dockerfile non-root setup.

### Step 8 — Wire the API spec dependency (`apiSpec`)

Replace the placeholder coordinate with the one captured in Step 2:

```groovy
dependencies {
  apiSpec "uk.gov.hmcts.cp:{api-name}:{semver}"
  ...
}
```

Exactly one `apiSpec` line per service. If multiple APIs seem needed, stop
and raise an ADR — that's usually a service-boundary smell.

### Step 9 — Environment variables and secrets

Per `docs/EnvironmentVariables.md`: `.env` + `.envrc` via `direnv` locally
(gitignored), all runtime config env-driven, Managed Identity for Azure auth,
secrets from Key Vault, `SERVER_PORT` default `8082`.

### Step 10 — Persistence (only if stateful)

Flyway migrations under `src/main/resources/db/migration/V{n}__{description}.sql`,
JPA entities + Spring Data repositories, MapStruct DTO mapping, Testcontainers
for integration tests.

### Step 11 — CI/CD

Activate `.github/workflows/ci-build-publish.yml`, `ci-draft.yml`,
`ci-released.yml`, CodeQL, Trufflehog, gitleaks, PMD, ACR publish per
`docs/GITHUB-ACTIONS.md`. Do not fork the workflows.

### Step 12 — Helm + Flux CD

Helm chart with liveness/readiness probes, `runAsNonRoot: true`,
Workload Identity annotation + federated credential, register in
`cpp-flux-config`.

### Step 13 — Observability wiring

OpenTelemetry starter already on the classpath; set `OTEL_TRACES_URL` /
`OTEL_METRICS_URL` via Helm; App Insights agent injected by the base image.

### Step 14 — First-run verification

```bash
./gradlew build
docker compose up
./gradlew bootRun
curl -i http://localhost:8082/actuator/health/readiness
curl -i http://localhost:8082/
```

Confirm stdout is JSON-parseable with `correlationId`/`requestId` in MDC.

### Step 15 — ADR any deviation

Use the `adr-template` skill for any deviation from the template.

---

## New team member setup

Anyone newly added to the owning team needs to do this once, to catch any
gap between "team has repo access" and "this person can actually push":

```bash
gh auth login                                          # if not already authenticated
git clone git@github.com:hmcts/{service-name}.git
cd {service-name}
git checkout -b smoke/access-check
git commit --allow-empty -m "chore: verify push access"
git push -u origin smoke/access-check
git push origin --delete smoke/access-check             # clean up the throwaway branch
```

If the push is rejected with a permissions error, re-check Step 4 (team
grant) and Step 4.5 (team membership) before assuming a tooling problem.

---

## Quick-check before marking "done"

- [ ] Owning GitHub team validated before the repo was created.
- [ ] Repo created via `gh repo create ... --template ... --public`.
- [ ] `gh repo view --json visibility` returns `"PUBLIC"`.
- [ ] Owning team granted `admin`.
- [ ] Team membership checked (Step 4.5) — not empty, or the gap was explicitly surfaced.
- [ ] Branch-protection required-reviewer count checked against team size (Step 5.5).
- [ ] New-member setup steps documented in the new repo's `README.md`.
- [ ] Service name follows convention and avoids forbidden tokens.
- [ ] Step 2 resolved the API repo (existing + version, or created via `springboot-api-from-template`) **before** the service repo was created.
- [ ] `build.gradle` `apiSpec` line replaced with the service's own coordinate.
- [ ] `spring.application.name` and metrics tags match the repo name.
- [ ] Java package renamed; `Example*` sample code removed.
- [ ] `README.md` describes the new service, owners, support model.
- [ ] All config read from env vars; no connection strings/SAS tokens/account keys anywhere.
- [ ] Azure services authenticated via Managed Identity.
- [ ] JSON logs to stdout validated locally.
- [ ] `/actuator/health/readiness` and `/liveness` return 200.
- [ ] Container user is `app` (non-root).
- [ ] Helm chart added with probes, MI annotation, resource limits.
- [ ] Flux config entry added.
- [ ] ADR present for every deviation from the template.

## Divergence policy

The template is the master source. Propose changes upstream; do not fork
defaults locally.
```

- [ ] **Step 2: Verify the frontmatter parses and required sections exist**

```bash
python3 - <<'EOF'
import yaml, re

path = "plugins/agents/hmcts-apim-sdlc-orchestrator/skills/springboot-service-from-template/SKILL.md"
with open(path) as f:
    text = f.read()

m = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
assert m, "no YAML frontmatter found"
front = yaml.safe_load(m.group(1))
assert front["name"] == "springboot-service-from-template", front
assert "description" in front and len(front["description"]) > 20

for required in ["## Required input", "## Process", "### Step 4.5", "### Step 5.5", "## New team member setup", "## Quick-check before marking \"done\""]:
    assert required in text, f"missing section: {required}"

assert "springboot-api-from-template" in text, "must reference the sibling skill"

print("OK: frontmatter valid, all required sections present")
EOF
```

Expected: `OK: frontmatter valid, all required sections present`

- [ ] **Step 3: Commit**

```bash
git add plugins/agents/hmcts-apim-sdlc-orchestrator/skills/springboot-service-from-template/SKILL.md
git commit -m "AMP-569: fork springboot-service-from-template into hmcts-apim-sdlc-orchestrator"
```

---

### Task 3: Rewrite `catalog-publisher` to match the canonical process + add the examples gate

**Files:**
- Modify: `plugins/agents/hmcts-apim-sdlc-orchestrator/agents/catalog-publisher.md` (full rewrite of the body; frontmatter `name`/`tools`/`model`/`color` unchanged, `description` updated)

**Interfaces:**
- Consumes: nothing from Task 1/2 (independent file).
- Produces: an agent named `catalog-publisher`, referenced by name in `CLAUDE.md`'s Path A/B tables (no change needed there — name is unchanged) and `README.md` (updated in Task 4).

- [ ] **Step 1: Replace the agent file content**

```markdown
---
name: catalog-publisher
description: |
  Register or update an api-cp-* spec in the HMCTS AMP catalog (hmcts/amp-catalog) after a GitHub Release. Event-driven — fires once per release, not on a schedule. Runs a mandatory public-exposure eligibility check before anything else, verifies the correct publish-api-docs.yml -> publish-swagger-ui.yml@v1 workflow chain, and validates every OpenAPI `examples` block against its schema before writing to the catalog.

  Path A (new spec): eligibility check, verifies the workflow chain and live Pages site, reads info.title/info.description, validates examples, raises a PR to amp-catalog adding the entry.
  Path A/B (enhancement): detects if title or description drifted from the current catalog entry and raises a PR to update it (after the same eligibility + examples checks).

  Does not modify the spec or the service repo — only touches amp-catalog/docs/apis.json. Does not add the per-repo publish-api-docs.yml workflow — that is the `publish-api-to-catalog` skill's job, run from inside the API repo itself.

  <example>
  user: "The first release of api-cp-crime-court-schedule is published — register it in the catalog"
  assistant: "I'll use the catalog-publisher to run the eligibility check, verify the Pages site and workflow chain, validate the spec's examples, and raise a PR to amp-catalog."
  </example>

  <example>
  user: "We updated the spec title in api-cp-crime-hearing-results-document-subscription — sync the catalog"
  assistant: "I'll use the catalog-publisher to detect the metadata drift and raise an update PR to amp-catalog, after re-checking eligibility and examples."
  </example>
model: sonnet
tools: Bash, Read, Edit, Write
color: blue
---

# Agent: Catalog Publisher

## Role

Register new `api-cp-*` specs in the HMCTS AMP catalog, and keep existing entries
up to date when spec metadata changes. Fires **once per GitHub Release** — not a
scheduled runner.

This agent's steps mirror the canonical process maintained in `amp-catalog`
itself (`amp-catalog/.claude/skills/publish-api-to-catalog/SKILL.md`), adapted
to this orchestrator's release-triggered framing. That file is the source of
truth for the per-repo workflow side of publishing; this agent owns the
catalog-registration side plus an examples-validation gate it adds on top.

- **Catalog repo:** `hmcts/amp-catalog`
- **Registry file:** `docs/apis.json`
- **Catalog page:** `https://hmcts.github.io/amp-catalog/`
- **Spec location:** `https://hmcts.github.io/<repo>/openapi-spec.yml` (bundled —
  the publish workflow inlines all `$ref`s, including `examples/*.yaml` files,
  before deploying; the published spec has no external refs left)
- **Per-repo workflow:** a thin caller `.github/workflows/publish-api-docs.yml`
  that calls the reusable `hmcts/amp-catalog/.github/workflows/publish-swagger-ui.yml@v1`
- **Auto-discovery:** `amp-catalog/scripts/discover_apis.py` runs daily in CI;
  this agent closes the gap for immediate registration and drift detection.

---

## Instructions

### Step 1 — Eligibility / public-exposure check (mandatory, blocking)

GitHub Pages on a public repo is **world-readable**. Before anything else,
confirm this API is allowed to be exposed that way:

```bash
REPO=$(basename "$PWD")
gh repo view --json visibility,nameWithOwner -q '.visibility + "  " + .nameWithOwner'
```

Ask the user to explicitly confirm the API is **external** and safe to expose
to the public internet (documentation-only or mock-execution use cases are
fine; internal-only APIs are not). If the API is internal-only, or the user
is unsure, or the repo is `private`/`internal` and they cannot confirm it
should be public: **STOP.** Do not proceed to any later step. Internal APIs
stay off the public catalog until the APIM Developer Portal lands.

Confirm `$REPO` starts with `api-cp-` — if not, stop; this agent only applies
to spec libraries.

### Step 2 — Identify the release

```bash
gh release view --repo hmcts/$REPO --json tagName,publishedAt \
  --jq '"Tag: \(.tagName)  Published: \(.publishedAt)"'
```

### Step 3 — Verify the correct workflow chain is wired

```bash
grep -rl "publish-api-docs.yml\|amp-catalog/.github/workflows/publish-swagger-ui.yml" .github/workflows/ 2>/dev/null || echo "NOT FOUND"
```

- **NOT FOUND** — the per-repo wrapper is missing. Adding it is the
  `publish-api-to-catalog` skill's job, run from inside this API repo, not
  this agent's. Stop and tell the user to run that skill first.
- **Found** — confirm it's the thin-wrapper pattern, not a stale inline copy:
  ```bash
  cat .github/workflows/publish-api-docs.yml
  ```
  Expect a line like `uses: hmcts/amp-catalog/.github/workflows/publish-swagger-ui.yml@v1`.
  If the file instead inlines its own Swagger UI build steps, flag the drift
  and stop — don't register a possibly-broken Pages pipeline.

### Step 4 — Verify GitHub Pages is live (and handle the one-time bootstrap gaps)

```bash
curl -sf "https://hmcts.github.io/$REPO/openapi-spec.yml" -o /tmp/spec.yml \
  && echo "Pages live" || echo "Pages not yet live"
```

If not live, check two one-time admin gaps before assuming the workflow just
hasn't run yet — both fail silently otherwise:

1. **Pages not enabled.** The workflow's `GITHUB_TOKEN` cannot *create* the
   Pages site; without this it fails at "Configure GitHub Pages" with
   `Resource not accessible by integration`:
   ```bash
   gh api "repos/hmcts/$REPO/pages" >/dev/null 2>&1 \
     || gh api -X POST "repos/hmcts/$REPO/pages" -f build_type=workflow
   ```
2. **Tag deploys rejected.** The auto-created `github-pages` environment
   permits deployments only from `main` by default; a release-triggered run
   uses the tag ref and is rejected at the environment gate (instant failure,
   no logs). Add the tag policy once (after the first run has created the
   environment):
   ```bash
   gh api -X POST "repos/hmcts/$REPO/environments/github-pages/deployment-branch-policies" \
     -f name='v*' -f type='tag'
   ```

Re-trigger and watch:

```bash
gh workflow run publish-api-docs.yml --repo hmcts/$REPO
gh run list --repo hmcts/$REPO --workflow publish-api-docs.yml --limit 3
```

### Step 5 — Read spec metadata

```bash
python3 - <<'EOF'
import yaml
with open("/tmp/spec.yml") as f:
    spec = yaml.safe_load(f)
info = spec.get("info", {})
print(f"title:       {info.get('title', '')}")
print(f"description: {info.get('description', '')}")
print(f"version:     {info.get('version', '')}")
EOF
```

### Step 6 — Read the current catalog entry

```bash
gh repo clone hmcts/amp-catalog /tmp/amp-catalog 2>/dev/null \
  || git -C /tmp/amp-catalog pull --ff-only
```

```bash
python3 - <<'EOF'
import json
with open("/tmp/amp-catalog/docs/apis.json") as f:
    data = json.load(f)
repo = "$REPO"
entry = next((a for a in data["apis"] if a["name"] == repo), None)
if entry:
    print(f"EXISTS: {json.dumps(entry, indent=2)}")
else:
    print("NOT IN CATALOG")
EOF
```

### Step 7 — Determine action

| Catalog state | Spec metadata | Action |
|---|---|---|
| Not in catalog | — | **Add** new entry |
| In catalog, title/description match | — | **No change needed** — confirm and stop |
| In catalog, title or description drifted | Changed | **Update** entry |

### Step 8 — Derive team from CODEOWNERS

```bash
gh api repos/hmcts/$REPO/contents/.github/CODEOWNERS \
  --header "Accept: application/vnd.github.raw" 2>/dev/null \
  | grep -v '^#' | grep -v '^$' | head -1 \
  | awk '{for(i=2;i<=NF;i++) if($i ~ /^@hmcts\//) {gsub("@hmcts/","",$i); print $i; exit}}'
```

If CODEOWNERS is absent or no team found, use `"AMP"` as the default.

### Step 9 — Validate examples against their schemas (mandatory gate, new)

Before writing anything to `apis.json`, validate every `examples:` block in
the bundled spec fetched in Step 4 (`/tmp/spec.yml`) against its sibling
`schema`:

```bash
python3 - <<'EOF'
import yaml, sys

with open("/tmp/spec.yml") as f:
    spec = yaml.safe_load(f)

schemas = spec.get("components", {}).get("schemas", {})

def resolve(ref):
    return schemas.get(ref.split("/")[-1], {})

def check_value(value, schema, path):
    errors = []
    if "$ref" in schema:
        schema = resolve(schema["$ref"])
    schema_type = schema.get("type")
    if schema_type == "array":
        if not isinstance(value, list):
            errors.append(f"{path}: expected array, got {type(value).__name__}")
        else:
            for i, item in enumerate(value):
                errors += check_value(item, schema.get("items", {}), f"{path}[{i}]")
    elif schema_type == "object" or "properties" in schema:
        if not isinstance(value, dict):
            errors.append(f"{path}: expected object, got {type(value).__name__}")
        else:
            props = schema.get("properties", {})
            for key, val in value.items():
                if key not in props:
                    errors.append(f"{path}.{key}: not defined in schema")
                else:
                    errors += check_value(val, props[key], f"{path}.{key}")
            for req in schema.get("required", []):
                if req not in value:
                    errors.append(f"{path}.{req}: required field missing")
    else:
        enum = schema.get("enum")
        if enum and value not in enum:
            errors.append(f"{path}: value {value!r} not in enum {enum}")
    return errors

all_errors = []
for route, methods in spec.get("paths", {}).items():
    for verb, op in methods.items():
        if verb not in ("get", "post", "put", "patch", "delete"):
            continue
        for status, resp in (op.get("responses") or {}).items():
            content = resp.get("content", {}) if isinstance(resp, dict) else {}
            for media_type, body in content.items():
                examples = body.get("examples") or {}
                schema = body.get("schema", {})
                for ex_name, ex in examples.items():
                    value = ex.get("value")
                    label = f"{route} {verb.upper()} {status} examples.{ex_name}"
                    all_errors += check_value(value, schema, label)

if all_errors:
    print("EXAMPLES INVALID:")
    for e in all_errors:
        print(f"  - {e}")
    sys.exit(1)
print("All examples validate against their schemas.")
EOF
```

- **Exit 0** ("All examples validate...") → proceed to Step 10.
- **Exit 1** ("EXAMPLES INVALID...") → **stop**. Report the exact mismatches
  to the user. Do not register or update the catalog entry with a spec whose
  examples don't validate.

### Step 10 — Update `apis.json`

**For a new entry:**

```python
import json

REPO = "$REPO"
TITLE = "<from Step 5>"
DESCRIPTION = "<from Step 5>"
TEAM = "<from Step 8>"

with open("/tmp/amp-catalog/docs/apis.json") as f:
    data = json.load(f)

# Additive only — never remove existing entries
if not any(a["name"] == REPO for a in data["apis"]):
    data["apis"].append({
        "name": REPO,
        "title": TITLE,
        "description": DESCRIPTION,
        "team": TEAM,
    })
    data["apis"].sort(key=lambda a: a["name"])
    with open("/tmp/amp-catalog/docs/apis.json", "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    print("Entry added.")
else:
    print("Already exists — use update path.")
```

**For an update (drift detected):** update only `title` and `description` —
never overwrite `name`, `team`, or any custom fields the catalog maintainers
may have set.

### Step 11 — Raise a PR to `amp-catalog`

This is **PR #2** in the overall sequence — the API repo's own
`publish-api-docs.yml` PR (Step 3) must already be merged and published
(confirmed live in Step 4) before this one is opened.

```bash
cd /tmp/amp-catalog
BRANCH="catalog/add-$REPO"    # or catalog/update-$REPO for updates
git checkout -b $BRANCH
git add docs/apis.json
git commit -m "feat(catalog): add $REPO to API registry"
git push origin $BRANCH
gh pr create \
  --repo hmcts/amp-catalog \
  --title "feat(catalog): add $REPO" \
  --body "Registers $REPO in the AMP catalog.\n\n- Title: $TITLE\n- Team: $TEAM\n- Examples validated against schema: yes\n- Spec: https://hmcts.github.io/$REPO/openapi-spec.yml\n- Pages: https://hmcts.github.io/$REPO/" \
  --base main
```

Check for an existing open PR before raising a new one:

```bash
gh pr list --repo hmcts/amp-catalog --head "catalog/$REPO" --state open
```

### Step 12 — Verify catalog page after merge

```bash
curl -sf "https://hmcts.github.io/amp-catalog/apis.json" \
  | python3 -c "import json,sys; apis=json.load(sys.stdin)['apis']; \
    match=[a for a in apis if a['name']=='$REPO']; \
    print('REGISTERED:', match[0]) if match else print('NOT FOUND')"
```

---

## Hard rules

- **Eligibility check (Step 1) is mandatory and blocking** — never skip it,
  even under time pressure. Internal-only APIs do not get registered.
- **Examples must validate against their schemas (Step 9) before any
  `apis.json` write** — if validation fails, stop and report the mismatch
  instead of registering or updating.
- **Additive only** — never remove or overwrite existing catalog entries.
- **Only update `title` and `description`** on an existing entry — `name`,
  `team`, and any custom fields are owned by catalog maintainers.
- **Never modify the `api-cp-*` repo's spec** — read-only access to the spec.
- **Never add the per-repo `publish-api-docs.yml` workflow** — that's the
  `publish-api-to-catalog` skill's job, run from inside the API repo.
- **Only runs on `api-cp-*` repos** — stop immediately for `service-cp-*` or
  other repo types.
- **Pages must be live before registering** — do not add an entry for a spec
  that is not yet published to GitHub Pages.
- **One PR per release** — check for an open PR before raising a new one.
```

- [ ] **Step 2: Verify the frontmatter parses and required sections/gates exist**

```bash
python3 - <<'EOF'
import yaml, re

path = "plugins/agents/hmcts-apim-sdlc-orchestrator/agents/catalog-publisher.md"
with open(path) as f:
    text = f.read()

m = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
assert m, "no YAML frontmatter found"
front = yaml.safe_load(m.group(1))
assert front["name"] == "catalog-publisher", front
assert front["tools"] == "Bash, Read, Edit, Write", front["tools"]

for required in [
    "### Step 1 — Eligibility / public-exposure check (mandatory, blocking)",
    "### Step 9 — Validate examples against their schemas (mandatory gate, new)",
    "## Hard rules",
    "Eligibility check (Step 1) is mandatory and blocking",
    "Examples must validate against their schemas (Step 9)",
]:
    assert required in text, f"missing: {required}"

print("OK: frontmatter valid, eligibility gate and examples gate both present")
EOF
```

Expected: `OK: frontmatter valid, eligibility gate and examples gate both present`

- [ ] **Step 3: Dry-run the examples-validation snippet against the already-fetched `api-cp-crime-hearing` spec**

This confirms the Step 9 script is actually correct Python, using the real
spec already on disk from the earlier manual check (re-fetch if `/tmp/spec.yml`
isn't present):

```bash
curl -sf "https://hmcts.github.io/api-cp-crime-hearing/openapi-spec.yml" -o /tmp/spec.yml
python3 - <<'EOF'
import yaml, sys

with open("/tmp/spec.yml") as f:
    spec = yaml.safe_load(f)

schemas = spec.get("components", {}).get("schemas", {})

def resolve(ref):
    return schemas.get(ref.split("/")[-1], {})

def check_value(value, schema, path):
    errors = []
    if "$ref" in schema:
        schema = resolve(schema["$ref"])
    schema_type = schema.get("type")
    if schema_type == "array":
        if not isinstance(value, list):
            errors.append(f"{path}: expected array, got {type(value).__name__}")
        else:
            for i, item in enumerate(value):
                errors += check_value(item, schema.get("items", {}), f"{path}[{i}]")
    elif schema_type == "object" or "properties" in schema:
        if not isinstance(value, dict):
            errors.append(f"{path}: expected object, got {type(value).__name__}")
        else:
            props = schema.get("properties", {})
            for key, val in value.items():
                if key not in props:
                    errors.append(f"{path}.{key}: not defined in schema")
                else:
                    errors += check_value(val, props[key], f"{path}.{key}")
            for req in schema.get("required", []):
                if req not in value:
                    errors.append(f"{path}.{req}: required field missing")
    else:
        enum = schema.get("enum")
        if enum and value not in enum:
            errors.append(f"{path}: value {value!r} not in enum {enum}")
    return errors

all_errors = []
for route, methods in spec.get("paths", {}).items():
    for verb, op in methods.items():
        if verb not in ("get", "post", "put", "patch", "delete"):
            continue
        for status, resp in (op.get("responses") or {}).items():
            content = resp.get("content", {}) if isinstance(resp, dict) else {}
            for media_type, body in content.items():
                examples = body.get("examples") or {}
                schema = body.get("schema", {})
                for ex_name, ex in examples.items():
                    value = ex.get("value")
                    label = f"{route} {verb.upper()} {status} examples.{ex_name}"
                    all_errors += check_value(value, schema, label)

if all_errors:
    print("EXAMPLES INVALID:")
    for e in all_errors:
        print(f"  - {e}")
    sys.exit(1)
print("All examples validate against their schemas.")
EOF
```

Expected: `All examples validate against their schemas.` (this matches the
manual finding from the design phase — confirms the gate script is correct,
not just that the API happens to be clean).

- [ ] **Step 4: Commit**

```bash
git add plugins/agents/hmcts-apim-sdlc-orchestrator/agents/catalog-publisher.md
git commit -m "AMP-569: realign catalog-publisher with canonical amp-catalog process, add examples gate"
```

---

### Task 4: Sync README, plugin.json, and marketplace.json

**Files:**
- Modify: `plugins/agents/hmcts-apim-sdlc-orchestrator/README.md`
- Modify: `plugins/agents/hmcts-apim-sdlc-orchestrator/.claude-plugin/plugin.json`
- Modify: `.claude-plugin/marketplace.json`

**Interfaces:**
- Consumes: skill/agent names from Tasks 1–3 (`springboot-api-from-template`, `springboot-service-from-template`, `catalog-publisher`) — names only, for doc tables.
- Produces: nothing consumed by later tasks — this is the doc-sync leaf.

- [ ] **Step 1: Update the README "What's inside" table**

In `plugins/agents/hmcts-apim-sdlc-orchestrator/README.md`, replace the
"What's inside" table row content:

```markdown
| Component | Items |
|---|---|
| **Agents** (`agents/`) | `requirements-analyst`, `apim-architect`, `story-writer`, `contract-test-engineer`, `implementation`, `code-reviewer`, `ci-orchestrator`, `deployer`, `catalog-publisher` (eligibility-checked, examples-gated) — full self-contained pipeline |
| **Skills** (`skills/`) | `openapi-spec-reviewer` — reviews a spec against 4 lenses (data-sharing/UK-GDPR, infrastructure-SLA/Azure, API standards, security); scored /100; `bootstrap-context` — writes `.claude/CLAUDE.md` with correct context imports (also runs automatically on session start); `springboot-api-from-template` — bootstraps a new `api-cp-*` repo from the HMCTS template, with team-ownership and git-access verification; `springboot-service-from-template` — bootstraps a new `service-cp-*` repo from the HMCTS template, chaining to `springboot-api-from-template` if the matching API repo doesn't exist yet |
| **Context** (`context/`) | `api-spec-shared`, `service-shared`, `shared-code-rules`, `hmcts-standards`, `logging-standards`, `azure-sdk-guide`, `claude-md-standards` |
| **Hooks** (`hooks/`) | `block-pii`, `block-secrets`, `guard-bash`, `guard-paths`, `bootstrap-context` (SessionStart — auto-creates `.claude/CLAUDE.md` in `api-cp-*`/`service-cp-*` repos) |
| **Orchestration** | `CLAUDE.md` — the dual-path, contract-first pipeline |
```

- [ ] **Step 2: Update `plugin.json` version and description**

In `plugins/agents/hmcts-apim-sdlc-orchestrator/.claude-plugin/plugin.json`:

```json
{
  "name": "hmcts-apim-sdlc-orchestrator",
  "version": "1.1.0",
  "description": "HMCTS API-Marketplace SDLC orchestrator — a fully self-contained, contract-first pipeline for OpenAPI-first api-cp-* spec libraries and service-cp-* Spring Boot services. Bundles all pipeline agents (requirements-analyst, apim-architect, story-writer, contract-test-engineer, implementation, code-reviewer, ci-orchestrator, deployer, catalog-publisher), the openapi-spec-reviewer and bootstrap-context skills, the forked springboot-api-from-template / springboot-service-from-template repo-bootstrap skills (with git-access verification), APIM context docs, and guard hooks. catalog-publisher runs a mandatory eligibility check and validates OpenAPI examples against their schemas before registering. Targets GHA + ADO CI/CD, PMD, CodeQL, GHCR, and the cp-vp-aks-deploy GitOps repo.",
  "author": {
    "name": "HMCTS APIM"
  },
  "license": "MIT",
  "keywords": [
    "hmcts",
    "apim",
    "api-marketplace",
    "sdlc",
    "orchestrator",
    "openapi",
    "spring-boot",
    "contract-first",
    "agents",
    "pipeline"
  ]
}
```

- [ ] **Step 3: Verify `plugin.json` is still valid JSON**

```bash
jq . plugins/agents/hmcts-apim-sdlc-orchestrator/.claude-plugin/plugin.json > /dev/null && echo "VALID JSON"
```

Expected: `VALID JSON`

- [ ] **Step 4: Update the marketplace.json entry (also fixes a pre-existing stale claim)**

In `.claude-plugin/marketplace.json`, the `hmcts-apim-sdlc-orchestrator` entry
(around line 105) currently says *"Reuses hmcts-sdlc-orchestrator generic
agents by reference"* — false; the plugin's own `CLAUDE.md` says the opposite
("Do not use `hmcts-sdlc-orchestrator` agents... they target a different
stack"). Replace the whole entry:

```json
    {
      "name": "hmcts-apim-sdlc-orchestrator",
      "source": "./plugins/agents/hmcts-apim-sdlc-orchestrator",
      "description": "HMCTS API-Marketplace SDLC orchestrator: contract-first dual-path pipeline for OpenAPI-first api-cp-* spec libraries and service-cp-* Spring Boot services. Fully self-contained — bundles its own pipeline agents (requirements-analyst, apim-architect, story-writer, contract-test-engineer, implementation, code-reviewer, ci-orchestrator, deployer, catalog-publisher), the openapi-spec-reviewer and bootstrap-context skills, and the forked springboot-api-from-template / springboot-service-from-template repo-bootstrap skills. catalog-publisher is eligibility-checked and examples-gated. Does not reuse hmcts-sdlc-orchestrator agents — that plugin targets a different (CQRS/WildFly) stack.",
      "version": "1.1.0",
      "category": "agent",
      "tags": ["hmcts", "apim", "api-marketplace", "sdlc", "orchestrator", "openapi", "spring-boot", "contract-first"]
    },
```

- [ ] **Step 5: Verify `marketplace.json` is still valid JSON and the version bumped**

```bash
jq '.plugins[] | select(.name=="hmcts-apim-sdlc-orchestrator") | {version, description}' .claude-plugin/marketplace.json
```

Expected: `version` is `"1.1.0"` and `description` no longer contains the
string `"Reuses hmcts-sdlc-orchestrator"`.

- [ ] **Step 6: Commit**

```bash
git add plugins/agents/hmcts-apim-sdlc-orchestrator/README.md \
        plugins/agents/hmcts-apim-sdlc-orchestrator/.claude-plugin/plugin.json \
        .claude-plugin/marketplace.json
git commit -m "AMP-569: sync docs/versions for forked template skills + catalog-publisher realignment"
```

---

### Task 5: Plugin verification pass

**Files:** none (verification only, per this repo's own "Testing a plugin
after creation or migration" convention in `CLAUDE.md`).

**Interfaces:**
- Consumes: all files from Tasks 1–4.
- Produces: a verified, reloadable plugin state — the gate before Task 6's
  real-world action.

- [ ] **Step 1: Run the code-review skill on the branch**

Invoke the `code-review:review` skill on the current branch. Fix every
**Must fix**, **Should fix**, and **Nit** finding before continuing.

- [ ] **Step 2: Reload plugins**

Run `/reload-plugins`. Confirm the summary line shows the skill count for
`hmcts-apim-sdlc-orchestrator` increased by 2 (the two forked skills) and
there are zero load errors for this plugin.

- [ ] **Step 3: Run `/doctor`**

Expected output: `"Claude Code diagnostics dismissed"`. If anything else
appears, fix the flagged file and re-reload before proceeding.

- [ ] **Step 4: Smoke-test the bootstrap skill trigger (dry-run, no `gh repo create`)**

Ask: *"Bootstrap a new api-cp-crime-caseadmin-demo repo"* and confirm Claude
responds by invoking `springboot-api-from-template` and asking for the
required input (Step 1's six items) — stop before any `gh repo create` call;
this is a trigger check, not an execution.

- [ ] **Step 5: Smoke-test the catalog-publisher trigger**

Ask: *"Register api-cp-crime-hearing in the catalog"* and confirm Claude
invokes `catalog-publisher` and starts with **Step 1 — the eligibility
question** ("is this API external and safe to expose publicly?") before
anything else. This confirms the gate is first, not buried.

---

### Task 6: Register `api-cp-crime-hearing` in the catalog

**Files:** none in `agentic-plugins-marketplace`. This task operates on
`amp-catalog` (clone/branch/PR) and reads from the live `api-cp-crime-hearing`
Pages site. **Human gate:** confirm with the user before pushing/opening the
PR — this creates a real, visible change in `hmcts/amp-catalog`.

**Interfaces:**
- Consumes: the rewritten `catalog-publisher` agent (Task 3).
- Produces: a merged-or-pending PR adding `api-cp-crime-hearing` to
  `amp-catalog/docs/apis.json`.

- [ ] **Step 1: Run the eligibility check**

`api-cp-crime-hearing` exposes read-only hearing lifecycle data to RaS and
HMPPS/Prison services per its own spec `info.description` — external,
documentation-only. Confirm with the user this is correct before continuing
(per catalog-publisher Step 1).

- [ ] **Step 2: Confirm the workflow chain and live Pages site**

Already confirmed during design (this plan's spec doc references the same
checks):

```bash
cat /Users/srivanimuddineni/HMCTS/APIM/api-cp-crime-hearing/.github/workflows/publish-api-docs.yml
curl -sS -o /dev/null -w "HTTP %{http_code}\n" "https://hmcts.github.io/api-cp-crime-hearing/openapi-spec.yml"
```

Expected: the workflow file `uses:` the reusable `publish-swagger-ui.yml@v1`,
and the curl returns `HTTP 200`.

- [ ] **Step 3: Run the examples gate**

```bash
curl -sf "https://hmcts.github.io/api-cp-crime-hearing/openapi-spec.yml" -o /tmp/spec.yml
```

Run the same validation script as Task 3 Step 3 (Dry-run). Expected:
`All examples validate against their schemas.`

- [ ] **Step 4: Read metadata and confirm it's not already listed**

```bash
python3 -c "
import yaml
with open('/tmp/spec.yml') as f:
    info = yaml.safe_load(f).get('info', {})
print('title:', info.get('title'))
print('description:', info.get('description'))
"
gh repo clone hmcts/amp-catalog /tmp/amp-catalog 2>/dev/null || git -C /tmp/amp-catalog pull --ff-only
python3 -c "
import json
with open('/tmp/amp-catalog/docs/apis.json') as f:
    data = json.load(f)
print('already listed:', any(a['name']=='api-cp-crime-hearing' for a in data['apis']))
"
```

Expected: `already listed: False` (confirmed missing during design).

- [ ] **Step 5: Derive the team and add the entry**

```bash
gh api repos/hmcts/api-cp-crime-hearing/contents/.github/CODEOWNERS \
  --header "Accept: application/vnd.github.raw" 2>/dev/null \
  | grep -v '^#' | grep -v '^$' | head -1 \
  | awk '{for(i=2;i<=NF;i++) if($i ~ /^@hmcts\//) {gsub("@hmcts/","",$i); print $i; exit}}'
```

Use the result (or `"AMP"` if none found) as `TEAM`, then add the entry to
`/tmp/amp-catalog/docs/apis.json` using the same additive-only Python snippet
as `catalog-publisher` Step 10, with `REPO="api-cp-crime-hearing"` and
`TITLE`/`DESCRIPTION` from Step 4 above.

- [ ] **Step 6: Confirm with the user, then raise the PR**

Show the user the exact entry to be added and ask for explicit go-ahead
before pushing, since this opens a real PR against `hmcts/amp-catalog`. Once
confirmed:

```bash
cd /tmp/amp-catalog
git checkout -b catalog/add-api-cp-crime-hearing
git add docs/apis.json
git commit -m "feat(catalog): add api-cp-crime-hearing to API registry"
git push origin catalog/add-api-cp-crime-hearing
gh pr create \
  --repo hmcts/amp-catalog \
  --title "feat(catalog): add api-cp-crime-hearing" \
  --base main
```

- [ ] **Step 7: Report the PR URL to the user**

Hand back the PR URL from Step 6's output — this task ends at "PR opened,"
not "PR merged"; merging is the catalog maintainers' call.