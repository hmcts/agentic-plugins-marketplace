---
name: wire-service-deployment
description: >
  Wire up auto-dev and auto-SIT deployment CI for a service-cp-* repo after Azure
  provisioning and cp-vp-aks-deploy registration are complete. Idempotent — safe to
  invoke again if the jobs already exist. Use when a service-cp-* repo is missing the
  deploy-dev and deploy-sit jobs in its ci-build-publish.yml, or when setting up a
  newly bootstrapped service for the first time.
---

# Skill: Wire Service Deployment

## When to invoke

Invoke **once per service repo**, after both of these external prerequisites are complete:

1. **Azure provisioning done** — the `dev` GitHub environment exists on the repo and has
   `DEPLOYMENT_APP_ID` and `DEPLOYMENT_APP_PRIVATE_KEY` secrets configured.
2. **Service registered in `cp-vp-aks-deploy`** — an entry for this service exists in
   `hmcts/cp-vp-aks-deploy` under `vp-config/services_values.yml`.

If either prerequisite is missing, **stop here** and tell the user what is outstanding.
Do not proceed until both are in place.

Invocation command: `/wire-service-deployment`

---

## Step 1 — Identify the service repo

Confirm you are in the root of a `service-cp-*` repo (or that the user has named one).
Derive the service name:

```bash
REPO_NAME=$(gh repo view --json name -q '.name')
echo "Service repo: $REPO_NAME"
```

---

## Step 2 — Idempotency check

Check whether the deployment jobs are already wired:

```bash
grep -q "deploy-dev:" .github/workflows/ci-build-publish.yml && echo "ALREADY_WIRED" || echo "NEEDS_WIRING"
```

If `ALREADY_WIRED`, tell the user: *"Deployment jobs are already present in
`ci-build-publish.yml`. Nothing to do."* and exit the skill.

---

## Step 3 — Verify GitHub environment secrets

Check that the `DEPLOYMENT_APP_ID` and `DEPLOYMENT_APP_PRIVATE_KEY` secrets exist in the
`dev` environment. These are required by `hmcts/action-ado-deploy@v1`.

```bash
gh secret list --env dev 2>/dev/null | grep -E "DEPLOYMENT_APP_ID|DEPLOYMENT_APP_PRIVATE_KEY"
```

If either secret is missing, stop and tell the user:

> "Prerequisites not met. The `dev` environment on this repo is missing one or both deployment
> secrets (`DEPLOYMENT_APP_ID`, `DEPLOYMENT_APP_PRIVATE_KEY`). Ask a platform engineer to
> configure these before running this skill."

---

## Step 4 — Verify service registration in cp-vp-aks-deploy

Check that the service has an entry in the GitOps values file:

```bash
gh api "repos/hmcts/cp-vp-aks-deploy/contents/vp-config/services_values.yml" \
  --jq '.content' | base64 -d | grep -q "$REPO_NAME" \
  && echo "REGISTERED" || echo "NOT_REGISTERED"
```

If `NOT_REGISTERED`, stop and tell the user:

> "Prerequisites not met. `$REPO_NAME` has no entry in
> `hmcts/cp-vp-aks-deploy/vp-config/services_values.yml`. The service must be registered
> in the GitOps config before deployment can be wired. Raise a PR on `cp-vp-aks-deploy`
> to add the entry, then re-run this skill."

---

## Step 5 — Discover cluster parameters

Read the cluster assignment from `services_values.yml`. The parameters needed are
`cpbackendenv`, `stack`, and `cluster` for both the `dev` and `sit` environments.
These are passed to ADO pipeline 434 as `template_parameters` in the deploy jobs.

```bash
gh api "repos/hmcts/cp-vp-aks-deploy/contents/vp-config/services_values.yml" \
  --jq '.content' | base64 -d > /tmp/services_values.yml
```

Scan the file for the service's section. If the file uses a flat key-value format with
environment stanzas, extract the relevant values. If you cannot parse them unambiguously,
ask the user:

> "I found your service in `services_values.yml` but couldn't extract the cluster params
> automatically. Please provide:
> - **dev** `cpbackendenv` (e.g. `steccm14`):
> - **dev** `stack` (e.g. `steamp01`):
> - **dev** `cluster` (e.g. `K8-STE-CS01-CL01`):
> - **sit** `cpbackendenv` (e.g. `sitccm01`):
> - **sit** `stack` (e.g. `sitamp01`):
> - **sit** `cluster` (e.g. `K8-SIT-CS01-CL02`):

The most common values across `service-cp-*` repos are shown as defaults — use them if
the user cannot locate their service's specific values, but flag them for verification."

Known defaults (for reference — always verify against the actual GitOps config):

