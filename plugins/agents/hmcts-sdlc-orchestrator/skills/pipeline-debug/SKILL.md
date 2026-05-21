---
name: pipeline-debug
description: Debug and understand Azure DevOps pipeline configurations. Use when a pipeline fails, when setting up CI/CD for a new repo, or when tracing variable resolution across templates.
---

# Pipeline Debug

Helps debug, understand, and configure Azure DevOps pipelines across CP repositories by tracing template references, variable resolution, and pipeline structure.

## When to Use

- User asks "why did my pipeline fail", "debug this pipeline", "trace this variable"
- User wants to set up CI/CD for a new repo
- User needs to understand how shared templates work
- User wants to find which template defines a specific step or variable

## Process

### Step 1: Identify the Pipeline

Read the repo's `azure-pipelines.yml` (or `azure-pipelines.yaml`). This is the entry point.

### Step 2: Trace Template References

CP pipelines use shared templates from `cpp-azure-devops-templates`. Template references look like:

```yaml
resources:
  repositories:
    - repository: cppAzureDevOpsTemplates
      type: github
      name: hmcts/cpp-azure-devops-templates
      ref: refs/heads/main

stages:
  - template: pipelines/context-verify.yaml@cppAzureDevOpsTemplates
```

For each template reference:
1. Read the template file from `cpp-azure-devops-templates/`
2. Map the parameters passed from the calling pipeline to the template's parameter definitions
3. Recursively follow any nested template references (stages → steps → tasks)

### Step 3: Trace Variable Resolution

Variables are resolved in this order (later overrides earlier):

1. **Pipeline-level variables** — defined in `azure-pipelines.yml`
2. **Variable groups** — referenced by name, stored in Azure DevOps
3. **Template parameters** — passed explicitly to templates
4. **Runtime expressions** — `${{ variables.xxx }}`, `$[ variables.xxx ]`
5. **Macro syntax** — `$(variableName)` resolved at runtime

### Step 4: Identify Common Pipeline Types

| Repo Type | PR Template | Merge Template | Key Steps |
|-----------|-------------|----------------|-----------|
| Context services | `context-verify.yaml` | `context-validation.yaml` | Maven build, SonarQube, JaCoCo |
| UI apps | `ui-verify.yaml` | `ui-validation.yaml` | npm install, lint, test, build |
| Terraform modules | `terratest.yaml` | — | terraform init, validate, plan, test |
| Docker images | `image-publish.yaml` | — | Docker build, ACR push |
| Helm charts | Custom in `cpp-helm-chart` | — | Helm lint, package, ACR push |
| UI E2E tests (`cpp-ui-e2e-serenity`) | `azure-pipelines.yml` (PR) | `azure-pipelines-dev01_regression.yml`, `*_BPO_regression.yml`, `*_migration.yml`, `*_migration_EDT.yml`, `*_migration-nows.yml`, `*_migration-ts.yml`, `azure-pipeline-cdci-dlrm.yml` | Maven `verify`, Serenity profiles, WebDriver browser provisioning, Serenity HTML reports |
| API integration tests (`cpp-apitests`) | `azure-pipelines.yaml` (PR) | `apitests-pipeline.yaml` | Maven `verify` (Failsafe runs `*IT.java`), REST Assured + JUnit 5 |

For test-authoring guidance in either of the two test repos above, see `cpp-test-authoring`.

### Step 5: Common Failure Patterns

| Symptom | Likely Cause | Where to Look |
|---------|-------------|---------------|
| `settings.xml not found` | Secure file download failed | Check `DownloadSecureFile` task and file name |
| `SonarQube analysis failed` | Wrong project key or missing token | Check `sonarQubeProjectKey` parameter |
| `mvn: command not found` | Wrong agent pool or missing tool | Check `pool` and `task: Maven@4` config |
| `npm ERR! 403` | .npmrc not configured for private registry | Check secure file `.npmrc` download |
| `docker push failed` | ACR login failed or wrong registry | Check `containerRegistry` service connection |
| `terraform plan failed` | Backend config mismatch or missing vars | Check `backend-config` parameters |
| `Helm lint failed` | Chart.yaml version mismatch or missing deps | Check `helm dependency update` step |
| Serenity report empty / no scenarios ran | Wrong tag filter or `glue` package missing | Check `TestRunner.java` `@CucumberOptions` + the profile's `-Dcucumber.filter.tags` |
| `cpp-apitests` build green but no tests executed | Class named `*Test.java` instead of `*IT.java` | Failsafe only picks up `*IT.java`; rename |
| WebDriver session creation failed | Browser/driver mismatch in agent pool | Check WebDriverManager config + agent pool image |

### Step 6: Generate Debugging Report

```
## Pipeline Analysis: [repo-name]

### Pipeline Type
[context-verify / ui-verify / custom]

### Template Chain
1. azure-pipelines.yml
   └─ pipelines/context-verify.yaml@cppAzureDevOpsTemplates
      ├─ stages/build.yaml
      │   └─ steps/maven-build.yaml
      └─ stages/quality.yaml
          └─ steps/sonarqube-scan.yaml

### Variables Resolved
| Variable | Value | Source |
|----------|-------|--------|
| sonarQubeProjectKey | uk.gov.moj.cpp... | pipeline parameter |
| mavenGoals | clean verify | template default |

### Issues Found
- [description of any problems]

### Recommended Fix
- [specific fix with file and line references]
```

## Key Files in cpp-azure-devops-templates

```
cpp-azure-devops-templates/
├── pipelines/
│   ├── context-verify.yaml         # Context service PR validation
│   ├── context-validation.yaml     # Context service merge build
│   ├── ui-verify.yaml              # UI app PR validation
│   ├── ui-validation.yaml          # UI app merge build
│   ├── terratest.yaml              # Terraform module testing
│   └── image-publish.yaml          # Docker image publishing
├── stages/                         # Reusable stage definitions
├── steps/                          # Reusable step definitions
└── variables/                      # Shared variable files
```

## Deployment Pipelines

For deployment-related issues, also check:
- `cpp-aks-deploy/aks-deploy.yaml` — main AKS deployment pipeline
- `cpp-aks-deploy/helmsman.toml` — Helmsman deployment configuration
- `cpp-aks-deploy/helmsman_vars/*.env` — environment-specific variables
- Approval gates: non-live auto-resumes on timeout; live requires CP DevOps SC approval
