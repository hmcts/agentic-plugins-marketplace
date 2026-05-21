---
name: springboot-service-from-template
description: Stand up a new HMCTS Spring Boot service using the canonical HMCTS template (service-hmcts-crime-springboot-template) as master source. Use when creating a new Spring Boot service or replacing a legacy WildFly context service with a modern Spring Boot equivalent.
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

- `context/azure-cloud-native.md` — posture and Shared Responsibility Model.
- `context/azure-sdk-guide.md` — Managed Identity, Key Vault, Service Bus.
- `context/logging-standards.md` — mandatory JSON logging.
- `context/tech-stack.md` — version pins.
- `context/coding-standards.md` — Java/Spring conventions.

## When to use

- User says "create a new HMCTS Spring Boot service", "bootstrap a microservice",
  "replace the WildFly service with Spring Boot", "spin up a new backend".
- User is about to start a new repo for a Spring Boot service.
- User has a repo created from the GitHub template and needs to tailor it.

## Do **not** use this skill for

- API specification repos — use `springboot-api-from-template` instead.
- Legacy `cpp-context-*` WildFly services — those follow
  `context-service-guide` / `context-scaffold`, and those patterns
  **must not** bleed into new Spring Boot services.

## API-first — handled inline in Step 2

Every HMCTS Spring Boot service has a matching API repo, and the API repo
comes first. This skill enforces that operationally in **Step 2** — it asks
for the API repo name, offers to derive it from the service name by
convention, checks the repo exists, and if it doesn't, delegates to
`springboot-api-from-template` to create it before the service repo is ever
touched.

- Pair convention: if the service is `service-cp-crime-caseadmin-hearings`,
  the API repo is `api-cp-crime-caseadmin-hearings` — same suffix.
- The service consumes the API via the `apiSpec` configuration in
  `build.gradle` — see Step 8 below. The template ships a placeholder
  (`uk.gov.hmcts.cp:api-hmcts-crime-template:X.Y.Z`); the service repo
  replaces it with the coordinate of its own API repo's published artefact.

The rationale is captured in `context/hmcts-standards.md` → "API-first
design". Do not collapse contract and implementation into one repo.

---

## Required input

