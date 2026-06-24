# Security Standards

This document defines the security requirements that HMCTS OpenAPI specifications
must satisfy. The `openapi-spec-reviewer` skill applies this file as a review lens
to identify authentication, authorisation, transport, and input validation gaps
before a spec is published.

---

## 1. Overview

<!-- TODO: Describe the HMCTS security framework within which these APIs operate.
     Reference any central security policy documents, the HMCTS identity provider,
     and any relevant compliance standards (e.g. NCSC guidelines, ISO 27001). -->

HMCTS Common Platform APIs operate within the following security framework:

- **Platform**: Azure API Management (APIM) as the gateway; services run on Azure Kubernetes Service (AKS) in the `hmcts.net` private network
- **Identity provider**: HMCTS Reform IDAM (Identity and Access Management) — an OAuth 2.0 / OpenID Connect provider for user-facing flows; Azure AD for service-to-service flows
- **Subscription management**: All external consumers must hold an `Ocp-Apim-Subscription-Key` issued by HMCTS APIM; this key identifies the consuming system
- **Compliance**: NCSC Cloud Security Principles, HMG Government Security Classifications, UK GDPR / DPA 2018, and NIST SP 800-53 controls as adopted by HMCTS
- **Penetration testing**: All new APIs must pass a CREST/CHECK-qualified penetration test before production release

---

## 2. Transport Security

- All `servers[*].url` entries must use `https://` — `http://` is not permitted
  in any environment other than local development
- TLS version requirements:

  **TLS 1.2** is the minimum version enforced at the HMCTS APIM gateway.
  **TLS 1.3** is preferred and used by default on all new APIM instances.
  TLS 1.0 and 1.1 are disabled at the gateway and must not be referenced in specs.

---

## 3. Authentication

<!-- TODO: Define the approved authentication mechanisms for HMCTS APIs.
     The table below lists common patterns — replace with the actual approved list. -->

| Mechanism | Status | Notes |
|-----------|--------|-------|
| OAuth 2.0 — Client Credentials (via IDAM / Azure AD) | **Approved** | Standard for service-to-service (machine) calls |
| OAuth 2.0 — Authorization Code + PKCE (via IDAM) | **Approved** | For user-facing flows where a human identity is required |
| OIDC (via HMCTS Reform IDAM) | **Approved** | Wraps OAuth 2.0; use for all user identity assertions |
| API Key header (`Ocp-Apim-Subscription-Key`) | **Approved** | Used by APIM to identify the consuming system; must be declared as an `apiKey` scheme with `in: header` |
| API Key query parameter | **Prohibited** | API keys in query parameters appear in server access logs and referrer headers |
| Basic Auth | **Prohibited** | Username/password over HTTP Basic is not permitted on any Common Platform endpoint |
| HMAC-SHA256 (webhook callbacks) | **Conditionally Approved** | Permitted only for inbound webhook/callback operations; must be documented with the `X-Hub-Signature-256` header scheme |

### 3.1 securitySchemes

- Every spec must declare at least one entry in `components/securitySchemes`
- The scheme must match an approved mechanism from the table above
- OAuth 2.0 scopes must be declared with descriptions
- Scope naming convention: `hmcts:<domain>:<action>`
  - Examples: `hmcts:case-details:read`, `hmcts:hearings:write`, `hmcts:defendants:read`
  - `<domain>` matches the API's resource domain in kebab-case
  - `<action>` is one of: `read`, `write`, `delete`, `admin`
- The `Ocp-Apim-Subscription-Key` scheme must be declared when the API is published via APIM:
  ```yaml
  components:
    securitySchemes:
      SubscriptionKey:
        type: apiKey
        in: header
        name: Ocp-Apim-Subscription-Key
  ```

---

## 4. Authorisation

- Every operation must have a `security` declaration, either globally or at the
  operation level
- Operations that are intentionally public (e.g. health checks, status endpoints)
  must be explicitly exempted with a comment in the spec and `security: []`
- All secured operations must declare `401 Unauthorized` and `403 Forbidden`
  response codes

HMCTS Common Platform uses an **ABAC (Attribute-Based Access Control)** model
implemented via the `cp-auth-rules-filter` Drools-based servlet filter. The filter:

1. Reads the `CJSCPPUID` header to identify the requesting user/service
2. Calls the `usersgroups-query-api` to fetch the caller's group memberships and permissions
3. Evaluates Drools rules to determine whether the specific operation on the specific resource is permitted

Specs must declare the OAuth 2.0 scope(s) required for each operation. At the
API Gateway layer, scope validation is a coarse-grained first check; the
`cp-auth-rules-filter` provides fine-grained authorisation downstream.

Operations that expose data across organisational boundaries (e.g. data visible
to defence solicitors vs Crown Prosecution Service) must declare separate scopes
for each consumer role.

---

## 5. Sensitive Data in URLs