| Environment | `cpbackendenv` | `stack` | `cluster` |
|---|---|---|---|
| dev | `steccm14` | `steamp01` | `K8-STE-CS01-CL01` |
| sit | `sitccm01` | `sitamp01` | `K8-SIT-CS01-CL02` |

---

## Step 6 — Create a branch

```bash
git checkout main && git pull origin main
git checkout -b chore/wire-service-deployment
```

---

## Step 7 — Patch `ci-build-publish.yml`

The goal is to replace the current simplified workflow with the full deployment-capable
version. The canonical diff adds:

**To the `workflow_call` secrets block:**
```yaml
      DEPLOYMENT_APP_ID:
        required: true
        description: "GitHub App ID for deployment"
      DEPLOYMENT_APP_PRIVATE_KEY:
        required: true
        description: "GitHub App private key for deployment"
```

**To the `workflow_call` inputs block:**
```yaml
      environment:
        required: true
        type: string
        default: dev
      deploy_dev:
        required: false
        type: boolean
        default: true
      deploy_sit:
        required: false
        type: boolean
        default: false
      deploy_environment:
        required: false
        type: string
        default: dev
```

**Add `environment` context to `Artefact-Version` and `Build` jobs:**
```yaml
    environment:
      name: ${{ inputs.environment }}
```

**Add `setup-gradle` step to `Build` job if missing** (insert before Gradle Build):
```yaml
      - name: Set up Gradle
        uses: gradle/actions/setup-gradle@v6
        with:
          gradle-version: current
```

**Add `id: trigger` and `outputs` to `Deploy` job:**
```yaml
    outputs:
      run_id: ${{ steps.trigger.outputs.run_id }}
```
And add `id: trigger` to the "Trigger ADO pipeline" step.

**Append after the `Deploy` job:**

```yaml
  Wait-For-ACR-Push:
    needs: [Deploy]
    if: ${{ inputs.trigger_deploy }}
    runs-on: ubuntu-latest
    steps:
      - name: Wait for ADO pipeline 460
        uses: hmcts/monitor-ado-pipeline@v1
        with:
          pipeline_id: 460
          run_id: ${{ needs.Deploy.outputs.run_id }}
          ado_pat: ${{ secrets.HMCTS_ADO_PAT }}
          poll_interval: 30
          timeout: 1800

  deploy-dev:
    needs: [Wait-For-ACR-Push, Artefact-Version, Build]
    if: ${{ inputs.trigger_deploy && inputs.deploy_dev }}
    runs-on: ubuntu-latest
    steps:
      - name: Generate date suffix
        id: date
        shell: bash
        run: echo "suffix=_$(date -u +'%d%m%y')" >> "$GITHUB_OUTPUT"

      - name: Deploy to dev via ADO pipeline
        uses: hmcts/action-ado-deploy@v1
        with:
          service_name: ${{ needs.Build.outputs.repo_name }}
          image_tag: ${{ needs.Artefact-Version.outputs.artefact_version }}
          tag_suffix: ${{ steps.date.outputs.suffix }}
          app_id: ${{ secrets.DEPLOYMENT_APP_ID }}
          app_private_key: ${{ secrets.DEPLOYMENT_APP_PRIVATE_KEY }}
          target_repository: hmcts/cp-vp-aks-deploy
          target_branch: env/dev
          values_file: vp-config/services_values.yml
          pipeline_id: 434
          ado_pat: ${{ secrets.HMCTS_ADO_PAT }}
          ref_name: refs/heads/env/dev
          wait: false
          template_parameters: >
            {
              "env": "dev",
              "cpbackendenv": "<DEV_CPBACKENDENV>",
              "stack": "<DEV_STACK>",
              "cluster": "<DEV_CLUSTER>"
            }

  deploy-sit:
    needs: [Wait-For-ACR-Push, Artefact-Version, Build]
    if: ${{ inputs.trigger_deploy && inputs.deploy_sit }}
    runs-on: ubuntu-latest
    steps:
      - name: Generate date suffix
        id: date
        shell: bash
        run: echo "suffix=_$(date -u +'%d%m%y')" >> "$GITHUB_OUTPUT"

      - name: Deploy to SIT via ADO pipeline
        uses: hmcts/action-ado-deploy@v1
        with:
          service_name: ${{ needs.Build.outputs.repo_name }}
          image_tag: ${{ needs.Artefact-Version.outputs.artefact_version }}
          tag_suffix: ${{ steps.date.outputs.suffix }}
          app_id: ${{ secrets.DEPLOYMENT_APP_ID }}
          app_private_key: ${{ secrets.DEPLOYMENT_APP_PRIVATE_KEY }}
          target_repository: hmcts/cp-vp-aks-deploy
          target_branch: env/sit
          values_file: vp-config/services_values.yml
          pipeline_id: 434
          ado_pat: ${{ secrets.HMCTS_ADO_PAT }}
          ref_name: refs/heads/env/sit
          wait: false
          template_parameters: >
            {
              "env": "sit",
              "cpbackendenv": "<SIT_CPBACKENDENV>",
              "stack": "<SIT_STACK>",
              "cluster": "<SIT_CLUSTER>"
            }
```

