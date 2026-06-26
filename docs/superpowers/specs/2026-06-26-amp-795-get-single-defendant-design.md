# AMP-795 — Get Single Defendant by ID

**Date:** 2026-06-26
**Repos:** `api-cp-crime-hearing`, `service-cp-crime-hearing`
**Branch:** `dev/AMP-795` (both repos)

---

## User Story

As a consumer, I want to retrieve a single defendant by their ID for a given hearing and case so that I can display or process that defendant's details without fetching the full defendant list.

---

## Endpoint

```
GET /hearings/{hearingId}/cases/{caseURN}/defendants/{defendantId}
```

### Path Parameters

| Parameter | Type | Format | Required | Description |
|---|---|---|---|---|
| `hearingId` | string | uuid | yes | Unique identifier of the hearing |
| `caseURN` | string | — | yes | Unique case URN (1–30 alphanumerics) |
| `defendantId` | string | uuid | yes | Unique identifier of the defendant for this appearance |

### Responses

| Status | Description |
|---|---|
| 200 | `DefendantView` object for the matched defendant |
| 400 | `caseURN` fails alphanumeric validation |
| 401 | Missing or invalid access token |
| 403 | Token lacks `hearing.read` scope |
| 404 | Hearing not found, or no defendant matches `defendantId` in the case |
| 500 | Unexpected error |

---

## Acceptance Criteria

**AC1 — Happy path, defendant found**
Given a `hearingId` and `caseURN` that resolve to a hearing, and a `defendantId` that identifies a defendant on that case → **200** with that defendant's `DefendantView`.

**AC2 — Defendant not found**
Given a `hearingId` and `caseURN` that resolve to a hearing, and a `defendantId` that does not match any defendant on that case → **404**.

**AC3 — Hearing not found**
Given a `hearingId` that does not resolve to any hearing → **404**.

---

## api-cp-crime-hearing Changes

### openapi-spec.yml

Add one new path entry under `paths`:

```yaml
/hearings/{hearingId}/cases/{caseURN}/defendants/{defendantId}:
  get:
    summary: Get a single defendant by ID for a hearing and case
    description: >-
      Returns the details of a single defendant identified by their appearance-scoped
      ID within a specific hearing and case. Returns 404 if the hearing does not
      exist or if no defendant with the given ID exists on the case.
    operationId: getDefendant
    tags:
      - hearings
    parameters:
      - hearingId (path, UUID)
      - caseURN (path, string)
      - defendantId (path, UUID)
    responses:
      200: DefendantView
      400/401/403/404/500: existing shared response components
```

**No new schema.** `DefendantView` (id, masterDefendantId, name, dateOfBirth, offences) is exactly the right shape for a single defendant.

### New example file

`src/main/resources/openapi/examples/defendant.yaml` — single-defendant example (mirrors one entry from `defendants.yaml`).

---

## service-cp-crime-hearing Changes

### DefendantMapper

Add a public `mapToDefendantView(DefendantEntry)` method that delegates to the existing private `toDefendantView`. This gives callers a single-item mapping path without exposing the private helper.

### HearingService

Extract `findDefendantsForCase(UUID hearingId, String caseURN) → List<DefendantEntry>` as a private method containing the prosecution-case filtering stream logic currently inlined in `getDefendants`. Refactor `getDefendants` to call it. Add:

```java
public DefendantView getDefendant(UUID hearingId, String caseURN, UUID defendantId) {
    return findDefendantsForCase(hearingId, caseURN).stream()
        .filter(d -> defendantId.equals(d.getId()))
        .findFirst()
        .map(defendantMapper::mapToDefendantView)
        .orElseThrow(() -> new ResponseStatusException(NOT_FOUND, "No defendant found for the supplied defendantId"));
}
```

404 for hearing-not-found (AC3) propagates automatically from `HearingClient.getHearing` via `HttpClientErrorException` → `GlobalExceptionHandler.handleClientException`.

### HearingController

Implement the generated `getDefendant(UUID hearingId, String caseURN, UUID defendantId)` method:
- validate `caseURN` with the existing `validateCaseUrn` helper
- delegate to `hearingService.getDefendant`
- return `ResponseEntity.ok().contentType(APPLICATION_JSON).body(view)`

---

## Tests

### Unit tests

| Class | New cases |
|---|---|
| `HearingControllerTest` | `getDefendant_should_returnOk`, `getDefendant_should_rejectCaseUrn_whenNotAlphanumeric` |
| `HearingServiceTest` | happy path (defendant found), defendant not found → 404, hearing returns null → propagates |

### Integration tests (HearingControllerIntegrationTest)

| Test | AC |
|---|---|
| `getDefendant_should_returnOk_withDefendantFields` | AC1 |
| `getDefendant_should_return404_whenDefendantIdNotFound` | AC2 |
| `getDefendant_should_return404_whenHearingDoesNotExist` | AC3 |

---

## Post-implementation Steps

1. `./gradlew openApiGenerate` then `publishToMavenLocal` in api-cp-crime-hearing
2. Build and test service-cp-crime-hearing against the local spec
3. PRs on both repos → merge to main
4. GitHub Release on api-cp-crime-hearing → triggers `publish-api-docs.yml` → catalog publisher registers in amp-catalog
5. GitHub Release on service-cp-crime-hearing

---

## Decision Log

| Decision | Rationale |
|---|---|
| Reuse `DefendantView` schema (not a new type) | Identical shape; no schema proliferation |
| Extract `findDefendantsForCase` private helper | Avoids duplicating the prosecution-case stream logic between `getDefendants` and `getDefendant` |
| 404 for caseURN-not-matching-any-case | Implied by AC2 — if the case doesn't exist on the hearing, the defendant cannot be found |
| `defendantId` maps to `DefendantEntry.id` | The path param is the appearance-scoped id, consistent with the existing `DefendantView.id` field |