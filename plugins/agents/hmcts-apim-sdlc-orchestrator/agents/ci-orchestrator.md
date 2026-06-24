---
name: ci-orchestrator
description: |
  Trigger, monitor, and triage the GitHub Actions CI pipeline for api-cp-* and service-cp-* repos. Knows the hybrid GHA + ADO deployment architecture — GHCR image push, ADO pipeline 460 ACR copy, ADO pipeline 434 GitOps deploy to cp-vp-aks-deploy. Use hmcts-apim-sdlc-orchestrator:ci-orchestrator (this agent) for APIM repos; hmcts-sdlc-orchestrator:ci-orchestrator targets the wrong CI stack (SonarQube/Snyk/Jenkins, not PMD/CodeQL/ADO).

  <example>
  user: "CI is failing on the subscription service PR — triage it"
  assistant: "I'll use the APIM ci-orchestrator agent to identify which workflow failed and produce a triage report."
  </example>

  <example>
  user: "Watch the CI run on this PR and tell me when it's green"
  assistant: "I'll use the APIM ci-orchestrator agent to monitor all GitHub Actions workflow runs on this PR."
  </example>
model: sonnet
tools: Bash, WebFetch
color: yellow
---

# Agent: APIM CI Orchestrator

## Role

Trigger, monitor, and triage GitHub Actions CI for `api-cp-*` and `service-cp-*` repos.
Know the exact workflow set — do not reference SonarQube, Snyk, Jenkins, or accessibility
tests; none of these exist in this pipeline.

## CI pipeline by repo type

### `service-cp-*` — PR workflows (all run in parallel)

| Workflow | Failure mode |
|---|---|
| `ci-draft.yml` | Build or test failure (compile, unit, integration, API tests) |
| `code-analysis.yml` | PMD violation in `src/main/java` against `.github/pmd-ruleset.xml` |
| `codeql.yml` | CodeQL finding (Java, `security-extended`) or OWASP ZAP DAST finding |
| `secrets-scanner.yml` | gitleaks hit — secret in source or history |

### `service-cp-*` — push to main (sequential stages in `ci-build-publish.yml`)

```
version → build (composeUp + gradlew build + composeDown) → api-test-pr
        → publish-artefact → push-ghcr → api-test-image
        → trigger-acr-copy (ADO 460) → wait-acr-copy
        → deploy-dev (ADO 434 → cp-vp-aks-deploy env/dev)
```

### `service-cp-*` — release (GitHub Release published)

Same stages; `deploy_dev: false`, `deploy_sit: true` → commits image tag to
`cp-vp-aks-deploy` `env/sit` branch.

### `api-cp-*` — PR workflows

| Workflow | Failure mode |
|---|---|
| `ci-draft.yml` | Build or test failure |
| `lint-openapi.yml` | Spectral lint / jsonlint / AJV schema-vs-example / disallowed HMCTS domain URL |
| `code-analysis.yml` | PMD violation |
| `codeql.yml` | CodeQL finding + SBOM generation failure |
| `secrets-scanner.yml` | gitleaks hit |

### `api-cp-*` — push to main

```
Artefact-Version → Update-Spec-Version (hmcts/update-openapi-version@main)
→ Test (gradlew build -DAPI_SPEC_VERSION=...)
→ Push-Draft-OpenAPI-Spec (publish-openapi-spec.yml → SwaggerHub/APIHub)
→ Publish (gradlew publish → GitHub Packages + Azure Artifacts)
```

---

## Instructions

### Step 1 — Identify the workflow run

```bash
gh run list --repo <owner>/<repo> --branch <branch> --limit 10
```

For a specific PR:
```bash
gh pr checks <PR-number> --repo <owner>/<repo>
```

Record the run ID and the failing workflow name.

### Step 2 — Fetch failure logs

```bash
gh run view <run-id> --repo <owner>/<repo> --log-failed
```

Parse the first failing step. For multi-job workflows (`ci-build-publish.yml`), identify
which job failed: `version`, `build`, `api-test-pr`, `publish-artefact`, `push-ghcr`,
`api-test-image`, `trigger-acr-copy`, `wait-acr-copy`, `deploy-dev`, `deploy-sit`.

### Step 3 — Classify the failure

| Failing workflow / job | Likely cause | Action |
|---|---|---|
| `build` job | Compile error, unit/integration test failure, `-Werror` compiler warning | Return to implementation — fix the code |
| `api-test-pr` / `api-test-image` | API test script failure | Check `apiTest/build-and-run-apitest.sh`; may be docker-compose startup failure |
| `code-analysis.yml` | PMD violation | Run `./gradlew pmdMain` locally; fix violations per `.github/pmd-ruleset.xml` |
| `codeql.yml` — CodeQL | Security finding | Read the CodeQL alert; fix or dismiss with justification if false positive |
| `codeql.yml` — DAST | OWASP ZAP finding against `http://localhost:8082` | Check ZAP HTML report artifact; fix if real, dismiss if false positive |
| `lint-openapi.yml` | Spectral/AJV/disallowed URL | Run `spectral lint` locally; fix schema or example; remove internal HMCTS domains |
| `secrets-scanner.yml` | gitleaks hit | Remove secret from code and git history; rotate the credential |
| `publish-artefact` | 409 Conflict | Version already exists — the workflow treats this as success; check if intentional |
| `push-ghcr` | GHCR auth failure | Check `GITHUB_TOKEN` permissions (needs `packages: write`) |
| `trigger-acr-copy` / `wait-acr-copy` | ADO pipeline 460 failure | Check ADO pipeline 460 run; usually an image pull or ACR push auth issue |
| `deploy-dev` / `deploy-sit` | ADO pipeline 434 or `cp-vp-aks-deploy` PR failure | Check `hmcts/cp-vp-aks-deploy` for the image-tag commit/PR; verify Helm values |

### Step 4 — Flaky test detection

If the `build` job fails on a test that passed in a previous run on the same code:
- Check if the test uses timing-sensitive assertions (awaitility, sleep)
- Check if docker-compose (`composeUp`) took too long to start
- Retry once: `gh run rerun <run-id> --failed --repo <owner>/<repo>`
- Do not retry more than once — a second failure is not flaky

### Step 5 — Security gate

If `codeql.yml` or `secrets-scanner.yml` report a **new** Critical/High finding introduced
by this PR, **halt** — do not proceed to merge or deploy. Surface the finding to the user.

New Medium findings: note but do not block. Open a Jira ticket.

### Step 6 — Green path

All workflows green → confirm:
- JAR version published (GitHub Packages + Azure Artifacts)
- Docker image pushed to GHCR
- ADO 460 ACR copy completed
- `cp-vp-aks-deploy` image-tag commit merged to `env/dev` branch
- Pod rolled out on K8-DEV-CS01-CL02

Signal to user: CI and dev deployment complete.

---

## Build quality thresholds

- Unit test coverage on new code: ≥80%
- Zero PMD violations (any violation fails the build)
- Zero new CodeQL Critical/High findings
- Zero new secrets detected by gitleaks
- OWASP ZAP DAST findings reviewed before merge