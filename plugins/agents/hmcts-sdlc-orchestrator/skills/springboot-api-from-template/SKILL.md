---
name: springboot-api-from-template
description: Start a new HMCTS Marketplace API specification repo using the canonical HMCTS template (api-hmcts-crime-template) as master source. Use when creating a new API spec repo (OpenAPI-first, spec-only) distinct from a runtime Spring Boot service.
---

# HMCTS Marketplace API from Template

This skill stands up a new OpenAPI specification repository from the HMCTS
template. API spec repos are distinct from runtime services:

- **api-*** repos contain the OpenAPI spec, validation tooling, generators,
  and publishing workflows. They produce the spec artefact consumed by
  services.
- **service-*** repos contain the runtime Spring Boot implementation and
  consume one or more api-* artefacts. Use `springboot-service-from-template`
  for those.

Do not mix runtime code into an api-* repo.

## API-first — why this skill runs before `springboot-service-from-template`

Every HMCTS Spring Boot service has a matching API repo. This skill produces
that API repo, and it is intended to run **before** the service skill —
ideally with time in between to review the contract with consumers.

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

- API repo: `api-{source-system}-[case-type]-{business-domain}-{entity}`
- Service repo: `service-{source-system}-[case-type]-{business-domain}-{entity}`

If a user jumps straight to `springboot-service-from-template` without an
API repo in place, redirect them here first.

## Master source

**GitHub:** https://github.com/hmcts/api-hmcts-crime-template

Everything under `build.gradle`, `gradle/`, `.github/workflows/`, and the
validation tooling belongs to the template. This skill must not inline those
files.

## Context to pull in

- `context/coding-standards.md` — naming, commit conventions.
- `context/hmcts-standards.md` — compliance and accessibility baseline.
- `context/tech-stack.md` — version pins.

For design decisions made during the API work, invoke `skills/adr-template.md`.

## When to use

- User says "create a new HMCTS API", "new API marketplace repo",
  "scaffold an OpenAPI spec repo".
- The work is specification-only: no runtime code, no database, no controllers.
- A new entity, reference-data resource, or business-domain API needs a repo.

## Do **not** use this skill for

- Runtime Spring Boot services — use `springboot-service-from-template`.
- Legacy RAML-based `cpp-context-*` API modules — those follow
  `context-service-guide` / `context-scaffold` and use different conventions.

---

## Required input

