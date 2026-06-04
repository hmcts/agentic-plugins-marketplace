# HMCTS API Standards

This document captures the HMCTS RESTful API Standards that OpenAPI specifications
in this repository must comply with. The `openapi-spec-reviewer` skill applies this
file as a review lens to enforce consistency and quality across all APIs.

The canonical reference is the [HMCTS RESTful API Standards](https://hmcts.github.io/restful-api-standards/).
This file records the key rules as actionable, reviewable checklist items.

---

## 1. Spec Metadata

Every OpenAPI specification must include complete metadata in the `info` object.

| Field | Requirement |
|-------|-------------|
| `info.title` | Required. Human-readable name of the API. |
| `info.description` | Required. Purpose of the API and the business domain it serves. |
| `info.version` | Required. SemVer string (e.g. `1.2.0`). Must not be `0.0.0` in a published spec. |
| `info.contact.email` | Required. Team or service email address. |
| `info.license.name` | Required. Must be `MIT` for HMCTS open APIs. |
| `info.contact.name` | Recommended. Team name (e.g. `HMCTS APIM`). |
| `x-api-id` | Recommended. Stable UUID identifying this API in the service catalogue. |

---

## 2. Versioning

<!-- TODO: Confirm the approved versioning approach. The placeholder below
     reflects content-type versioning as referenced in API-VERSIONING-STRATEGY.md
     — adjust if the standard differs. -->

- API version must be communicated via the `Accept` / `Content-Type` media type:
  `application/vnd.hmcts.<resource>+json;version=<N>`
  Example: `application/vnd.hmcts.case-details+json;version=1`
- Version must **not** appear in the URL path (e.g. `/v1/resources` is non-compliant)
- The `info.version` field must follow SemVer (`MAJOR.MINOR.PATCH`)
- Major version increments (breaking changes) require a new media type version number
- Minor/patch changes are backward-compatible and do not require a version bump in the media type

---

## 3. URL and Path Design

- Paths must be lowercase and hyphen-separated (kebab-case): `/case-hearings`
- Path segments must be nouns; verbs are not permitted in paths
- Resource names must be plural: `/defendants`, `/hearings`, `/cases`
  Exception: singleton sub-resources (e.g. `/cases/{case_id}/status`) may use singular
- Path parameters must use snake_case: `{defendant_id}`, `{hearing_date}`, `{case_urn}`
- Sub-resources use nested paths: `/cases/{case_id}/hearings`, not a flat `/case-hearings`
- Domain-specific conventions:
  - Case identifiers: `{case_id}` (UUID) or `{case_urn}` (URN string) depending on domain key
  - Hearing identifiers: `{hearing_id}` (UUID)
  - Court identifiers: `{courthouse_id}`, `{courtroom_id}` (UUID)

---

## 4. HTTP Methods

| Method | Permitted Use |
|--------|--------------|
| `GET` | Retrieve a resource or collection. Must be idempotent and side-effect free. |
| `POST` | Create a new resource. |
| `PUT` | Replace a resource entirely. |
| `PATCH` | Partial update of a resource. |
| `DELETE` | Remove a resource. |

- Prefer `PATCH` over `PUT` for partial updates — Common Platform resources are complex
  objects; replacing the entire resource is rarely safe
- `PUT` is acceptable only when the full resource state is always known to the caller
- `DELETE` must return `204 No Content` (no body) on success

---

## 5. Operation IDs

- Every operation must have a unique `operationId`
- Format: camelCase, descriptive, follows the pattern `<verb><Resource>By<Qualifier>`
  e.g. `getHearingByHearingId`, `createDefendantCase`
- Must not contain spaces, hyphens, or underscores

---

## 6. Tags

- Every operation must be assigned at least one tag
- Tags must correspond to resource domains (e.g. `hearings`, `defendants`, `scheduling`)
- Tag names must be lowercase and hyphen-separated
- All tags used in operations must be declared in the top-level `tags` array with a description

---

## 7. Parameters

- All path parameters must be marked `required: true`
- Query parameters must include a `description` explaining their effect
- Parameter names use snake_case
- Boolean flags should be avoided as path parameters — use query parameters

Standard query parameters for collection endpoints:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `limit` | integer | Yes | Maximum records to return. Default: 20, Maximum: 100 |
| `offset` | integer | No | Zero-based record offset for pagination. Default: 0 |
| `sort` | string | No | Sort field and direction, e.g. `hearing_date:asc` |

All collection endpoints must declare `limit` and `offset` at minimum.

---

## 8. Request and Response Bodies

- Request bodies must reference a named schema in `components/schemas`
- Response bodies must reference a named schema in `components/schemas`
- Inline schemas are only acceptable for trivially simple responses (e.g. `string`)
- All schema properties must include a `description`

---

## 9. Error Responses

All operations must declare consistent error responses. The standard `ErrorResponse`
schema (defined in `components/schemas`) must be used for all `4xx` and `5xx` responses.

Minimum required response codes per operation:

| Code | Condition | Required on |
|------|-----------|-------------|
| `400` | Bad request / validation failure | All mutating operations; GET with query params |
| `401` | Unauthenticated | All secured operations |
| `403` | Unauthorised | All secured operations |
| `404` | Resource not found | All operations with path parameters |
| `409` | Conflict — resource already exists | `POST` create operations |
| `422` | Unprocessable Entity — business rule violation | Mutating operations |
| `429` | Too Many Requests | All operations (rate limited by APIM) |
| `500` | Internal server error | All operations |
| `503` | Service Unavailable | All operations |
| `504` | Gateway Timeout | All operations |

---

## 10. Schemas and Components

- All reusable schemas must live in `components/schemas`
- Schema names must be PascalCase: `HearingDetail`, `DefendantSummary`
- Required fields must be declared in the `required` array
- `additionalProperties: true` is discouraged; use explicit schema definitions
- Enumerations must use `enum` with all permitted values listed

---

## 11. Examples

- Every schema in `components/schemas` should include at least one example
- Path-level or operation-level `examples` are preferred over inline `example` values
  for complex objects

---

## 12. Review Checklist (for the Claude skill)

When applying this lens, the reviewer should check that the OpenAPI spec:

- [ ] `info.title`, `info.description`, `info.version`, and `info.contact.email` are present and non-empty
- [ ] `info.version` is not `0.0.0` (placeholder value)
- [ ] No version segment appears in any path (e.g. `/v1/`, `/v2/`)
- [ ] All paths are lowercase and use hyphens, not underscores or camelCase
- [ ] All `operationId` values are present, unique, and camelCase
- [ ] All operations have at least one tag
- [ ] Top-level `tags` array is present and all used tags are declared
- [ ] Standard error response codes are present on every operation
- [ ] All request/response bodies reference `$ref` schemas in `components/schemas`
- [ ] `DELETE` operations return `204` (no body schema)
- [ ] `POST` operations declare `409 Conflict` response
- [ ] Collection endpoints declare `limit` and `offset` query parameters with `maximum: 100`
- [ ] Collection response schemas include `total`, `limit`, and `offset` fields
- [ ] `info.contact.email` is a team address (not a personal email)
- [ ] `info.license.name` is `MIT`
- [ ] Vendor media type versioning (`application/vnd.hmcts.*+json`) is used where the API uses versioning