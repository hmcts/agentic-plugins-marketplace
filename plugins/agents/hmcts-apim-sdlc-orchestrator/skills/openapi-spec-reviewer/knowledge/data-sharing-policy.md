# Data Sharing Policy

This document defines HMCTS data sharing constraints that must be reflected in
OpenAPI specifications. The `openapi-spec-reviewer` skill applies this file as a
review lens to identify policy gaps before a spec is published.

---

## 1. Overview

HMCTS APIs in the Common Platform programme operate under the **Data Protection
Act 2018 (DPA 2018)** and **UK GDPR**. All APIs process personal data relating
to defendants, victims, witnesses, and legal representatives in the context of
criminal proceedings — a category that includes both standard personal data
(Article 6 UK GDPR) and special category data (Article 9 UK GDPR, e.g. health
information used in sentencing).

This policy applies to all `api-cp-*` spec libraries and `service-cp-*`
microservices in the HMCTS Common Platform programme. Compliance is assessed at
the OpenAPI specification layer; the spec must make data handling intent
explicit so downstream consumers can perform their own DPIA and data sharing
assessments.

Legal basis for processing: **Article 6(1)(e) UK GDPR** (public task), with
criminal justice processing further governed by **Schedule 1 Part 2 DPA 2018**
(substantial public interest — administration of justice). Special category
data requires **Article 9(2)(f)** (legal claims) or **Article 9(2)(g)**
(substantial public interest under Schedule 1 DPA 2018).

---

## 2. Data Classification Tiers

HMCTS follows HM Government (HMG) **Government Security Classifications (GSC)**
policy. All Common Platform data is classified at minimum **OFFICIAL**.

| Classification | Description | API Exposure Rules |
|----------------|-------------|-------------------|
| **OFFICIAL** | Standard government information including most case data, hearing dates, and court schedules | May be exposed in API responses; `description` of each field must state the data category |
| **OFFICIAL-SENSITIVE** | Case data that could prejudice proceedings, identify covert sources, or endanger individuals (e.g. victim/witness addresses, ongoing investigation details) | May only be exposed to explicitly authorised consumer systems; the spec must declare the restricted scope required |
| **SECRET / TOP SECRET** | Not applicable to Common Platform APIs | Must not appear in any Common Platform OpenAPI spec |

If a response schema contains any OFFICIAL-SENSITIVE fields, the operation
description must state: *"This operation returns OFFICIAL-SENSITIVE data. Caller
must hold the `<scope>` scope."*

---

## 3. Personally Identifiable Information (PII)

### 3.1 PII Categories

The following PII categories appear in Common Platform case data. Each carries
specific handling requirements.

| PII Category | Examples | Classification |
|---|---|---|
| Defendant identity | Full name, date of birth, National Insurance number | OFFICIAL |
| Defendant address | Home address, place of birth | OFFICIAL-SENSITIVE |
| Legal representation | Solicitor name, firm, contact details | OFFICIAL |
| Case identifiers | Case URN, case ID (UUID), hearing ID (UUID) | OFFICIAL |
| Victim / witness identity | Name, contact details | OFFICIAL-SENSITIVE |
| Health / medical data | Pre-sentence reports, mental health assessments | OFFICIAL-SENSITIVE (special category) |
| Financial data | Means assessment, fine details | OFFICIAL |
| Biometric data | DNA, fingerprint references | OFFICIAL-SENSITIVE (special category) |

### 3.2 Path and Query Parameter Rules

- **Case identifiers in path parameters must use opaque UUIDs**, not
  human-readable case numbers or URNs. Example: `{case_id}` must be a UUID
  format. Exception: `case_urn` is permitted where the URN is the canonical
  key for that API's domain and no UUID alternative exists.
- **No direct personal identifiers** (name, DOB, NI number, address) may appear
  as path or query parameters — they must be in the request body.
- Query parameters used for search/filter must not accept PII in plain text
  without a documented business justification in the operation description.
- All path and query parameters containing identifiers must declare
  `pattern` constraints to prevent injection.

### 3.3 Response Body Rules

- Every field in a response schema that contains PII must have a `description`
  that identifies the data category (using the table in §3.1) and states who
  may receive it.
- Response schemas must not include fields that the consuming service has no
  documented need for (data minimisation — see §5).
