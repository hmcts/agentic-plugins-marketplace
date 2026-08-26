---
name: add-apim-api
description: Step-by-step checklist for adding a new APIM API to the HMCTS CP crime API infrastructure Terraform config. Use whenever adding a new API, registering a new service in APIM, or asking how to wire up a new endpoint — even if the user doesn't say "skill". Triggers on phrases like "add an API to infra", "new API entry", "register this in APIM", "add to tfvars".
---

# Adding a New APIM API

Only one file needs changing per environment: the relevant `*.tfvars`.

## Checklist

- [ ] Choose a map key
- [ ] Set `display_name` following the naming convention
- [ ] Set `path` following the path convention
- [ ] Set `service_host` safely (no secrets scanner violations)
- [ ] Add the entry to each environment's `*.tfvars`

## Naming Conventions

### display_name pattern

```
"Crime <Domain Description> API (<shortname>)"
```

- Sentence case
- Always ends with `API (<shortname>)` — the shortname in parentheses is mandatory
- `<shortname>` is the same as the `path` suffix (e.g. `slc`, `hrds`, `pcr`)

**`display_name`**, **`path`**, and **`service_path`** for all 6 CP APIs:

| Term | display_name | path | service_path | Map key |
|---|---|---|---|---|
| slc | `"Crime Scheduling and Listing Schedule API (slc)"` | `amp/slc` | `/slc` | `courtschedule` |
| hrds | `"Crime Hearing Results Document Subscription API (hrds)"` | `amp/hrds` | `/hrds` | `hearingresults` |
| pcr | `"Crime Results PCR API (pcr)"` | `amp/pcr` | `/pcr` | `pcr` |
| dl | `"Crime Defendant Details API (dl)"` | `amp/dl` | `/dl` | `defendantdetails` |
| rcc | `"Crime Ref Data Court Hearing Courthouse API (rcc)"` | `amp/rcc` | `/rcc` | `courthouse` |
| pcd | `"Crime Prosecution Case Details API (pcd)"` | `amp/pcd` | `/pcd` | `prosecutioncasedetails` |

**Map key** — drives the Terraform resource name. Lowercase, no hyphens, no spaces.

## tfvars Entry Pattern

Add this block inside `apis = {` in each environment's `*.tfvars`:

```hcl
  {map-key} = {
    openapi_spec_path = "../src/main/resources/openapi/openapi-spec.yml"
    display_name      = "Crime X and Y Z API ({shortname})"
    path              = "amp/{shortname}"
    service_host      = "{hostname-without-.org.uk}"
    service_path      = "/{shortname}"
    revision          = "1"
  }
```

### sbox example (for reference)
```hcl
  courtschedule = {
    openapi_spec_path = "../src/main/resources/openapi/openapi-spec.yml"
    display_name      = "Crime Scheduling and Listing Schedule API (slc)"
    path              = "amp/slc"
    service_host      = "{cp-appgw-url}"
    service_path      = "/slc"
    revision          = "1"
  }
```

## Secrets Scanner Rule

The HMCTS secrets scanner flags URLs containing `.cjscp.org.uk`, `.cpp.nonlive`, `.cpp.live`, or `.vault.azure.net`.

**Safe** — store only the hostname prefix, no protocol, no `.org.uk`:
```hcl
service_host = "{cp-appgw-url}"
service_path = "/slc"
```

`apis.tf` reconstructs the full backend URL automatically:
```hcl
service_url = "https://${each.value.service_host}.org.uk${each.value.service_path}"
```

## Per-Environment Entra IDs

Each `*.tfvars` must have its own `entra_tenant_id` and `entra_client_id`. Get the correct values from the team — never copy IDs across environments.

## Policy

No changes needed to `policies/api-policy.xml`, `apis.tf`, `products.tf`, or `variables.tf`.

JWT auth, rate limiting (30/min), quota (500/day), and concurrency (max 10) are applied automatically at the API level via `azurerm_api_management_api_policy` in `apis.tf`, templated with the Entra IDs from tfvars.

## Adding a New Environment (new `*.tfvars`)

If the environment doesn't have a tfvars file yet, creating one will trigger the workflow — but it will fail unless 3 GitHub repository variables exist for it.

The workflow derives variable names from the tfvars filename (e.g. `dev.tfvars` → uppercase `DEV`):

| GitHub Variable | Example for `dev` |
|---|---|
| `AZURE_CLIENT_ID_{ENV}` | `AZURE_CLIENT_ID_DEV` |
| `AZURE_SUBSCRIPTION_{ENV}` | `AZURE_SUBSCRIPTION_DEV` |
| `AZURE_SUBSCRIPTION_ID_{ENV}` | `AZURE_SUBSCRIPTION_ID_DEV` |

Plus one shared variable (already set if sbox works):

| GitHub Variable | Used for |
|---|---|
| `TFSTATE_STORAGE_ACCOUNT_NONPROD` | All non-prod environments |
| `TFSTATE_STORAGE_ACCOUNT_PROD` | `prod` only |

Set these at: **GitHub repo → Settings → Secrets and variables → Actions → Variables**

The federated credentials that back `AZURE_CLIENT_ID_{ENV}` are managed in the HMCTS `azure-github-federation-config` repo — raise a PR there to onboard a new environment or repo before the GitHub variable will work.

## What NOT to touch for a new API

These files never need changing when adding a new API:
- `apis.tf`
- `products.tf`
- `variables.tf`
- `policies/api-policy.xml`