Substitute `<DEV_*>` and `<SIT_*>` placeholders with the values discovered in Step 5.

---

## Step 8 — Patch `ci-draft.yml`

Add the two deployment secrets and environment inputs to the `ci-draft` job's `secrets:`
and `with:` blocks:

```yaml
    secrets:
      # ... existing secrets ...
      DEPLOYMENT_APP_ID: ${{ secrets.DEPLOYMENT_APP_ID }}
      DEPLOYMENT_APP_PRIVATE_KEY: ${{ secrets.DEPLOYMENT_APP_PRIVATE_KEY }}
    with:
      environment: dev
      # ... existing inputs ...
      deploy_environment: dev
```

Push to main on a merge triggers `deploy_dev` (defaults to `true`), so no explicit
`deploy_dev: true` is needed here.

---

## Step 9 — Patch `ci-released.yml`

Add deployment secrets and set `deploy_dev: false` / `deploy_sit: true` so a GitHub
Release triggers auto-SIT:

```yaml
    secrets:
      # ... existing secrets ...
      DEPLOYMENT_APP_ID: ${{ secrets.DEPLOYMENT_APP_ID }}
      DEPLOYMENT_APP_PRIVATE_KEY: ${{ secrets.DEPLOYMENT_APP_PRIVATE_KEY }}
    with:
      environment: dev
      # ... existing inputs (is_release, is_publish, trigger_docker, trigger_deploy) ...
      deploy_dev: false
      deploy_sit: true
      deploy_environment: dev
```

---

## Step 10 — Commit and raise PR

```bash
git add .github/workflows/ci-build-publish.yml \
         .github/workflows/ci-draft.yml \
         .github/workflows/ci-released.yml

git commit -m "chore(ci): wire auto-dev and auto-SIT deployment

Adds DEPLOYMENT_APP_ID/DEPLOYMENT_APP_PRIVATE_KEY secrets, deploy-dev and
deploy-sit GitOps jobs, and Wait-For-ACR-Push monitoring to ci-build-publish.yml.
Configures ci-draft (push→dev) and ci-released (release→SIT) callers.

One-time setup — runs after Azure provisioning and cp-vp-aks-deploy registration."

git push -u origin chore/wire-service-deployment

gh pr create \
  --title "chore(ci): wire auto-dev and auto-SIT deployment" \
  --body "$(cat <<'EOF'
## Summary

One-time deployment wiring for this service-cp-* repo, following the
standard pattern used across all HMCTS APIM services.

- `ci-build-publish.yml` — adds \`deploy-dev\` and \`deploy-sit\` GitOps
  jobs (ADO pipeline 434 via \`hmcts/action-ado-deploy@v1\`), plus
  \`Wait-For-ACR-Push\` monitoring and deployment secrets/inputs
- `ci-draft.yml` — push to main now triggers auto-dev deploy
- `ci-released.yml` — GitHub Release now triggers auto-SIT deploy

## Prerequisites verified

- [x] Service registered in \`hmcts/cp-vp-aks-deploy\` (vp-config/services_values.yml)
- [x] \`DEPLOYMENT_APP_ID\` and \`DEPLOYMENT_APP_PRIVATE_KEY\` secrets exist in the \`dev\` environment

## Verification needed before merge

- [ ] Confirm \`cpbackendenv\`, \`stack\`, and \`cluster\` values in the deploy jobs
      match the cluster assigned to this service in cp-vp-aks-deploy
EOF
)"
```

---

## Rules

- **Never run this skill on `main` directly.** Always create and push from a new branch.
- **Never apply if `deploy-dev` already exists** in `ci-build-publish.yml` — check in Step 2.
- **Never hardcode secrets.** All secrets pass through `${{ secrets.* }}` — no literal values.
- **This skill is a one-time setup.** After the PR merges, it does not need to be re-run
  unless the service's cluster assignment changes (in which case, raise a targeted PR that
  updates only the `template_parameters` blocks in the deploy jobs).
- If `gh api` cannot read `cp-vp-aks-deploy` (permissions issue), ask the user to provide
  cluster params manually rather than blocking the entire workflow.