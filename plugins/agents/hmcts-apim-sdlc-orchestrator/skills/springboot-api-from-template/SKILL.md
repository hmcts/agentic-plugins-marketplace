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