Ask the user (one question at a time is fine; batch if they've already volunteered some):

1. **Repo name** — must follow HMCTS Marketplace naming conventions:
   - Standard APIs: `api-{source-system}-[case-type]-{business-domain}-{name-of-entity}`.
   - Reference data APIs: `api-cp-refdata-{product-domain}-{name-of-entity}`
     (`product-domain` is **required** for reference data — global ownership
     means no ownership).
   - `source-system` examples: `cp`, `dcs`, `sscs`.
   - `case-type` (optional): `civil` | `crime` | `family` | `tribunal`.
   - `business-domain` examples on CP: `caseingestion`, `casematerial`,
     `caseadmin`, `casehearing`, `schedulingandlisting`.
   - **Forbidden tokens:** `common`, `core`, `base`, `utils`, `helpers`,
     `misc`, `shared`.
2. **Owning GitHub team slug** — the team that will own the repo. **Prerequisite** — the repo will not be created without one. The team must already exist in the `hmcts` org; if it does not, stop and ask the org admins to create the team first. Optional: a secondary team slug plus its permission (usually `push`).
3. **Short description** — one-line summary used on the GitHub repo and in the new `README.md`.
4. **Owning product team context** — the human product team name, on-call/support model, and escalation path (used to populate `README.md`; distinct from the GitHub team slug above).
5. **API version** — SemVer baseline + media type per
   `docs/API-VERSIONING-STRATEGY.md` in the template.
6. **Primary consumers** — which services will consume this spec.

If any are unknown, stop and surface as an open question. **A repo without an owning GitHub team must not be created** — ownership-before-creation is a hard rule. If the team doesn't exist, it must be created first (an org-owner action), then this skill continues.

**GitHub owner is not a user input.** The default owner is `hmcts`; use it without asking. Only deviate if the user has already told you the repo belongs in a different org — and even then, treat it as an exception, not a choice.

**Repo visibility is not a user input.** HMCTS operates under "Coding in the Open" — new API spec repos are created **public**. Do not ask, do not offer a private option, do not pass `--private`. The only exception is an ADR explicitly approved by the tech lead citing a legal/classification constraint; without one, the repo is public.

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

### Step 2 — Create the repo from the template (via GitHub API)

Use the GitHub API (`POST /repos/{template_owner}/{template_repo}/generate`) via the `gh` CLI — the scripted equivalent of the UI's "Use this template" button.

**Command**

Do not run this before all inputs above are confirmed with the user and the owning team has been validated (Step 1). Once confirmed:

```bash
gh repo create hmcts/{api-name} \
  --template hmcts/api-hmcts-crime-template \
  --public \
  --description "{short description}" \
  --clone
```

- Owner is `hmcts`. Do not substitute another org unless the user has explicitly said the repo belongs elsewhere.
- `--public` is **mandatory**. Do not substitute `--private`. If the user asks for private, pause and require an ADR citing the legal/classification reason before proceeding.
- `--clone` drops the working copy next to the current directory; `cd` into it before continuing with the remaining steps.

### Step 3 — Grant the owning team access

Immediately after creation — before any other customisation — grant the owning GitHub team access. Do not defer this.

```bash
gh api --method PUT \
  /orgs/hmcts/teams/{team-slug}/repos/hmcts/{api-name} \
  -f permission=admin
```

- Default permission for the owning team is `admin` — the team must be able to manage settings, secrets, and collaborators.
- If a secondary team was supplied, grant it with the lower permission the user specified (usually `push`):
  ```bash
  gh api --method PUT \
    /orgs/hmcts/teams/{secondary-team-slug}/repos/hmcts/{api-name} \
    -f permission=push
  ```

**Verify**

```bash
gh api /repos/hmcts/{api-name}/teams --jq '.[] | {slug, permission}'
```

Expected output includes the owning team with permission `admin` (and any secondary team at its requested permission).

### Step 4 — Post-creation bookkeeping

1. Confirm visibility and template lineage:
   ```bash
   gh repo view hmcts/{api-name} --json visibility,templateRepository
   ```
   Expected: `visibility: "PUBLIC"`, `templateRepository.name: "api-hmcts-crime-template"`.
2. `cd {api-name}` — subsequent steps run inside the new working copy.

**UI fallback**

If `gh` is unavailable or the user explicitly prefers the UI, use GitHub → template repo → **"Use this template"** → **"Create a new repository"**. Owner: `hmcts`. Visibility: **Public** (do not select Private). After creation, go to Settings → Collaborators and teams → Add the owning team with `Admin`. Clone locally. The no-repo-without-a-team rule still applies in the UI path — the team grant is not optional.

### Step 5 — Read the template supporting docs

Read in full before editing anything:

- `README.md` — naming convention, setup, cleanup.
- `docs/API-VERSIONING-STRATEGY.md` — media type + SemVer versioning rules.
- `docs/OPENAPI-FILE-CONVENTIONS.md` — file and content conventions.
- `docs/OPENAPI-SPEC-VERSIONING.md` — rules for evolving the spec.
- `docs/CHAIN_OF_CUSTODY.md` — supply chain audit requirements.
- `docs/DATA-PRODUCTS.md` — structured data output expectations.
- `docs/GITHUB-ACTIONS.md` — required secrets and variables.

Align any open questions against `https://hmcts.github.io/restful-api-standards/`.

### Step 6 — Post-template manual steps

Follow the template README:

1. Settings → General → enable "Automatically delete head branches".
2. Import `.github/rulesets/main-branch-protection.json` into repo rulesets,
   then delete that JSON from the new repo.
3. Delete files only meaningful in the template:
   - `./docs/*` (replace with repo-specific docs).
   - `./src/main/resources/openapi/deleteme`.
4. Rewrite `README.md` for the new API.

### Step 7 — Write the OpenAPI spec

- Location: `src/main/resources/openapi/openapi-spec.yml`.
- Structure and conventions: per `docs/OPENAPI-FILE-CONVENTIONS.md`.
- Response schemas, request schemas, and error shapes conform to
  `https://hmcts.github.io/restful-api-standards/`.
- Every endpoint documents: auth, error responses, pagination, media type,
  version.
- Keep the spec the single source of truth — consumer services generate
  clients / controllers from this artefact; do not write the controllers here.

### Step 8 — Versioning

- Media-type versioning on requests: `Accept: application/vnd.hmcts.<resource>.v1+json`.
- SemVer on the spec artefact published from this repo.
- Breaking changes require a new major version and an ADR in the consumer
  services that adopt it.

### Step 9 — Configure GitHub Actions

- Add the secrets and variables listed in `docs/GITHUB-ACTIONS.md`.
- Enable repo rulesets.
- Do not fork the workflows locally — if a workflow must change, open a PR
  against the template.

### Step 10 — Publish the spec artefact

The template's publish workflow emits the spec as a Maven artefact that
consumer services depend on (`apiSpec "uk.gov.hmcts.cp:api-{...}:X.Y.Z"`).
Consumers generate their controllers from this artefact.

---

## Quick-check before marking "done"

- [ ] Owning GitHub team was validated (`gh api /orgs/hmcts/teams/{slug}` returned the team) **before** the repo was created.
- [ ] Repo created via `gh repo create ... --template ... --public` (or the UI fallback with Public selected).
- [ ] `gh repo view --json visibility` returns `"PUBLIC"`.
- [ ] Owning team granted `admin` on the repo — `gh api /repos/hmcts/{api-name}/teams` shows it.
- [ ] Repo name follows naming convention and avoids forbidden tokens.
- [ ] Owning team named in README.md (not a generic team handle).
- [ ] Template `docs/*` rewritten or removed.
- [ ] `deleteme` sample artefact removed from `src/main/resources/openapi/`.
- [ ] `openapi-spec.yml` conforms to `https://hmcts.github.io/restful-api-standards/`.
- [ ] Versioning strategy stated (media type + SemVer).
- [ ] Required GitHub secrets/variables configured.
- [ ] Main branch ruleset imported and `.github/rulesets/main-branch-protection.json` deleted.
- [ ] No runtime Java code introduced — this repo is spec + build tooling only.

## Divergence policy

The template owns the validation tooling, publishing workflow, and naming.
Propose changes upstream rather than forking locally.