Ask the user (one question at a time is fine; batch if they've already volunteered some):

1. **Service name** — must follow `service-{source-system}-[case-type]-{business-domain}-{name-of-entity}`.
   - `source-system`: `cp` (Common Platform), `dcs` (Crown Court Digital Case System), `sscs`, etc.
   - `case-type` (optional): `civil` | `crime` | `family` | `tribunal`.
   - `business-domain`: e.g., `caseingestion`, `caseadmin`, `casehearing`, `schedulingandlisting`.
   - `name-of-entity`: the specific entity/resource.
   - **Forbidden tokens:** `common`, `core`, `base`, `utils`, `helpers`, `misc`, `shared`. Global ownership = no ownership.
2. **Owning GitHub team slug** — the team that will own the repo. **Prerequisite** — the repo will not be created without one. The team must already exist in the `hmcts` org; if it does not, stop and ask the org admins to create the team first. Optional: a secondary team slug plus its permission (usually `push`).
3. **Short description** — one-line summary used on the GitHub repo and in the new `README.md`.
4. **Java package root** — `uk.gov.hmcts.cp.{business-domain}.{entity}` (or the project's equivalent).
5. **Upstream / downstream** — which services does this call, and which call it?
6. **Stateful?** — does it need Postgres? (Flyway + Testcontainers wiring is already in the template.)
7. **Azure integrations expected** — Service Bus topics/queues, Key Vault references, App Configuration usage. Trigger `azure-sdk-guide.md` if any are planned.
8. **Ownership context** — on-call rota, support model, escalation path (used to populate `README.md`; distinct from the GitHub team slug above).

The **matching API repo name and published artefact version** are captured interactively in Step 2 — do not ask for them in this list. Step 2 offers to derive the API repo name from the service name by convention, lets the user override, looks up the repo, and either captures its version or delegates to `springboot-api-from-template` to create the API repo first.

If any of these are unknown, surface as an open question before proceeding. **A repo without an owning GitHub team must not be created** — ownership-before-creation is a hard rule. If the team doesn't exist, the team must be created first (an org-owner action), then this skill continues.

**GitHub owner is not a user input.** The default owner is `hmcts`; use it without asking. Only deviate if the user has already told you the repo belongs in a different org (e.g., `hmcts-contino`) — and even then, treat it as an exception, not a choice.

**Repo visibility is not a user input.** HMCTS operates under "Coding in the Open" — new service repos are created **public**. Do not ask, do not offer a private option, do not pass `--private`. The only exception is an ADR explicitly approved by the tech lead citing a legal/classification constraint; without one, the repo is public.

---

## Process

### Step 1 — Validate the owning GitHub team exists

**Do not skip this step and do not proceed to repo creation until it passes.** A repo without an owning team is unowned; unowned repos are forbidden.

**Prerequisites**

- `gh` CLI installed and authenticated (`gh auth status`).
- The authenticated user has permission to create repos in `hmcts` and at least team-maintainer or org-owner rights for the chosen team.

**Validate**

```bash
gh api /orgs/hmcts/teams/{team-slug} --jq '.slug, .name'
```

- If the call returns the team slug and name, proceed.
- If it returns `Not Found`, stop. Ask an `hmcts` org owner to create the team first. Do not proceed to Step 2, and do not fall back to creating the repo with only a user as admin.
- Repeat for the optional secondary team, if one was supplied.

Helpful: `gh api /orgs/hmcts/teams --paginate --jq '.[].slug'` lists all team slugs.

### Step 2 — Confirm (or create) the matching API repo

Every service has a matching API repo. Resolve it before the service repo is created.

**Ask the user — in this order**

1. **"What's the API repo name for this service?"** — do not accept "whatever, just pick one"; the user must either type it or accept a derived default.
2. Offer the derived default based on the service name: swap the `service-` prefix for `api-`. For a service called `service-cp-crime-caseadmin-hearings`, the derived API repo name is `api-cp-crime-caseadmin-hearings`. Ask: **"Use `{derived-name}`, or provide a different name?"**
3. Capture the final API repo name as `{api-name}`.

**Check whether the API repo already exists**

```bash
gh repo view hmcts/{api-name} --json name,visibility,isTemplate 2>/dev/null
```

- **Exists** → proceed to "confirm the API is ready to consume" below.
- **Not found** → proceed to "create the API repo first" below.

**If the API repo exists — confirm it's ready to consume**

1. Ask the user for the published API artefact version they want the service to depend on — SemVer only, never a snapshot or a branch name. If they don't know, stop and ask them to check the API repo's publish workflow / release list before resuming.
2. Record the coordinate `uk.gov.hmcts.cp:{api-name}:{version}` — Step 8 replaces the template's `apiSpec` placeholder with this.

**If the API repo does not exist — create it first**

The service must not be created before the API. Halt this skill's service-creation flow and delegate:

1. Invoke `springboot-api-from-template` with the name the user provided as `{api-name}`. Pass through any inputs already collected that apply (owning team, owner, description — "API spec for `{service-name}`" is a reasonable default description).
2. After the API skill completes — the repo exists, the spec has been drafted, and a first version has been published — return to this skill and resume Step 3 with the new coordinate in hand.
3. If the API skill cannot complete (e.g., the owning team doesn't exist yet or consumer review is still open), surface that as a blocker. Do not create the service repo and do not wire a placeholder coordinate hoping to fix it later.

**Important** — do not fall back to pointing the service at the template's own API (`uk.gov.hmcts.cp:api-hmcts-crime-template:X.Y.Z`). That placeholder exists only so the template itself can build; it is not a valid production coordinate.

### Step 3 — Create the repo from the template (via GitHub API)

Use the GitHub API (`POST /repos/{template_owner}/{template_repo}/generate`) via the `gh` CLI. This is the scripted equivalent of the UI's "Use this template" button and preserves the template settings GitHub needs to keep the lineage intact.

**Command**

Do not run this before all inputs above are confirmed with the user and the owning team has been validated (Step 1). Once confirmed:

```bash
gh repo create hmcts/{service-name} \
  --template hmcts/service-hmcts-crime-springboot-template \
  --public \
  --description "{short description}" \
  --clone
```

- Owner is `hmcts`. Do not substitute another org unless the user has explicitly said the repo belongs elsewhere.
- `--public` is **mandatory**. Do not substitute `--private`. If the user asks for private, pause and require an ADR citing the legal/classification reason before proceeding.
- `--clone` drops the working copy next to the current directory; `cd` into it before continuing with the remaining steps.
- Add `--include-all-branches` only if the team explicitly needs the template's non-default branches (rare).

### Step 4 — Grant the owning team access

Immediately after creation — before any other customisation — grant the owning GitHub team access. Do not defer this.

```bash
gh api --method PUT \
  /orgs/hmcts/teams/{team-slug}/repos/hmcts/{service-name} \
  -f permission=admin
```

- Default permission for the owning team is `admin` — the team must be able to manage settings, secrets, and collaborators.
- If a secondary team was supplied, grant it with the lower permission the user specified (usually `push`):
  ```bash
  gh api --method PUT \
    /orgs/hmcts/teams/{secondary-team-slug}/repos/hmcts/{service-name} \
    -f permission=push
  ```

**Verify**

```bash
gh api /repos/hmcts/{service-name}/teams --jq '.[] | {slug, permission}'
```

Expected output includes the owning team with permission `admin` (and any secondary team at its requested permission).

### Step 5 — Post-creation bookkeeping

1. Confirm the repo is public and the template lineage is recorded:
   ```bash
   gh repo view hmcts/{service-name} --json visibility,templateRepository
   ```
   Expected: `visibility: "PUBLIC"`, `templateRepository.name: "service-hmcts-crime-springboot-template"`.
2. Enable "Automatically delete head branches" and import the main-branch ruleset per the template's post-template manual steps.
3. `cd {service-name}` — every subsequent step is run inside the new working copy.

**UI fallback**

If `gh` is unavailable or the user explicitly prefers the UI, use GitHub → template repo → **"Use this template"** → **"Create a new repository"**. Owner: `hmcts`. Visibility: **Public** (do not select Private). After creation, go to Settings → Collaborators and teams → Add the owning team with `Admin`. Clone locally. The no-repo-without-a-team rule still applies in the UI path — the team grant is not optional.

### Step 6 — Read what the template already gives you

Read, in this order — do not modify yet:

- `README.md` — baseline requirements, prerequisites, build/test commands.
- `build.gradle` + `gradle/*.gradle` — Spring Boot version, Java version, plugin set, dependencies.
- `src/main/resources/application.yaml` — env-var-driven config, graceful shutdown, HTTP/2, forward-headers, probes, OTEL.
- `src/main/resources/logback.xml` — JSON logging (do not replace).
- `Dockerfile` — non-root, base image `hmcts/apm-services:*-jre`, App Insights agent via `lib/applicationinsights.json`.
- `.github/workflows/` — CI/CD, security scanning, ACR publish.
- `docs/SpringUpgradev4.md`, `docs/EnvironmentVariables.md`, `docs/JWTFilter.md`, `docs/Logging.md`, `docs/PIPELINE.md` — operational detail.

Confirm these match `context/tech-stack.md`. If they have diverged, trust the template and raise an issue to reconcile tech-stack.md.

### Step 7 — Service identity

Tailor the things that are genuinely service-specific:

1. `settings.gradle` — update `rootProject.name` to the service name.
2. `src/main/resources/application.yaml`:
   - `spring.application.name: service-UPDATE-TO-BE-NAME-OF-SERVICE` → the real name.
   - `management.metrics.tags.service` → the real name.
3. Rename the Java base package from the template placeholder to `uk.gov.hmcts.cp.{business-domain}.{entity}`.
4. Rename `Application.java` references accordingly.
5. Delete template sample code you aren't keeping — `ExampleController`, `ExampleService`, `ExampleRepository`, `ExampleMapper` and their tests. Keep `GlobalExceptionHandler`, `RootController`, filters, config.
6. Update `README.md` to describe the new service (purpose, owners, runbook link, escalation).

Do **not** change: `build.gradle` plugin block, the `apply from:` list, the `logback.xml` encoder/providers, or the Dockerfile non-root setup.

### Step 8 — Wire the API spec dependency (`apiSpec`)

The API repo name and version were captured (or the API repo was created) in Step 2. Apply them here.

The template's `build.gradle` has a dedicated `apiSpec` configuration that pulls in the API contract as a build-time artefact:

```groovy
dependencies {
  // Api spec
  apiSpec "uk.gov.hmcts.cp:api-hmcts-crime-template:2.0.2"
  ...
}
```

Replace the placeholder coordinate with **the coordinate captured in Step 2**:

```
uk.gov.hmcts.cp:{api-name}:{semver}
```

For example, a service `service-cp-crime-caseadmin-hearings` whose API repo is `api-cp-crime-caseadmin-hearings` at version `1.0.0`:

```groovy
apiSpec "uk.gov.hmcts.cp:api-cp-crime-caseadmin-hearings:1.0.0"
```

Rules:

- **Exactly one `apiSpec` line per service.** If the service needs to consume multiple APIs, stop and raise an ADR — this is a design smell that usually means the service boundary is wrong.
- The version must be a published SemVer from the API repo's publish workflow. Do not point at `SNAPSHOT` or a branch.
- If Step 2 could not produce a published version (e.g., the API repo exists but has no release yet), halt here too. Return to `springboot-api-from-template`, finish and publish the API, then resume.
- Do not change the `apiSpec` configuration itself (the `configurations { apiSpec }` block and `implementation.extendsFrom apiSpec`) — that wiring is owned by the template.
- Do not leave the template's `api-hmcts-crime-template` coordinate in place. That placeholder is for the template's own build; it is not a valid production dependency for a real service.

### Step 9 — Environment variables and secrets

Follow `docs/EnvironmentVariables.md` in the template:

- Local dev uses `.env` + `.envrc` with `direnv`. `.env` is gitignored.
- All runtime configuration is env-driven. No hardcoded endpoints.
- Managed Identity for Azure service auth — see `context/azure-sdk-guide.md`.
- Secrets resolved from Azure Key Vault. No connection strings in `application.yaml`.
- Server port is `SERVER_PORT` (default `8082`); expose explicitly in Helm values.

### Step 10 — Persistence (only if stateful)

The template already ships Flyway + Postgres + Testcontainers. To customise:

1. Add migration scripts under `src/main/resources/db/migration/V{n}__{description}.sql`.
2. Define JPA entities + Spring Data repositories in the service package.
3. Map to DTOs with MapStruct (already on the classpath).
4. Keep integration tests on Testcontainers; do not point them at real databases.

### Step 11 — CI/CD

The template wires `.github/workflows/ci-build-publish.yml`, `ci-draft.yml`, `ci-released.yml`, CodeQL, Trufflehog, gitleaks, PMD, and ACR publish. To activate:

1. Add repo-level GitHub secrets/variables per `docs/GITHUB-ACTIONS.md` in the API template (the conventions align).
2. Enable GitHub ruleset `main-branch-protection.json` if present.
3. Configure the Azure DevOps pipeline that builds the Docker image against ACR (referenced from `ci-build-publish.yml`).
4. Do not fork the workflows. If a workflow must change, open an issue / PR against the template.

### Step 12 — Helm + Flux CD

- Add a Helm chart under `cpp-helm-chart` (or the repo convention in use) referencing the new image.
- Set liveness `/actuator/health/liveness`, readiness `/actuator/health/readiness`.
- Set container `runAsNonRoot: true`, matching the Dockerfile user.
- Assign a User-Assigned Managed Identity to the Pod via `azure.workload.identity/use` annotation + federated credential.
- Register the service in `cpp-flux-config` for the correct environment.

### Step 13 — Observability wiring

- `spring-boot-starter-opentelemetry` is already on the classpath.
- Set `OTEL_TRACES_URL` and `OTEL_METRICS_URL` via Helm values per environment.
- App Insights Java agent is injected by the base image + `lib/applicationinsights.json`. Do **not** embed the App Insights SDK in code.
- Metrics tags `service` / `cluster` / `region` are already wired — populate `CLUSTER_NAME` and `REGION` in Helm.

### Step 14 — First-run verification

Run locally and confirm:

```bash
./gradlew build                     # compiles, runs tests, produces bootable jar
docker compose up                   # Postgres + any sidecars declared in template
./gradlew bootRun                   # starts the service
curl -i http://localhost:8082/actuator/health/readiness   # expect 200
curl -i http://localhost:8082/                            # expect RootController response
```

Watch stdout and confirm every line is JSON, parseable by `jq`, with `correlationId` and `requestId` in the MDC block. See `context/logging-standards.md`.

### Step 15 — ADR any deviation

Any step where the user wants to deviate from what the template provides
(different logging library, different JDBC driver, different base image,
bespoke messaging abstraction) requires an ADR before proceeding. Use
`skills/adr-template.md`.

---

## Quick-check before marking "done"

- [ ] Owning GitHub team was validated (`gh api /orgs/hmcts/teams/{slug}` returned the team) **before** the repo was created.
- [ ] Repo created via `gh repo create ... --template ... --public` (or the UI fallback with Public selected).
- [ ] `gh repo view --json visibility` returns `"PUBLIC"`.
- [ ] Owning team granted `admin` on the repo — `gh api /repos/hmcts/{service-name}/teams` shows it.
- [ ] Service name follows `service-...` naming convention and avoids forbidden tokens.
- [ ] Step 2 resolved the API repo — either confirmed an existing `api-*` repo with a published artefact version, or ran `springboot-api-from-template` to create one — **before** the service repo was created.
- [ ] API repo name follows the pair convention (`service-{suffix}` ↔ `api-{suffix}`), or a deliberate override was recorded.
- [ ] `build.gradle` `apiSpec` line replaced with the service's own API coordinate (`uk.gov.hmcts.cp:{api-repo-name}:{semver}`); the placeholder `api-hmcts-crime-template` coordinate is gone.
- [ ] `spring.application.name` and `management.metrics.tags.service` match the repo name.
- [ ] Java package renamed away from template placeholder.
- [ ] Template sample code removed (Example*); conventions kept (Exception handler, filters).
- [ ] `README.md` describes the new service, owners, and support model.
- [ ] No edits to `build.gradle` plugin block, the `apply from:` list, the `configurations { apiSpec }` block, `logback.xml`, or the Dockerfile user setup. (The `apiSpec` dependency *line* is the only expected change in `build.gradle`.)
- [ ] All config read from env vars; no connection strings, SAS tokens, or account keys anywhere.
- [ ] Azure services authenticated via Managed Identity (see `azure-sdk-guide.md`).
- [ ] JSON logs to stdout validated locally (see `logging-standards.md`).
- [ ] `/actuator/health/readiness` and `/actuator/health/liveness` return 200.
- [ ] Container user is `app` (non-root); base image from HMCTS ACR.
- [ ] Helm chart added with probes, MI annotation, resource limits.
- [ ] Flux config entry added for the target environment.
- [ ] ADR present for every deviation from the template.

## Divergence policy

The template is the master source. If the team wants a different default:

1. Propose the change on the template repo with an issue/PR.
2. Do **not** fork the default locally and call it the new standard.
3. If the change is accepted, every service picks it up on its next template
   refresh.