- Tokens, credentials, and session identifiers must never appear in path or query
  parameters — they must be passed in request headers
- Case references and defendant identifiers used as path parameters must be
  opaque identifiers (e.g. UUID), not human-readable values that could leak
  information if logged
- **Case URNs** (`case_urn`) are an exception: they are the canonical public
  identifier for a criminal case and are permitted as path parameters, but must
  be declared with a `pattern` constraint (e.g. `'^[A-Z]{2}[0-9]{8}[A-Z0-9]{2}$'`)
- **Hearing IDs, defendant IDs, and document IDs** must be UUIDs in path parameters
- **Names, dates of birth, addresses** must never appear as path or query parameters

---

## 6. Input Validation

All fields that accept user-supplied data must declare appropriate constraints
in the schema to prevent injection and oversized payload attacks:

| Field Type | Required Constraints |
|------------|---------------------|
| String | `minLength`, `maxLength`, `pattern` (where format is known) |
| Integer / Number | `minimum`, `maximum` |
| Array | `minItems`, `maxItems` |
| Free-text / `additionalProperties` | **Prohibited in request bodies.** All properties must be declared explicitly to prevent injection payloads being accepted via unknown fields. |

---

## 7. Security Headers

<!-- TODO: Define which security-related response headers the API must declare
     in its spec (e.g. X-Content-Type-Options, X-Frame-Options, HSTS).
     Note: some of these may be injected by the API Gateway rather than the
     application — clarify which the spec must declare explicitly. -->

The following security headers are **injected by APIM** and do not need to be
declared in the OpenAPI spec, but implementations must not override them:

| Header | Value injected by APIM | Spec declaration required? |
|--------|----------------------|---------------------------|
| `Strict-Transport-Security` | `max-age=31536000; includeSubDomains` | No |
| `X-Content-Type-Options` | `nosniff` | No |
| `X-Frame-Options` | `DENY` | No |
| `Content-Security-Policy` | Configured per APIM policy | No |
| `Referrer-Policy` | `no-referrer` | No |

The following headers **must be declared in the OpenAPI spec** as response headers
on the relevant operations, because they carry semantic meaning that consumers
need to handle:

| Header | Operations | Purpose |
|--------|------------|---------|
| `X-Correlation-Id` | All | Echoes the request correlation ID for end-to-end tracing |
| `X-RateLimit-Limit` | All secured | Rate limit ceiling |
| `X-RateLimit-Remaining` | All secured | Remaining quota |
| `X-RateLimit-Reset` | All secured | Window reset timestamp |
| `Retry-After` | 429 responses | Seconds until retry is safe |
| `Location` | 201 Create, 202 Async | URL of created resource or status endpoint |

---

## 8. Secrets and Credentials in Specs

- API keys, tokens, passwords, and connection strings must never appear in
  OpenAPI spec files (including `example` values)
- Example values for authentication fields must use clearly fake placeholders
  (e.g. `"Bearer <your-token>"`, `"TODO-replace-with-real-value"`)

---

## 9. Dependency and Supply Chain

- All schema `$ref` values must be local references (`#/components/schemas/...` or
  relative file paths within the same repo)
- External `$ref` URLs (e.g. `https://...` or `http://...`) are **prohibited**:
  they create a build-time dependency on a third-party service and may leak schema
  information or include malicious content
- Shared schema components must be vendored into the repo under
  `src/main/resources/openapi/schema/` and referenced locally

---

## 10. Review Checklist (for the Claude skill)

When applying this lens, the reviewer should check that the OpenAPI spec:

- [ ] All `servers[*].url` values use `https://`
- [ ] `components/securitySchemes` is present and non-empty
- [ ] At least one approved authentication scheme is declared
- [ ] API key schemes do not use `in: query`
- [ ] A `security` declaration is present globally or on every operation
- [ ] Operations with `security: []` have a documented justification
- [ ] All secured operations declare `401` and `403` responses
- [ ] All string fields that accept user input declare `maxLength`
- [ ] No real credentials or tokens appear in `example` values
- [ ] No external `$ref` URLs appear anywhere in the spec
- [ ] API key scheme, if present, uses `in: header` not `in: query`
- [ ] `Ocp-Apim-Subscription-Key` is declared as an `apiKey` header scheme when API is APIM-published
- [ ] OAuth 2.0 scopes follow the `hmcts:<domain>:<action>` naming convention
- [ ] `CJSCPPUID` is declared as a required request header on all non-public operations
- [ ] `X-Correlation-Id` is declared as a response header on all operations
- [ ] All string input fields declare `maxLength` and `pattern` where format is known
- [ ] `additionalProperties: true` does not appear in any request body schema
- [ ] HMAC security schemes (where present) use `X-Hub-Signature-256` header pattern
- [ ] No Basic Auth scheme is declared
- [ ] All `servers[*].url` values use `https://` (not `http://`)