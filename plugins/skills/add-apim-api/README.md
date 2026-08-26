# Add APIM API Skill

Checklist and reference guide for adding a new Azure API Management (APIM) API to the HMCTS CP crime API infrastructure Terraform config.

## Usage

In any CP API repo that uses the APIM Terraform pattern, type:

```
/add-apim-api
```

Claude will walk you through the naming conventions, tfvars entry pattern, secrets scanner rules, Entra ID requirements, and GitHub variable setup for a new API.

## What it covers

- **Naming convention** — `display_name` pattern: `"Crime X and Y Z API (<shortname>)"`
- **Path convention** — always `amp/<shortname>` (e.g. `amp/slc`)
- **tfvars entry template** — copy-paste ready block for each environment
- **Secrets scanner safety** — store `service_host` without `.org.uk`; `service_path` as `/<shortname>`
- **Per-environment Entra IDs** — each environment needs its own tenant/client ID, never copied across environments
- **GitHub Actions variables** — the 3 vars required per new environment
- **`azure-github-federation-config`** — where to raise a PR for OIDC federation

## Repos that use this pattern

| Term | API repo |
|---|---|
| slc | api-cp-crime-schedulingandlisting-courtschedule |
| hrds | api-cp-crime-hearing-results-document-subscription |
| pcr | api-cp-crime-results-pcr |
| dl | api-cp-crime-defendant-details |
| rcc | api-cp-refdata-courthearing-courthouses |
| pcd | api-cp-crime-prosecution-case-details |

## Installation

```bash
/plugin install add-apim-api@agentic-plugins-marketplace
```
