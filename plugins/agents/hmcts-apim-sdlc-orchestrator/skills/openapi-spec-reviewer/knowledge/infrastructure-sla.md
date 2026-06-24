# Infrastructure SLA

This document defines the infrastructure Service Level Agreements (SLAs) that
HMCTS APIs must satisfy. The `openapi-spec-reviewer` skill applies this file as a
review lens to identify gaps between what the spec declares and what the
infrastructure is contractually required to deliver.

---

## 1. Overview

HMCTS Common Platform APIs are hosted on **Azure API Management (APIM)** in
front of Spring Boot microservices running on **Azure Kubernetes Service (AKS)**.
All traffic from consumers enters via the APIM gateway; services are never
accessible directly from outside the cluster.

Environment topology:

| Environment | Purpose |
|---|---|
| `nonlive` / `sbox` | Integration testing, sandbox exploration |
| `staging` | Pre-production validation |
| `production` | Live criminal justice processing |

APIM enforces rate limiting, TLS termination, subscription key validation, and
request/response logging. Backend services on AKS are responsible for business
logic SLAs. The combined end-to-end SLA covers both layers.

---

## 2. Response Time Targets

Targets are measured from the APIM gateway to the first byte of the response
(excluding client network latency).

| Endpoint Category | Target p50 | Target p95 | Target p99 | Max Acceptable |
|-------------------|-----------|-----------|-----------|----------------|
| Read (single resource by ID) | 200 ms | 500 ms | 1 000 ms | 2 000 ms |
| Read (collection / search) | 300 ms | 800 ms | 2 000 ms | 5 000 ms |
| Write (create / update) | 300 ms | 800 ms | 2 000 ms | 5 000 ms |
| Bulk / batch operations | 500 ms | 2 000 ms | 5 000 ms | 30 000 ms |
| Health / liveness probes (`/actuator/health`) | 50 ms | 100 ms | 200 ms | 500 ms |
| Prometheus metrics (`/actuator/prometheus`) | 100 ms | 300 ms | 500 ms | 1 000 ms |

Operations whose p99 target exceeds 2 000 ms must include a note in their
`description` explaining why (e.g. bulk export, downstream legacy system).

---

## 3. Availability Targets

| Environment | Availability Target | Measurement Window |
|-------------|--------------------|--------------------|
| Production | 99.9% | Rolling calendar month |
| Staging | 99.5% | Rolling calendar month |
| Non-live / sandbox | 95.0% | Best-effort; planned maintenance windows permitted |

99.9% production availability equates to a maximum of ~43 minutes downtime per
month. Planned maintenance windows must be communicated via the HMCTS service
catalogue and do not count against the SLA.

---

## 4. Rate Limiting

Azure APIM enforces rate limits at the subscription key level. Limits are
applied per consumer product (subscription tier).

### 4.1 Limits

| Tier | Requests per Minute | Requests per Day | Burst (per 10 s) |
|------|--------------------|--------------------|------------------|
| Standard (most CP services) | 600 | 100 000 | 60 |
| Elevated (batch consumers) | 3 000 | 500 000 | 300 |
| Internal tooling / testing | 60 | 10 000 | 10 |

Rate limits are enforced by APIM and cannot be overridden at the service level.
Consumers that exceed their limit receive `429 Too Many Requests`.

### 4.2 Required Headers

The following response headers are injected by APIM on rate-limited operations
and must be declared in the OpenAPI spec for all secured operations:

| Header | Required | Description |
|--------|----------|-------------|
| `X-RateLimit-Limit` | Yes | Total requests allowed in the current window |
| `X-RateLimit-Remaining` | Yes | Requests remaining in the current window |
| `X-RateLimit-Reset` | Yes | Unix timestamp (seconds) when the window resets |
| `Retry-After` | Yes (on 429) | Seconds until the consumer may retry; present on `429` responses only |

---

## 5. Timeout Policy

APIM enforces gateway-level timeouts. Services must respond within the backend
timeout; operations that may exceed it must implement async patterns.

| Layer | Timeout Value |
|-------|--------------|
| APIM gateway (total request) | 30 seconds |
| APIM → backend service (forward timeout) | 25 seconds |
| Backend service → downstream CP backend | 20 seconds |
| Backend service → database | 5 seconds |
| Backend service → Azure Service Bus | 10 seconds |

Operations that may legitimately take longer than 25 seconds (e.g. document
generation, bulk export) must use an async pattern: accept the request with
`202 Accepted`, return a `Location` header pointing to a status endpoint, and
provide a GET status endpoint that returns `200` when complete.

---

## 6. Required Error Responses for SLA-Governed Endpoints

All operations must declare the following response codes. They are enforced
by APIM and will be returned even if the backend service does not implement them.

| HTTP Status | Condition | Required? |
|-------------|-----------|-----------|
| `400 Bad Request` | Invalid input / schema validation failure | Yes — all mutating operations and GET with query params |
| `401 Unauthorized` | Missing or invalid subscription key / token | Yes — all secured operations |
| `403 Forbidden` | Valid credentials but insufficient scope | Yes — all secured operations |
| `404 Not Found` | Resource does not exist | Yes — all operations with path parameters |
| `429 Too Many Requests` | Rate limit exceeded | Yes — all operations |
| `500 Internal Server Error` | Unhandled backend error | Yes — all operations |
| `503 Service Unavailable` | Backend or downstream system unavailable | Yes — all operations |
| `504 Gateway Timeout` | Backend did not respond within timeout | Yes — all operations |

---

## 7. Pagination and Bulk Operation Constraints

Collection endpoints (those returning arrays of resources) must implement
cursor-based or offset-based pagination with the following constraints:

| Parameter | Required | Default | Maximum |
|-----------|----------|---------|---------|
| `limit` | Yes | 20 | 100 |
| `offset` | For offset pagination | 0 | — |
| `cursor` | For cursor pagination | — | — |

- Default page size must be documented in the parameter `description`
- Maximum page size of 100 must be enforced and documented
- Responses must include a pagination envelope:
  - `total` — total number of matching records (where computable without
    excessive cost; omit and document if too expensive)
  - `limit`, `offset` / `next_cursor` — echo back the effective values used

Operations that return more than 1 000 records in a single response without
pagination are a rate-limiting and data minimisation violation and will be
flagged as Critical.

---

## 8. Review Checklist (for the Claude skill)

When applying this lens, the reviewer should check that the OpenAPI spec:

- [ ] Every operation declares a `429 Too Many Requests` response
- [ ] Every operation declares `503 Service Unavailable` and `504 Gateway Timeout`
      responses
- [ ] `X-RateLimit-Limit`, `X-RateLimit-Remaining`, and `X-RateLimit-Reset`
      response headers are declared on all secured operations
- [ ] `Retry-After` response header is declared on `429` responses
- [ ] Collection endpoints declare `limit` and `offset` (or `cursor`) query
      parameters with `maximum` constraints
- [ ] Collection response schemas include `total`, `limit`, and
      `offset` / `next_cursor` envelope fields
- [ ] Operations that may exceed 25 s use `202 Accepted` + `Location` async
      pattern and are not declared as synchronous returning `200`
- [ ] Any operation with a p99 target > 2 000 ms documents the reason in its
      `description`
