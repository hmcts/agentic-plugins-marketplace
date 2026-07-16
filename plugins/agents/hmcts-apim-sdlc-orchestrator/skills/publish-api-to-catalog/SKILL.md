---
name: publish-api-to-catalog
description: Use when working inside an api-cp-* repo and the user wants to publish/expose their API docs, "add my API to the catalog", set up the publish-api-docs workflow, or get a hmcts.github.io docs site. Wires the current repo into the amp-catalog Swagger UI pipeline, handles the two one-time GitHub Pages admin gaps that fail silently otherwise, and verifies the live site. This is the per-repo counterpart to the catalog-publisher agent, which only touches amp-catalog/docs/apis.json.
---

# Skill: Publish API to Catalog

This is the canonical copy of `amp-catalog/.claude/skills/publish-api-to-catalog/SKILL.md`,
mirrored into this orchestrator so it's available whenever working inside an
`api-cp-*` repo without needing a local `amp-catalog` clone. Keep both in sync
if either changes.

Onboards the **current repository** to the API Catalog stop-gap: a public
Swagger UI site at `https://hmcts.github.io/<repo>/`, plus an automatic
listing in [amp-catalog](https://github.com/hmcts/amp-catalog).

The per-repo footprint is a single workflow file — most of this skill is
**checking** the API is safe to expose and **verifying** the result.

Run these phases in order. Do not skip Phase 2.

---

## Phase 1 — Locate and validate the OpenAPI spec

1. Confirm you are in an API repo (it has an OpenAPI spec). Find it:
   ```bash
   find . -path ./.git -prune -o -name "openapi-spec.y*ml" -print 2>/dev/null
   ```
   The HMCTS convention is `src/main/resources/openapi/openapi-spec.yml`. If
   there are several, ask the user which is the published spec.
2. Sanity-check it parses and read its `info` block (used later for the catalog
   entry):
   ```bash
   ruby -ryaml -e 'i=YAML.load_file(ARGV[0])["info"]; puts i["title"]; puts i["description"]' <SPEC_PATH>
   ```
   If it does not parse, stop and report — fix the spec first.
3. **Check the `servers` block.** SwaggerHub virtservers are no longer
   available; exposed APIs must use the standard server URL pattern, with the
   version matching the API version (`info.version`):
   ```yaml
   servers:
     - description: <API title>
       url: https://<api_repo_name>.net/{version}
       variables:
         version:
           default: <info.version>
           description: API version; matches the spec info.version
   ```
   If the spec still points at `virtserver.swaggerhub.com` (or any other
   pattern), fix it as part of this onboarding — include it in the Phase 4 PR
   or open a separate `chore:` PR.

   The in-repo version is only a placeholder — do not hand-bump it. The real
   version is the GitHub release tag (without the `v` prefix), stamped in two
   places:
   - **Release artefacts**: `hmcts/update-openapi-version` (in
     `ci-released.yml`) re-stamps `info.version` and `servers[0]` with this
     same pattern.
   - **Docs site**: the shared `publish-swagger-ui.yml` workflow stamps the
     spec before deploying (release tag on release runs; latest `v*` tag via
     `git describe` on manual dispatch), so the published Swagger UI always
     shows the released version. Repos with no `v*` tag yet publish the
     committed placeholder until their first release.
4. Record the path relative to the repo root as `OPENAPI_PATH`.

## Phase 2 — Eligibility check (REQUIRED — do not skip)

GitHub Pages on a **public** repo is **world-readable**. Only external APIs may
be published this way:

- **2c — external, documentation-only:** ✅ eligible
- **2b — external, mock execution:** ✅ eligible (docs-only here; Try-It is off)
- **2a — internal (developers only):** ❌ **NOT eligible** — it must not be
  exposed publicly. These stay on API Hub until the Developer Portal lands.

Do this:
1. Check repo visibility:
   ```bash
   gh repo view --json visibility,nameWithOwner -q '.visibility + "  " + .nameWithOwner'
   ```
2. **Ask the user to confirm the API is external (bucket 2b or 2c) and safe to
   expose to the public internet.** State plainly that this publishes the spec
   to a world-readable URL.
3. If the API is internal-only (2a), or the user is unsure, or the repo is
   `private`/`internal` and they cannot confirm it should be public: **STOP.**
   Do not add the workflow. Explain that internal APIs are out of scope for this
   stop-gap and should wait for the APIM Developer Portal.

Only continue past here once the user has explicitly confirmed public exposure
is intended.

## Phase 3 — Add the caller workflow

Create `.github/workflows/publish-api-docs.yml` with `openapi_path` set to the
`OPENAPI_PATH` from Phase 1. Pin to the released tag `@v1`:

```yaml
name: Publish API docs

# Publishes this API's Swagger UI to https://hmcts.github.io/<repo>/ on release.
# All the work lives in the shared catalog workflow; this repo only declares
# where its OpenAPI spec is. See https://github.com/hmcts/amp-catalog.
on:
  release:
    types: [ published ]
  workflow_dispatch:

permissions:
  contents: read
  pages: write
  id-token: write

jobs:
  docs:
    uses: hmcts/amp-catalog/.github/workflows/publish-swagger-ui.yml@v1
    with:
      openapi_path: <OPENAPI_PATH>
```

Do **not** add `docs/index.html`, a per-repo `publish-swagger-ui.yml`, or any
edit to `ci-released.yml` — the shared workflow handles all of that (enabling
Pages, generating the viewer, deploying).

## Phase 4 — Open a PR

Branch, commit just this file, push, and open a PR. Never commit on the default
branch directly.

```bash
git checkout -b chore/publish-api-docs
git add .github/workflows/publish-api-docs.yml
git commit -m "chore: publish API docs to GitHub Pages via amp-catalog"
git push -u origin chore/publish-api-docs
gh pr create --fill
```

Tell the user the PR URL and that merging it, then cutting a release, publishes
the docs.

> **This is the first of up to two PRs.** This API-repo PR must be approved,
> merged, and published (release/dispatch) **first** — before any catalog
> listing — so the docs site is live. If the user wants immediate listing, the
> optional section below opens a second PR in `amp-catalog`; both PRs need
> approval and merge, API-repo PR first.

## Phase 5 — Publish and verify

After the PR is merged (ask the user to merge, or merge if they direct you):

1. **Enable GitHub Pages (once, requires repo admin).** In the hmcts org the
   workflow's `GITHUB_TOKEN` cannot *create* the Pages site — without this the
   run fails at "Configure GitHub Pages" with `Resource not accessible by
   integration`. Enable it with your own credentials first:
   ```bash
   repo=$(gh repo view --json name -q .name)
   gh api "repos/hmcts/$repo/pages" >/dev/null 2>&1 \
     || gh api -X POST "repos/hmcts/$repo/pages" -f build_type=workflow
   ```
2. Trigger a publish without waiting for a real release:
   ```bash
   gh workflow run publish-api-docs.yml
   ```
3. Watch it to completion:
   ```bash
   gh run list --workflow publish-api-docs.yml --limit 1
   gh run watch <RUN_ID>
   ```
4. **Allow release (tag) deploys (once, requires repo admin).** The
   auto-created `github-pages` environment permits deployments only from `main`
   by default. A `release`-triggered run uses the **tag** ref, so it is
   rejected at the environment gate — the deploy job fails instantly with no
   logs and the site stays 404. Add a tag policy once (after the first run has
   created the environment):
   ```bash
   repo=$(gh repo view --json name -q .name)
   gh api -X POST "repos/hmcts/$repo/environments/github-pages/deployment-branch-policies" \
     -f name='v*' -f type='tag'
   ```
5. Confirm the live site (expect HTTP 200), and that the published version
   matches the repo's latest release (the shared workflow stamps it; if the
   repo has no releases yet the committed placeholder is expected):
   ```bash
   repo=$(gh repo view --json name -q .name)
   curl -sS -o /dev/null -w "%{http_code}\n" "https://hmcts.github.io/$repo/"
   curl -sS -o /dev/null -w "%{http_code}\n" "https://hmcts.github.io/$repo/openapi-spec.yml"
   curl -sS "https://hmcts.github.io/$repo/openapi-spec.yml" | yq '.info.version'
   gh api "repos/hmcts/$repo/releases/latest" -q .tag_name   # should be v<that version>
   ```
