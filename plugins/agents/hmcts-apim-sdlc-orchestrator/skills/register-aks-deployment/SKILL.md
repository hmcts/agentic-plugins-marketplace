---
name: register-aks-deployment
description: >
  Wire up automatic first-time GitOps registration for a service-cp-* repo in
  hmcts/cp-vp-aks-deploy. One-time, Claude-invoked install — patches
  ci-build-publish.yml with a deterministic `register-aks-deploy` job that then
  runs unattended on every push to main. Idempotent both at install time (safe
  to re-run) and at runtime (no-ops once the service is registered). Use when a
  service-cp-* repo has never been deployed before and has no entry in
  cp-vp-aks-deploy's vp-config/apps_to_deploy, or when setting up a newly
  bootstrapped service ahead of its first merge to main.
---

# Skill: Register AKS Deployment

## Problem this solves

`wire-service-deployment` wires the `deploy-dev`/`deploy-sit` jobs, but it hard-stops
if the service has no entry in `hmcts/cp-vp-aks-deploy` yet — today a human has to
notice that, hand-edit `vp-config/apps_to_deploy` and `vp-config/services_values.yml`,
and raise the PR themselves. This skill removes that manual step by installing a CI
job that does it automatically the first time the service's `main` branch builds.

This is step **zero** in the GitOps bootstrap sequence:

```
register-aks-deployment (this skill, one-time)
  → registration PR to cp-vp-aks-deploy auto-opened on first push to main
  → human reviews + merges
  → wire-service-deployment (Step 4 check now passes)
  → deploy-dev / deploy-sit jobs wired
  → deployer agent monitors ongoing deploys
```

Invocation command: `/register-aks-deployment`

---

## Step 1 — Identify the service repo

```bash
REPO_NAME=$(gh repo view --json name -q '.name')
echo "Service repo: $REPO_NAME"
```

---

## Step 2 — Idempotency check

```bash
grep -q "register-aks-deploy:" .github/workflows/ci-build-publish.yml \
  && echo "ALREADY_WIRED" || echo "NEEDS_WIRING"
```

If `ALREADY_WIRED`, tell the user: *"The register-aks-deploy job is already present
in `ci-build-publish.yml`. Nothing to do."* and exit the skill.

---

## Step 3 — Verify GitHub App secrets

This job reuses the same GitHub App already required by `wire-service-deployment`
(`hmcts/action-ado-deploy@v1` uses it to push to `cp-vp-aks-deploy`) — no new secrets
are introduced.

```bash
gh secret list --env dev 2>/dev/null | grep -E "DEPLOYMENT_APP_ID|DEPLOYMENT_APP_PRIVATE_KEY"
```

If either is missing, stop and tell the user:

> "Prerequisites not met. The `dev` environment on this repo is missing one or both
> deployment secrets (`DEPLOYMENT_APP_ID`, `DEPLOYMENT_APP_PRIVATE_KEY`). Ask a
> platform engineer to configure these before running this skill."

This is the *only* prerequisite — unlike `wire-service-deployment`, this skill does
**not** require the service to already be registered in `cp-vp-aks-deploy`. Registering
it is exactly what the installed job will do.

---

## Step 4 — Create a branch

```bash
git checkout main && git pull origin main
git checkout -b chore/register-aks-deployment
```

---

## Step 5 — Add the `register-aks-deploy` job to `ci-build-publish.yml`

