---
name: openapi-spec-reviewer
description: Use when the user wants to review, audit, or check an OpenAPI v3 spec — applies HMCTS data-sharing policy (UK GDPR/DPA 2018), infrastructure SLA (Azure APIM/AKS), API standards, and security standards (OAuth 2, TLS, input validation). Returns a scored report with Critical/Warning/Info findings.
---

# Skill: OpenAPI Spec Reviewer

## Trigger

Invoke this skill when a user provides an OpenAPI v3.x specification (YAML or JSON)
and asks for a review, audit, or policy check.

Invocation command: `/openapi-spec-reviewer`

---

## Prerequisites

Before beginning the review, load and internalise the following knowledge documents
as active review lenses. They define the policy constraints against which the spec
will be assessed.

The knowledge files are bundled with this skill in its `knowledge/` directory
(resolve relative to this `SKILL.md`):

- `knowledge/data-sharing-policy.md`
- `knowledge/infrastructure-sla.md`
- `knowledge/api-standards.md`
- `knowledge/security-standards.md`

---

## Input Handling

### Version Guard

Check the `openapi` field at the root of the document.

- If the version is `2.x` (i.e. a Swagger/OAS2 spec), **stop immediately** and respond:

  > **Unsupported specification version.**
  > This skill only supports OpenAPI 3.x and higher. The provided specification
  > declares `openapi: <detected-version>`, which is OpenAPI v2 (Swagger).
  > Please upgrade your spec to OpenAPI 3.0.x or 3.1.x before requesting a review.

- If the `openapi` field is absent or the document cannot be parsed, respond:

  > **Parse error.**
  > The provided input could not be read as a valid OpenAPI document.
  > Please check that:
  > - The document is valid YAML or JSON
  > - The root-level `openapi` field is present (e.g. `openapi: "3.0.3"`)
  > - All `$ref` values point to resolvable locations
  >
  > Paste the corrected spec and re-run `/openapi-spec-reviewer`.

- If the document is structurally parseable but incomplete (e.g. missing `info`,
  `paths`, or `components`), continue the review but flag each missing section as
  a **Critical** finding under the relevant lens.

---

## Review Process

Apply each of the four lenses in sequence. For every issue found, record a finding
using the structure defined in the Output Format section below.

### Lens 1 — Data Sharing Policy

Source: `knowledge/data-sharing-policy.md`

Review the spec for:
- Presence and correctness of data classification markers in descriptions
- Exposure of personally identifiable information (PII) or sensitive case data in
  path parameters, query parameters, request bodies, or response schemas
- Missing or inadequate descriptions on fields that carry personal data
- Absence of consent or lawful basis statements where required by policy
- Use of `additionalProperties: true` on schemas that may leak sensitive fields
- Logging or tracing fields that could inadvertently capture PII

### Lens 2 — Infrastructure SLA

Source: `knowledge/infrastructure-sla.md`

Review the spec for:
- Declared or missing timeout values relative to SLA targets per endpoint category
- Rate limiting headers (`X-RateLimit-*`, `Retry-After`) absent from responses
- Missing `429 Too Many Requests` and `503 Service Unavailable` response definitions
  on endpoints subject to SLA constraints
- Response time expectations not communicated via documentation or extensions
- Bulk or streaming endpoints that lack pagination or chunking controls which
  could breach SLA targets under load

### Lens 3 — HMCTS API Standards

Source: `knowledge/api-standards.md`

Review the spec for:
- `info.title`, `info.version`, and `info.contact.email` completeness
- API versioning approach: version in media type (`application/vnd.hmcts.*+json;version=N`)
  rather than in the URL path
- Endpoint naming: lowercase, hyphen-separated, noun-based, no verbs in paths
- `operationId` values: present, unique, camelCase, descriptive
- HTTP method semantics: correct use of GET/POST/PUT/PATCH/DELETE
- Consistent error response schema across all `4xx`/`5xx` responses
- Pagination patterns on collection endpoints (`GET /resources`)
- Required response codes present for each operation (at minimum: success + `400` + `500`)
- Tag usage: all operations tagged; tags correspond to resource domains
- `$ref` usage: shared schemas extracted to `components/schemas`

### Lens 4 — Security Standards

Source: `knowledge/security-standards.md`

Review the spec for:
- Presence of a `securitySchemes` definition in `components`
- Global or per-operation `security` declarations — flag any operation with no
  security applied unless explicitly justified (e.g. health check)
- Use of OAuth 2.0 / OIDC flows appropriate to the HMCTS context
- Absence of API key schemes passed as query parameters (must use headers)
- HTTPS enforced in all `servers[*].url` entries — flag `http://` URLs
- Sensitive data (tokens, credentials, case references) not present in path
  parameters where they would be logged by infrastructure
- Input validation: `pattern`, `minLength`/`maxLength`, `minimum`/`maximum`
  constraints present on fields that accept user-supplied data
- Missing `401 Unauthorized` and `403 Forbidden` responses on secured operations

---

## Output Format

Structure the report as follows:

---

### OpenAPI Spec Review Report

**Spec title:** `<info.title>`
**Spec version:** `<info.version>`
**OpenAPI version:** `<openapi field value>`
**Review date:** `<today's date>`

---

#### Lens 1: Data Sharing Policy

| Severity | Location | Issue | Recommended Fix |
|----------|----------|-------|-----------------|
| Critical / Warning / Info | `paths./example/{id}.get` > `parameters[0]` | Description of issue | What to change |

*(Repeat rows for each finding. If no issues: "No issues found.")*

---

#### Lens 2: Infrastructure SLA

| Severity | Location | Issue | Recommended Fix |
|----------|----------|-------|-----------------|
| ... | ... | ... | ... |

---

#### Lens 3: HMCTS API Standards

| Severity | Location | Issue | Recommended Fix |
|----------|----------|-------|-----------------|
| ... | ... | ... | ... |

---

#### Lens 4: Security Standards

| Severity | Location | Issue | Recommended Fix |
|----------|----------|-------|-----------------|
| ... | ... | ... | ... |

---

### Summary

| Lens | Verdict | Critical | Warning | Info |
|------|---------|----------|---------|------|
| Data Sharing Policy | PASS / FAIL | N | N | N |
| Infrastructure SLA | PASS / FAIL | N | N | N |
| HMCTS API Standards | PASS / FAIL | N | N | N |
| Security Standards | PASS / FAIL | N | N | N |

**Overall Readiness Score: XX / 100**

Score calculation:
- Start at 100
- Deduct 10 points per Critical finding
- Deduct 3 points per Warning finding
- Deduct 1 point per Info finding
- Minimum score is 0

A lens is **PASS** if it has zero Critical findings.
A lens is **FAIL** if it has one or more Critical findings.

---

### Next Steps

List the top three highest-priority actions the API author should take before
this spec is considered ready for publication, based on the findings above.

---

## Severity Definitions

| Severity | Meaning |
|----------|---------|
| **Critical** | Blocks publication. Violates a mandatory policy, security requirement, or HMCTS standard. Must be resolved before the spec is approved. |
| **Warning** | Should be resolved before publication. Indicates a gap in policy compliance or best-practice deviation that carries meaningful risk. |
| **Info** | Improvement opportunity. Does not block publication but would improve quality, consistency, or future maintainability. |