6. **Catalog listing** is automatic — the daily `discover-apis.yml` job in
   amp-catalog picks the repo up and opens a PR adding it to `docs/apis.json`.
   Tell the user it will appear within ~24h.

## Optional — list immediately / override metadata

If the user wants it in the catalog now, or the auto-derived title / description
/ team will be wrong, add the entry by hand in **amp-catalog** instead of
waiting for discovery:

1. Find or get a clone of `hmcts/amp-catalog`. Check for an existing local
   clone first (e.g. a sibling of the current repo); otherwise clone to a temp
   dir:
   ```bash
   ls "$(dirname "$PWD")" | grep amp-catalog || gh repo clone hmcts/amp-catalog /tmp/amp-catalog
   ```
2. Sync it: `git checkout main && git pull` (verify the working tree is clean
   first — if it isn't, stop and ask the user).
3. Append an entry to the `apis` array in `docs/apis.json`, keeping the
   existing JSON style:
   ```json
   {
     "name": "<repo-name>",
     "title": "<from spec info.title>",
     "description": "<one-liner>",
     "team": "<owning team>"
   }
   ```
   - `title` / `description` come from the spec `info` block read in Phase 1
     (tidy the description into a one-liner if needed).
   - `team` cannot be derived — ask the user, offering the team values already
     present in `docs/apis.json` as options.
   - `docs` / `repo` URLs are derived from `name`; override only if
     non-standard.
4. Branch, commit, push, and open the PR (never commit on main):
   ```bash
   git checkout -b chore/add-<repo-name-short>
   git add docs/apis.json
   git commit -m "chore: add <repo-name> to catalog"
   git push -u origin chore/add-<repo-name-short>
   gh pr create --title "chore: add <repo-name> to catalog" \
     --body "Manually lists <title> ahead of the next discover-apis.yml run. Caller workflow PR: hmcts/<repo-name>#<NN>."
   ```
5. Verify checks pass before handing the PR URL to the user:
   ```bash
   gh pr checks <PR_NUMBER>
   ```
   Expect `validate` (and `scan`) to pass. The later `discover-apis.yml` run
   will see the entry already present and not duplicate it.

This is the **second** PR. Merge order matters: the API-repo PR (Phase 4) must
be approved, merged, and published first so the docs site is live; only then
merge this catalog PR, so its link resolves. Both need approval and merge.

## Guardrails

- The Phase 2 eligibility check is mandatory. When in doubt, do not publish.
- Two PRs result when listing immediately (API-repo workflow + catalog entry).
  Both need approval and merge, **API-repo PR first** — the docs site must be
  live before the catalog links to it.
- Always pin the caller to `@v1`, never `@main`.
- This is a temporary bridge; when the APIM Developer Portal lands these sites
  are retired. Do not build anything on top of the Pages URLs.