Append after the `Build` job (runs alongside/after it, independent of `trigger_docker`/
`trigger_deploy` — registration should happen even on a repo's very first draft build):

```yaml
  register-aks-deploy:
    needs: [Build]
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    steps:
      - name: Generate GitHub App token for cp-vp-aks-deploy
        id: app-token
        uses: actions/create-github-app-token@v2
        with:
          app-id: ${{ secrets.DEPLOYMENT_APP_ID }}
          private-key: ${{ secrets.DEPLOYMENT_APP_PRIVATE_KEY }}
          owner: hmcts
          repositories: cp-vp-aks-deploy

      - name: Checkout cp-vp-aks-deploy env/dev
        uses: actions/checkout@v7
        with:
          repository: hmcts/cp-vp-aks-deploy
          ref: env/dev
          token: ${{ steps.app-token.outputs.token }}
          path: cp-vp-aks-deploy

      - name: Check if already registered
        id: check
        working-directory: cp-vp-aks-deploy
        run: |
          REPO_NAME=${GITHUB_REPOSITORY##*/}
          if grep -q "$REPO_NAME" vp-config/apps_to_deploy vp-config/services_values.yml; then
            echo "registered=true" >> "$GITHUB_OUTPUT"
          else
            echo "registered=false" >> "$GITHUB_OUTPUT"
          fi

      - name: Check for an existing registration PR
        id: existing_pr
        if: steps.check.outputs.registered == 'false'
        env:
          GH_TOKEN: ${{ steps.app-token.outputs.token }}
        run: |
          REPO_NAME=${GITHUB_REPOSITORY##*/}
          COUNT=$(gh pr list --repo hmcts/cp-vp-aks-deploy \
            --head "chore/register-${REPO_NAME}-aks-deploy" --json number --jq 'length')
          echo "count=$COUNT" >> "$GITHUB_OUTPUT"

      - name: Generate manifest entry and open registration PR
        if: steps.check.outputs.registered == 'false' && steps.existing_pr.outputs.count == '0'
        working-directory: cp-vp-aks-deploy
        env:
          GH_TOKEN: ${{ steps.app-token.outputs.token }}
        run: |
          set -euo pipefail
          REPO_NAME=${GITHUB_REPOSITORY##*/}
          SERVICE_NAME=${REPO_NAME#service-cp-}
          BRANCH="chore/register-${REPO_NAME}-aks-deploy"

          git checkout -b "$BRANCH"
          echo "$REPO_NAME" >> vp-config/apps_to_deploy

          cat >> vp-config/services_values.yml <<EOF
            ${REPO_NAME}:
              fullnameOverride: ${SERVICE_NAME}
              image:
                repository: "\${acrUrl}/hmcts/${REPO_NAME}-service"
                tag: "0.0.0-pending"
              livenessProbe:
                httpGet:
                  path: /
                  port: http
              readinessProbe:
                httpGet:
                  path: /
                  port: http
                  scheme: HTTP
              route:
                path:
                  - /${SERVICE_NAME}
          EOF

          git config user.name "hmcts-deployment-bot"
          git config user.email "deployment-bot@hmcts.net"
          git add vp-config/apps_to_deploy vp-config/services_values.yml
          git commit -m "chore: register ${REPO_NAME} for AKS dev deployment"
          git push -u origin "$BRANCH"

          gh pr create --repo hmcts/cp-vp-aks-deploy \
            --base env/dev \
            --head "$BRANCH" \
            --title "chore: register ${REPO_NAME} for AKS dev deployment" \
            --body "Auto-generated by ${REPO_NAME}'s first merge to main.

          **Human review required before merge:**
          - [ ] \`route.path\` — placeholder is \`/${SERVICE_NAME}\`, verify against the
                service's actual OpenAPI base path
          - [ ] \`image.repository\` — verify the GHCR/ACR image name matches what
                CI actually pushes
          - [ ] \`image.tag\` — placeholder \`0.0.0-pending\`; the next deploy-dev run
                (after wire-service-deployment is applied) will overwrite it with a
                real artefact version
          - [ ] certs/volumes — this service may need a certs configMap block like
                other services in \`services_values.yml\`; none was added here since
                the script cannot infer that automatically"
```

Substitute `actions/checkout@vN` to match whatever version the rest of the repo's
workflows already use (some repos are on `v6`, some `v7` — match the existing file).

---

## Step 6 — Update `wire-service-deployment`'s Step 4 message

`wire-service-deployment` Step 4 currently tells the user to raise the `cp-vp-aks-deploy`
PR by hand. Update its guidance to point here instead:

> "`$REPO_NAME` has no entry in `hmcts/cp-vp-aks-deploy/vp-config/services_values.yml`
> yet. Run `/register-aks-deployment` first — its installed CI job will open the
> registration PR automatically on the next push to main. Once that PR is merged,
> re-run `/wire-service-deployment`."

---

## Step 7 — Commit and raise PR

```bash
git add .github/workflows/ci-build-publish.yml

git commit -m "chore(ci): add register-aks-deploy job

Automatically registers this service in hmcts/cp-vp-aks-deploy (vp-config/
apps_to_deploy + services_values.yml) the first time main builds, by opening
a PR against env/dev. No-ops once the service is already registered. Reuses
the existing DEPLOYMENT_APP_ID/DEPLOYMENT_APP_PRIVATE_KEY GitHub App — no new
secrets required.

One-time install — the job it adds then runs unattended on every push to main."

git push -u origin chore/register-aks-deployment

gh pr create \
  --title "chore(ci): add register-aks-deploy job" \
  --body "$(cat <<'EOF'
## Summary

Adds a deterministic `register-aks-deploy` job to `ci-build-publish.yml` that
runs on every push to main. If this service has no entry in
`hmcts/cp-vp-aks-deploy` yet, it opens a PR adding one (idempotent — no-ops
on every subsequent run once registered, and skips re-opening a PR that's
already open).

This closes the gap where a brand-new service-cp-* repo's first-ever
deployment registration was a manual, easy-to-forget step.

## Verification needed before merge

- [ ] Confirm `DEPLOYMENT_APP_ID` / `DEPLOYMENT_APP_PRIVATE_KEY` secrets exist
      in the `dev` environment (same ones `wire-service-deployment` needs)
- [ ] After merge, watch the next push to main open the registration PR
      against `hmcts/cp-vp-aks-deploy` `env/dev`, and review the generated
      route/image values before merging that PR
EOF
)"
```

---

## Rules

- **Never run this skill on `main` directly.** Always create and push from a new branch.
- **Never apply if `register-aks-deploy` already exists** in `ci-build-publish.yml` —
  check in Step 2.
- **The installed job never auto-merges the registration PR.** `cp-vp-aks-deploy` is
  the GitOps source of truth for every service on the platform — a human always
  reviews route path, image repository, and probe/cert config before merge.
- **The installed job is safe to leave running forever.** Once a service is
  registered, `grep -q "$REPO_NAME"` short-circuits it to a no-op on every future
  push to main.
- **Never hardcode secrets.** All auth goes through the existing GitHub App via
  `actions/create-github-app-token@v2` — no literal tokens.
- If `gh api`/`gh pr list` cannot reach `cp-vp-aks-deploy` (permissions issue) at
  install time, that's a Step 3 prerequisite failure, not a reason to skip Step 5 —
  the installed job will surface its own auth failures clearly in the Actions log.