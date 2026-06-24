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

Enable "Automatically delete head branches", then import the main-branch
ruleset **via the API, not the GitHub UI's "New ruleset" flow** (same as the
API skill's Step 6) — `gh repo create --template` does not carry rulesets
over, and clicking through "New ruleset" in the UI defaults
`required_approving_review_count` to `0`, silently leaving the new repo
mergeable without review. This was found live on a freshly-created
`service-cp-*` repo whose ruleset had `required_approving_review_count: 0`
despite the template's own `.github/rulesets/main.json` correctly specifying
`1` — the gap is in *how* the ruleset gets imported, not the template file:

```bash
gh api --method POST repos/hmcts/{service-name}/rulesets \
  --input service-hmcts-crime-springboot-template/.github/rulesets/main.json
```

(Adjust the `--input` path to wherever the template was cloned/checked out.
Do not hand-recreate the ruleset's JSON via UI clicks or `-f`/`-F` flags —
`gh api -F` does not reliably build the nested `rules[]` array of objects;
always import the template's actual file with `--input`.)

### Step 5.5 — Verify the imported ruleset, not just its presence (new)

```bash
gh api repos/hmcts/{service-name}/rulesets \
  --jq '.[] | select(.name=="main") | .rules[] | select(.type=="pull_request") | .parameters.required_approving_review_count'
```

This must print `1` (or whatever non-zero value the template specifies) —
**never `0`**. If it prints `0`, the import silently dropped or zeroed the
field; do not just flag it, fix it immediately by re-importing
(`gh api --method PUT repos/hmcts/{service-name}/rulesets/{id} --input
{the-template-json}`) and re-check. A `0` value is always a bug, not a policy
trade-off — unlike the deadlock check below, it is safe to fix without asking.

Separately, compare the (now-verified-non-zero) count against the Step 4.5
member count; flag — don't silently fix — if the required review count would
deadlock the team's own PRs (e.g. a 1-person team needing 2 approvals). That
one *is* a policy trade-off for the user to decide.

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
   the "New team member setup" section below. While editing it, **strip the
   template's generic boilerplate** rather than carrying it into every new
   repo verbatim:
   - Delete the "About this template", "Want to Build Your Own Path?", and
     "Implementation Patterns & Demo Project" sections (the full demo-repo
     table). They describe the template, not this service — link to the
     [template README](https://github.com/hmcts/service-hmcts-crime-springboot-template/blob/main/README.md)
     and its [docs](https://github.com/hmcts/service-hmcts-crime-springboot-template/blob/main/docs)
     instead of inlining them.
   - Delete the inline "Prerequisites" / "Installation" / "Static code
     analysis" sections (Java/Gradle/PMD setup) for the same reason — generic
     build instructions belong in the template's own README, not duplicated
     per repo.
   - Delete `docs/PIPELINE.md` and `docs/SpringUpgradev4.md` from the new
     repo (or any other doc that narrates the *template's* own development
     history rather than this service) — they reference classes and
     decisions from the template's lineage that don't exist in the new repo,
     and rot immediately. Keep only docs that are genuinely about this
     service (e.g. `docs/Logging.md` if customised).
   - Keep everything that's actually specific to this repo: the API
     contract, upstream/downstream calls, owning team, support model, and
     the "New team member setup" section.
   - Reference: this exact trim was done after-the-fact for
     `service-cp-crime-hearing` — see its README/PR history for the target
     shape. Doing it here at scaffold time avoids a repeat cleanup PR.

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
- [ ] Branch-protection `required_approving_review_count` confirmed non-zero (Step 5.5) — fixed immediately if it printed `0`.
- [ ] Branch-protection required-reviewer count checked against team size (Step 5.5).
- [ ] New-member setup steps documented in the new repo's `README.md`.
- [ ] Service name follows convention and avoids forbidden tokens.
- [ ] Step 2 resolved the API repo (existing + version, or created via `springboot-api-from-template`) **before** the service repo was created.
- [ ] `build.gradle` `apiSpec` line replaced with the service's own coordinate.
- [ ] `spring.application.name` and metrics tags match the repo name.
- [ ] Java package renamed; `Example*` sample code removed.
- [ ] `README.md` describes the new service, owners, support model.
- [ ] `README.md` stripped of generic template boilerplate (demo-project
      catalogue, "About this template", inline build/PMD instructions) —
      links to the template README/docs instead of inlining them.
- [ ] `docs/PIPELINE.md` / `docs/SpringUpgradev4.md` (or equivalent
      template-history docs) removed, not carried into the new repo.
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