- Fields containing OFFICIAL-SENSITIVE data must not be included in generic
  summary/list responses; they may only appear in detail endpoints where the
  consumer has an explicit authorisation.
- Error response bodies must not echo back user-supplied input that may contain
  PII — error messages must reference field names, not field values.

---

## 4. Consent and Lawful Basis

The lawful basis for processing must be stated in the `info.description` of
every spec that handles personal data. Required wording:

> *"This API processes personal data under Article 6(1)(e) UK GDPR (public task)
> and the administration of justice provisions of Schedule 1 Part 2 DPA 2018.
> Special category data, where present, is processed under Article 9(2)(f)
> UK GDPR (legal claims) or Article 9(2)(g) (substantial public interest)."*

Operations that return special category data must additionally state the legal
basis in their own `description` field.

There is no consent mechanism for Common Platform data — processing is based
entirely on the public task / administration of justice lawful basis. Specs
must not imply that data subjects have a right to withdraw consent.

---

## 5. Data Minimisation

- `additionalProperties: true` is **prohibited** in all request and response
  schemas. Every property must be explicitly declared so that data minimisation
  can be assessed at review.
- Response schemas must expose only the fields that the consuming service's
  documented use case requires. Returning the full data model when only a
  subset is needed is a data minimisation violation.
- Collection / search endpoints must not return detailed PII in list responses;
  they should return identifiers and summary fields only, with detail available
  via a separate GET-by-ID endpoint.
- Request schemas must not accept fields that the operation does not use.
  Unused input fields are an injection surface and a minimisation violation.

---

## 6. Audit and Traceability Fields

All operations that handle PII must propagate the following headers. They
must be declared in the spec as required request headers (or as parameters
on the path/operation):

| Header | Required | Purpose |
|--------|----------|---------|
| `X-Correlation-Id` | Yes | End-to-end request tracing; must be a UUID generated by the originating system if not present |
| `CJSCPPUID` | Yes | Identifies the human or service account making the request; mandatory for all backend calls in Common Platform |

**Logging exclusions:** The following fields must never be written to application
logs, even in DEBUG mode:

- Defendant name, date of birth, National Insurance number
- Victim / witness name or address
- Health / biometric data fields
- The value of any `Authorization` or `Ocp-Apim-Subscription-Key` header

`X-Correlation-Id` and `CJSCPPUID` may be logged for audit purposes.

---

## 7. Cross-Border and Third-Party Data Sharing

- Common Platform data must not be transferred outside the UK / EEA without
  explicit authorisation from the HMCTS Data Protection Officer.
- OpenAPI specs must not declare `servers[*].url` entries pointing to domains
  outside `*.hmcts.net`, `*.platform.hmcts.net`, or `*.cjscp.org.uk`.
  Third-party or external domain server URLs indicate an unapproved data sharing
  arrangement and will be flagged as Critical.
- External `$ref` URLs in schema definitions are prohibited — all schemas must
  be defined locally to prevent inadvertent data leakage to third-party schema
  registries.
- API specs must not be published to public registries (e.g. SwaggerHub public)
  without an explicit data sharing agreement covering the consuming organisation.

---

## 8. Review Checklist (for the Claude skill)

When applying this lens, the reviewer should check that the OpenAPI spec:

- [ ] `info.description` contains a lawful basis statement referencing UK GDPR
      and DPA 2018 (see §4 for required wording)
- [ ] No path or query parameter contains direct personal identifiers (name,
      DOB, NI number, address)
- [ ] All path parameters that are identifiers use UUID format with
      `pattern: '^[0-9a-fA-F-]{36}$'` or equivalent (exception: documented URN fields)
- [ ] `additionalProperties: true` does not appear in any request or response schema
- [ ] Every schema property containing PII has a `description` that names the
      data category from §3.1
- [ ] Operations returning OFFICIAL-SENSITIVE data state the required scope in
      their `description`
- [ ] Special category data operations include Article 9 lawful basis in their
      `description`
- [ ] `X-Correlation-Id` and `CJSCPPUID` are declared as required headers on
      all non-public operations
- [ ] Error response schemas do not include properties that echo user input
- [ ] No `servers[*].url` points to a domain outside approved HMCTS namespaces
- [ ] No external `$ref` URLs appear in schema definitions
- [ ] Collection endpoints do not return detailed PII fields (name, DOB, address)
      in list/summary responses
