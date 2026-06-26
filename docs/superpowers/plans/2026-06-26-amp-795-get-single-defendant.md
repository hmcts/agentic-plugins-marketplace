# AMP-795 — Get Single Defendant by ID — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `GET /hearings/{hearingId}/cases/{caseURN}/defendants/{defendantId}` to `api-cp-crime-hearing` (OpenAPI spec) and `service-cp-crime-hearing` (Spring Boot implementation), then release both and publish the updated spec to the AMP catalog.

**Architecture:** The new endpoint reuses the existing `HearingsApi` interface, `DefendantView` schema, and `getHearing` backend call. A private `findDefendantsForCase` helper is extracted from the existing `getDefendants` flow and shared with the new `getDefendant` method. A 404 for a missing hearing propagates automatically from `HearingClient` via `HttpClientErrorException`; a 404 for a missing defendant is thrown explicitly by the service.

**Tech Stack:** Java 25, Spring Boot 4.1.0, OpenAPI Generator 7.23.0, WireMock (integration tests), Gradle 8.x, spectral (spec linting), GitHub Releases, AMP catalog (`hmcts/amp-catalog`).

## Global Constraints

- Java 25 toolchain (`java.gradle`) — `jakarta` imports only, `javax` is banned
- Compiler warnings are errors (`-Werror`) — never add `@SuppressWarnings` without justification
- PMD ruleset at `.github/pmd-ruleset.xml` — generated code excluded, hand-written code is not
- All schemas stay inline in `openapi-spec.yml` — no external JSON Schema files
- Examples live in separate YAML files under `src/main/resources/openapi/examples/`
- OpenAPI 3.0.x only
- `caseURN` path parameter must be validated against `^[0-9a-zA-Z]{1,30}$` before reaching the service — same rule as existing endpoints
- All path/log inputs must be sanitised with `Encode.forJava()` (OWASP encoder) before logging
- Never edit files under `build/generated/` — edit the spec and re-run `openApiGenerate`

---

## File Map

### api-cp-crime-hearing

| Action | File |
|---|---|
| Modify | `src/main/resources/openapi/openapi-spec.yml` |
| Create | `src/main/resources/openapi/examples/defendant.yaml` |

### service-cp-crime-hearing

| Action | File |
|---|---|
| Modify | `build.gradle` (update api-cp-crime-hearing version for local dev then for release) |
| Modify | `src/main/java/uk/gov/hmcts/cp/mappers/DefendantMapper.java` |
| Modify | `src/main/java/uk/gov/hmcts/cp/services/HearingService.java` |
| Modify | `src/main/java/uk/gov/hmcts/cp/controllers/HearingController.java` |
| Modify | `src/test/java/uk/gov/hmcts/cp/mappers/DefendantMapperTest.java` |
| Modify | `src/test/java/uk/gov/hmcts/cp/services/HearingServiceTest.java` |
| Modify | `src/test/java/uk/gov/hmcts/cp/controllers/HearingControllerTest.java` |
| Modify | `src/test/java/uk/gov/hmcts/cp/integration/HearingControllerIntegrationTest.java` |

---

## Task 1: Branch Setup

**Files:** None — git operations only.

- [ ] **Step 1: Pull latest main and create branch in api-cp-crime-hearing**

```bash
cd /Users/srivanimuddineni/HMCTS/APIM/api-cp-crime-hearing
git checkout main
git pull origin main
git checkout -b dev/AMP-795
```

Expected: branch `dev/AMP-795` created from latest main.

- [ ] **Step 2: Pull latest main and create branch in service-cp-crime-hearing**

```bash
cd /Users/srivanimuddineni/HMCTS/APIM/service-cp-crime-hearing
git checkout main
git pull origin main
git checkout -b dev/AMP-795
```

Expected: branch `dev/AMP-795` created from latest main.

---

## Task 2: OpenAPI Spec — Add New Endpoint and Example

**Files:**
- Modify: `src/main/resources/openapi/openapi-spec.yml` (api-cp-crime-hearing)
- Create: `src/main/resources/openapi/examples/defendant.yaml` (api-cp-crime-hearing)

**Interfaces:**
- Produces: `operationId: getDefendant` — the OpenAPI Generator emits `getDefendant(UUID hearingId, String caseURN, UUID defendantId)` on `HearingsApi` with return type `ResponseEntity<DefendantView>`

- [ ] **Step 1: Add the new path to openapi-spec.yml**

In `src/main/resources/openapi/openapi-spec.yml`, insert the block below immediately after the closing of the `/hearings/{hearingId}/cases/{caseURN}/defendants:` block (after the last `500` response reference on that path, before the `components:` key):

```yaml
  /hearings/{hearingId}/cases/{caseURN}/defendants/{defendantId}:
    get:
      summary: Get a single defendant by ID for a hearing and case
      description: >-
        Returns the details of a single defendant identified by their
        appearance-scoped ID within a specific hearing and case. Returns 404 if
        the hearing does not exist or if no defendant with the given ID exists
        on the case.
      operationId: getDefendant
      tags:
        - hearings
      parameters:
        - in: path
          name: hearingId
          required: true
          description: Unique identifier of the hearing
          schema:
            type: string
            format: uuid
          example: "f1d2c3b4-a5e6-4f7a-8b9c-0d1e2f3a4b5c"
        - in: path
          name: caseURN
          required: true
          description: Unique case reference identifying the case
          schema:
            type: string
          example: "ABCD1234567"
        - in: path
          name: defendantId
          required: true
          description: Unique identifier of the defendant for this appearance
          schema:
            type: string
            format: uuid
          example: "30b83084-d2fe-4a70-bbd1-fae1dfdb4b95"
      responses:
        '200':
          description: Defendant found
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/DefendantView"
              examples:
                defendant:
                  $ref: "./examples/defendant.yaml"
        '400':
          $ref: "#/components/responses/BadRequest"
        '401':
          $ref: "#/components/responses/Unauthorized"
        '403':
          $ref: "#/components/responses/Forbidden"
        '404':
          $ref: "#/components/responses/NotFound"
        '500':
          $ref: "#/components/responses/InternalServerError"
```

- [ ] **Step 2: Create the example file**

Create `src/main/resources/openapi/examples/defendant.yaml`:

```yaml
summary: Single defendant with offences
value:
  id: "30b83084-d2fe-4a70-bbd1-fae1dfdb4b95"
  masterDefendantId: "a1f2e3d4-c5b6-4789-9abc-1d2e3f4a5b6c"
  name: "John Doe"
  dateOfBirth: "1980-01-31"
  offences:
    - id: "c4a1b2d3-e5f6-4789-9abc-0d1e2f3a4b5c"
      code: "TH68001"
      title: "Theft from a shop"
      status: "Convicted"
```

- [ ] **Step 3: Lint the spec**

```bash
cd /Users/srivanimuddineni/HMCTS/APIM/api-cp-crime-hearing
spectral lint "src/main/resources/openapi/openapi-spec.yml"
```

Expected: no errors. Fix any issues before proceeding.

- [ ] **Step 4: Regenerate the Java interfaces**

```bash
./gradlew openApiGenerate
```

Expected: BUILD SUCCESSFUL. Verify the generated interface now contains `getDefendant`:

```bash
grep -n "getDefendant" build/generated/src/main/java/uk/gov/hmcts/cp/openapi/api/HearingsApi.java
```

Expected: one or more lines containing `getDefendant`.

- [ ] **Step 5: Run the existing api-cp tests**

```bash
./gradlew test
```

Expected: BUILD SUCCESSFUL, all existing `OpenApiObjectsTest` tests pass.

- [ ] **Step 6: Publish to local Maven repository**

```bash
./gradlew publishToMavenLocal
```

Expected: BUILD SUCCESSFUL. Verify:

```bash
ls ~/.m2/repository/uk/gov/hmcts/cp/api-cp-crime-hearing/0.0.999/
```

Expected: `api-cp-crime-hearing-0.0.999.jar` and `api-cp-crime-hearing-0.0.999.pom` present.

- [ ] **Step 7: Commit**

```bash
cd /Users/srivanimuddineni/HMCTS/APIM/api-cp-crime-hearing
git add src/main/resources/openapi/openapi-spec.yml \
        src/main/resources/openapi/examples/defendant.yaml
git commit -m "$(cat <<'EOF'
feat(hearing): add GET single defendant endpoint (AMP-795)

Adds GET /hearings/{hearingId}/cases/{caseURN}/defendants/{defendantId}
to retrieve a single defendant by their appearance-scoped ID.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: DefendantMapper — Add mapToDefendantView (TDD)

**Files:**
- Modify: `build.gradle` (service-cp-crime-hearing) — point to local spec build
- Modify: `src/test/java/uk/gov/hmcts/cp/mappers/DefendantMapperTest.java`
- Modify: `src/main/java/uk/gov/hmcts/cp/mappers/DefendantMapper.java`

**Interfaces:**
- Consumes: `uk.gov.hmcts.cp:api-cp-crime-hearing:0.0.999` from MavenLocal
- Produces: `DefendantMapper.mapToDefendantView(DefendantEntry entry) → DefendantView` (public method)

- [ ] **Step 1: Point the service at the local spec build**

In `service-cp-crime-hearing/build.gradle`, change:

```groovy
  implementation('uk.gov.hmcts.cp:api-cp-crime-hearing:1.0.1')
```

to:

```groovy
  implementation('uk.gov.hmcts.cp:api-cp-crime-hearing:0.0.999')
```

- [ ] **Step 2: Write the failing test**

In `src/test/java/uk/gov/hmcts/cp/mappers/DefendantMapperTest.java`, add this test after the last existing test method:

```java
@Test
void mapToDefendantView_should_mapSingleEntry() {
    DefendantEntry entry = DefendantEntry.builder()
            .id(DEFENDANT_ID)
            .masterDefendantId(MASTER_DEFENDANT_ID)
            .personDefendant(PersonDefendant.builder()
                    .personDetails(PersonDetails.builder().firstName("John").lastName("Doe").build())
                    .build())
            .offences(List.of(OffenceEntry.builder()
                    .id(OFFENCE_ID)
                    .offenceCode("TH68001")
                    .offenceTitle("Theft from a shop")
                    .plea(PleaEntry.builder().pleaValue("GUILTY").build())
                    .build()))
            .build();

    DefendantView view = mapper.mapToDefendantView(entry);

    assertThat(view.getId()).isEqualTo(DEFENDANT_ID);
    assertThat(view.getMasterDefendantId()).isEqualTo(MASTER_DEFENDANT_ID);
    assertThat(view.getName()).isEqualTo("John Doe");
    assertThat(view.getOffences()).hasSize(1);
    assertThat(view.getOffences().get(0).getCode()).isEqualTo("TH68001");
    assertThat(view.getOffences().get(0).getStatus()).isEqualTo("GUILTY");
}
```

- [ ] **Step 3: Run to confirm it fails**

```bash
cd /Users/srivanimuddineni/HMCTS/APIM/service-cp-crime-hearing
./gradlew test --tests 'uk.gov.hmcts.cp.mappers.DefendantMapperTest.mapToDefendantView_should_mapSingleEntry'
```

Expected: FAIL — compilation error: `cannot find symbol: method mapToDefendantView(DefendantEntry)`.

- [ ] **Step 4: Add mapToDefendantView to DefendantMapper**

Replace the full contents of `src/main/java/uk/gov/hmcts/cp/mappers/DefendantMapper.java`:

```java
package uk.gov.hmcts.cp.mappers;

import org.springframework.stereotype.Component;
import uk.gov.hmcts.cp.domain.HearingResponse.DefendantEntry;
import uk.gov.hmcts.cp.domain.HearingResponse.OffenceEntry;
import uk.gov.hmcts.cp.domain.HearingResponse.PersonDefendant;
import uk.gov.hmcts.cp.domain.HearingResponse.PleaEntry;
import uk.gov.hmcts.cp.openapi.model.DefendantView;
import uk.gov.hmcts.cp.openapi.model.OffenceView;

import java.util.Collections;
import java.util.List;
import java.util.Optional;

@Component
public class DefendantMapper {

    private static final String DEFAULT_OFFENCE_STATUS = "Awaiting plea";

    public List<DefendantView> mapToDefendantViews(final List<DefendantEntry> entries) {
        return Optional.ofNullable(entries)
                .orElse(Collections.emptyList())
                .stream()
                .map(this::toDefendantView)
                .toList();
    }

    public DefendantView mapToDefendantView(final DefendantEntry entry) {
        return toDefendantView(entry);
    }

    private DefendantView toDefendantView(final DefendantEntry entry) {
        return DefendantView.builder()
                .id(entry.getId())
                .masterDefendantId(entry.getMasterDefendantId())
                .name(toName(entry.getPersonDefendant()))
                .offences(toOffenceViews(entry.getOffences()))
                .build();
    }

    private String toName(final PersonDefendant personDefendant) {
        return Optional.ofNullable(personDefendant)
                .map(PersonDefendant::getPersonDetails)
                .map(details -> (details.getFirstName() + " " + details.getLastName()).strip())
                .orElse(null);
    }

    private List<OffenceView> toOffenceViews(final List<OffenceEntry> offences) {
        return Optional.ofNullable(offences)
                .orElse(Collections.emptyList())
                .stream()
                .map(this::toOffenceView)
                .toList();
    }

    private OffenceView toOffenceView(final OffenceEntry offence) {
        return OffenceView.builder()
                .id(offence.getId())
                .code(offence.getOffenceCode())
                .title(offence.getOffenceTitle())
                .status(toStatus(offence.getPlea()))
                .build();
    }

    private String toStatus(final PleaEntry plea) {
        final String pleaValue = Optional.ofNullable(plea).map(PleaEntry::getPleaValue).orElse(null);
        return (pleaValue == null || pleaValue.isBlank()) ? DEFAULT_OFFENCE_STATUS : pleaValue;
    }
}
```

- [ ] **Step 5: Run all mapper tests**

```bash
./gradlew test --tests 'uk.gov.hmcts.cp.mappers.DefendantMapperTest'
```

Expected: BUILD SUCCESSFUL — all existing tests and the new test pass.

---

## Task 4: HearingService — Extract Helper and Add getDefendant (TDD)

**Files:**
- Modify: `src/test/java/uk/gov/hmcts/cp/services/HearingServiceTest.java`
- Modify: `src/main/java/uk/gov/hmcts/cp/services/HearingService.java`

**Interfaces:**
- Consumes: `DefendantMapper.mapToDefendantView(DefendantEntry)` (Task 3), `HearingClient.getHearing(UUID)` (existing)
- Produces: `HearingService.getDefendant(UUID hearingId, String caseURN, UUID defendantId) → DefendantView`; throws `ResponseStatusException(NOT_FOUND)` when no defendant matches `defendantId`

- [ ] **Step 1: Add two failing tests to HearingServiceTest**

At the top of `HearingServiceTest`, add to the import block (if not already present):

```java
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;
```

Then add these two tests after the last existing `getDefendants_*` test:

```java
@Test
void getDefendant_should_returnMappedView_whenDefendantFound() {
    DefendantEntry matchingDefendant = DefendantEntry.builder()
            .id(DEFENDANT_ID_1)
            .masterDefendantId(MASTER_DEFENDANT_ID_1)
            .build();
    HearingResponse hearingResponse = HearingResponse.builder()
            .hearing(HearingDetail.builder()
                    .prosecutionCases(List.of(
                            ProsecutionCase.builder()
                                    .prosecutionCaseIdentifier(ProsecutionCaseIdentifier.builder().caseURN(CASE_URN_A).build())
                                    .defendants(List.of(matchingDefendant))
                                    .build()
                    ))
                    .build())
            .build();
    DefendantView expectedView = DefendantView.builder().id(DEFENDANT_ID_1).build();
    when(hearingClient.getHearing(hearingId)).thenReturn(hearingResponse);
    when(defendantMapper.mapToDefendantView(matchingDefendant)).thenReturn(expectedView);

    DefendantView result = hearingService.getDefendant(hearingId, CASE_URN_A, DEFENDANT_ID_1);

    assertThat(result).isEqualTo(expectedView);
}

@Test
void getDefendant_should_throw404_whenDefendantIdNotFound() {
    HearingResponse hearingResponse = HearingResponse.builder()
            .hearing(HearingDetail.builder()
                    .prosecutionCases(List.of(
                            ProsecutionCase.builder()
                                    .prosecutionCaseIdentifier(ProsecutionCaseIdentifier.builder().caseURN(CASE_URN_A).build())
                                    .defendants(List.of(
                                            DefendantEntry.builder().id(DEFENDANT_ID_2).masterDefendantId(MASTER_DEFENDANT_ID_2).build()
                                    ))
                                    .build()
                    ))
                    .build())
            .build();
    when(hearingClient.getHearing(hearingId)).thenReturn(hearingResponse);

    ResponseStatusException ex = assertThrows(ResponseStatusException.class,
            () -> hearingService.getDefendant(hearingId, CASE_URN_A, DEFENDANT_ID_1));

    assertThat(ex.getStatusCode()).isEqualTo(HttpStatus.NOT_FOUND);
}
```

- [ ] **Step 2: Run to confirm they fail**

```bash
./gradlew test --tests 'uk.gov.hmcts.cp.services.HearingServiceTest.getDefendant_should_returnMappedView_whenDefendantFound'
```

Expected: FAIL — compilation error: `cannot find symbol: method getDefendant`.

- [ ] **Step 3: Replace HearingService.java with the refactored version**

Replace the full contents of `src/main/java/uk/gov/hmcts/cp/services/HearingService.java`:

```java
package uk.gov.hmcts.cp.services;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;
import uk.gov.hmcts.cp.clients.HearingClient;
import uk.gov.hmcts.cp.domain.HearingResponse;
import uk.gov.hmcts.cp.domain.HearingTimelineResponse;
import uk.gov.hmcts.cp.mappers.DefendantAttendanceMapper;
import uk.gov.hmcts.cp.mappers.DefendantMapper;
import uk.gov.hmcts.cp.mappers.HearingMapper;
import uk.gov.hmcts.cp.openapi.model.DefendantAttendanceView;
import uk.gov.hmcts.cp.openapi.model.DefendantView;
import uk.gov.hmcts.cp.openapi.model.HearingTimelineView;

import java.util.Collections;
import java.util.List;
import java.util.Objects;
import java.util.Optional;
import java.util.UUID;

@Service
@RequiredArgsConstructor
@Slf4j
public class HearingService {

    private final CaseUrnMapperService caseUrnMapperService;
    private final HearingClient hearingClient;
    private final HearingMapper hearingMapper;
    private final DefendantAttendanceMapper defendantAttendanceMapper;
    private final DefendantMapper defendantMapper;

    public HearingTimelineView getCaseTimeline(final String caseUrn) {
        final UUID caseId = caseUrnMapperService.getCaseId(caseUrn);
        final HearingTimelineResponse timelineResponse = hearingClient.getTimeline(caseId);
        return hearingMapper.mapToHearingTimelineView(timelineResponse);
    }

    public DefendantAttendanceView getDefendantAttendance(final UUID hearingId) {
        final HearingResponse hearingResponse = hearingClient.getHearing(hearingId);
        return defendantAttendanceMapper.mapToDefendantAttendanceView(hearingId, hearingResponse);
    }

    public List<DefendantView> getDefendants(final UUID hearingId, final String caseURN, final UUID masterDefendantId) {
        final List<HearingResponse.DefendantEntry> defendants = findDefendantsForCase(hearingId, caseURN).stream()
                .filter(d -> masterDefendantId == null || masterDefendantId.equals(d.getMasterDefendantId()))
                .toList();
        return defendantMapper.mapToDefendantViews(defendants);
    }

    public DefendantView getDefendant(final UUID hearingId, final String caseURN, final UUID defendantId) {
        return findDefendantsForCase(hearingId, caseURN).stream()
                .filter(d -> defendantId.equals(d.getId()))
                .findFirst()
                .map(defendantMapper::mapToDefendantView)
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND,
                        "No defendant found for the supplied defendantId"));
    }

    private List<HearingResponse.DefendantEntry> findDefendantsForCase(final UUID hearingId, final String caseURN) {
        final HearingResponse hearingResponse = hearingClient.getHearing(hearingId);
        final List<HearingResponse.ProsecutionCase> prosecutionCases = Optional.ofNullable(hearingResponse)
                .map(HearingResponse::getHearing)
                .map(HearingResponse.HearingDetail::getProsecutionCases)
                .orElse(Collections.emptyList());
        return prosecutionCases.stream()
                .filter(pc -> matchesCaseUrn(pc, caseURN))
                .flatMap(pc -> Optional.ofNullable(pc.getDefendants()).orElse(Collections.emptyList()).stream())
                .toList();
    }

    private boolean matchesCaseUrn(final HearingResponse.ProsecutionCase prosecutionCase, final String caseUrn) {
        return Optional.ofNullable(prosecutionCase.getProsecutionCaseIdentifier())
                .map(HearingResponse.ProsecutionCaseIdentifier::getCaseURN)
                .map(urn -> Objects.equals(urn, caseUrn))
                .orElse(false);
    }
}
```

- [ ] **Step 4: Run all service tests**

```bash
./gradlew test --tests 'uk.gov.hmcts.cp.services.HearingServiceTest'
```

Expected: BUILD SUCCESSFUL — all existing `getDefendants_*` tests still pass, plus the two new `getDefendant_*` tests.

---

## Task 5: HearingController — Implement getDefendant (TDD)

**Files:**
- Modify: `src/test/java/uk/gov/hmcts/cp/controllers/HearingControllerTest.java`
- Modify: `src/main/java/uk/gov/hmcts/cp/controllers/HearingController.java`

**Interfaces:**
- Consumes: `HearingService.getDefendant(UUID, String, UUID) → DefendantView` (Task 4)
- Produces: `HearingController.getDefendant(UUID, String, UUID)` implementing the `HearingsApi` generated interface

- [ ] **Step 1: Write the failing tests**

In `src/test/java/uk/gov/hmcts/cp/controllers/HearingControllerTest.java`, add these two tests after the last existing test:

```java
@Test
void getDefendant_should_returnOk_withDefendantView() {
    DefendantView expectedView = DefendantView.builder().id(DEFENDANT_ID).masterDefendantId(MASTER_DEFENDANT_ID).build();
    when(hearingService.getDefendant(HEARING_ID, CASE_URN, DEFENDANT_ID)).thenReturn(expectedView);

    ResponseEntity<DefendantView> response = hearingController.getDefendant(HEARING_ID, CASE_URN, DEFENDANT_ID);

    assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
    assertThat(response.getBody()).isEqualTo(expectedView);
}

@Test
void getDefendant_should_rejectCaseUrn_whenNotAlphanumeric() {
    assertThrows(ResponseStatusException.class,
            () -> hearingController.getDefendant(HEARING_ID, "<script>alert('xss')</script>", DEFENDANT_ID));
}
```

- [ ] **Step 2: Run to confirm they fail**

```bash
./gradlew test --tests 'uk.gov.hmcts.cp.controllers.HearingControllerTest.getDefendant_should_returnOk_withDefendantView'
```

Expected: FAIL — `HearingController` does not implement `getDefendant`.

- [ ] **Step 3: Replace HearingController.java with the complete implementation**

Replace the full contents of `src/main/java/uk/gov/hmcts/cp/controllers/HearingController.java`:

```java
package uk.gov.hmcts.cp.controllers;

import lombok.NonNull;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.owasp.encoder.Encode;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import uk.gov.hmcts.cp.openapi.api.HearingsApi;
import uk.gov.hmcts.cp.openapi.model.DefendantAttendanceView;
import uk.gov.hmcts.cp.openapi.model.DefendantView;
import uk.gov.hmcts.cp.openapi.model.HearingTimelineView;
import uk.gov.hmcts.cp.services.HearingService;

import java.util.List;
import java.util.UUID;

@RestController
@RequiredArgsConstructor
@Slf4j
public class HearingController implements HearingsApi {

    private static final String CASE_URN_REGEX = "^[0-9a-zA-Z]{1,30}$";

    private final HearingService hearingService;

    @Override
    @NonNull
    public ResponseEntity<HearingTimelineView> getCaseTimeline(final String caseURN) {
        log.info("Received request to get case timeline for caseURN:{}", Encode.forJava(caseURN));
        final HearingTimelineView timelineView = hearingService.getCaseTimeline(validateCaseUrn(caseURN));
        return ResponseEntity.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .body(timelineView);
    }

    @Override
    @NonNull
    public ResponseEntity<DefendantAttendanceView> getDefendantAttendance(final UUID hearingId) {
        log.info("Received request to get defendant attendance for hearingId:{}", Encode.forJava(String.valueOf(hearingId)));
        final DefendantAttendanceView attendanceView = hearingService.getDefendantAttendance(hearingId);
        return ResponseEntity.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .body(attendanceView);
    }

    @Override
    @NonNull
    public ResponseEntity<List<DefendantView>> getDefendants(final UUID hearingId, final String caseURN, final UUID masterDefendantId) {
        log.info("Received request to get defendants for hearingId:{} caseURN:{}",
                Encode.forJava(String.valueOf(hearingId)), Encode.forJava(caseURN));
        final List<DefendantView> defendants = hearingService.getDefendants(hearingId, validateCaseUrn(caseURN), masterDefendantId);
        return ResponseEntity.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .body(defendants);
    }

    @Override
    @NonNull
    public ResponseEntity<DefendantView> getDefendant(final UUID hearingId, final String caseURN, final UUID defendantId) {
        log.info("Received request to get defendant for hearingId:{} caseURN:{} defendantId:{}",
                Encode.forJava(String.valueOf(hearingId)), Encode.forJava(caseURN), Encode.forJava(String.valueOf(defendantId)));
        final DefendantView defendant = hearingService.getDefendant(hearingId, validateCaseUrn(caseURN), defendantId);
        return ResponseEntity.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .body(defendant);
    }

    private String validateCaseUrn(final String caseUrn) {
        if (caseUrn == null || !caseUrn.matches(CASE_URN_REGEX)) {
            log.warn("CaseUrn {} does not match expected caseRegex:{}", Encode.forJava(caseUrn), CASE_URN_REGEX);
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Case urn must be between 1 and 30 alphanumerics");
        }
        return caseUrn;
    }
}
```

- [ ] **Step 4: Run all controller tests**

```bash
./gradlew test --tests 'uk.gov.hmcts.cp.controllers.HearingControllerTest'
```

Expected: BUILD SUCCESSFUL — all existing tests pass, plus the two new `getDefendant_*` tests.

---

## Task 6: Integration Tests and Full Build

**Files:**
- Modify: `src/test/java/uk/gov/hmcts/cp/integration/HearingControllerIntegrationTest.java`

**Interfaces:**
- Consumes: the full stack from Tasks 3–5 via MockMvc

- [ ] **Step 1: Add the three integration tests**

In `src/test/java/uk/gov/hmcts/cp/integration/HearingControllerIntegrationTest.java`, add these tests after the last existing test:

```java
@Test
void getDefendant_should_returnOk_withDefendantFields() throws Exception {
    stubGetHearing(HEARING_ID, HTTP_OK, """
            {"hearing":{"id":"%s","prosecutionCases":[{"prosecutionCaseIdentifier":{"caseURN":"%s"},"defendants":[
                {"id":"%s","masterDefendantId":"%s","personDefendant":{"personDetails":{"firstName":"John","lastName":"Doe"}},"offences":[{"id":"%s","offenceCode":"TH68001","offenceTitle":"Theft from a shop","plea":{"pleaValue":"GUILTY"}}]}
            ]}]}}
            """.formatted(HEARING_ID, CASE_URN, DEFENDANT_ID, MASTER_DEFENDANT_ID, OFFENCE_ID));

    mockMvc.perform(get("/hearings/{hearingId}/cases/{caseURN}/defendants/{defendantId}",
                    HEARING_ID, CASE_URN, DEFENDANT_ID)
                    .accept(MediaType.APPLICATION_JSON))
            .andDo(print())
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value(DEFENDANT_ID.toString()))
            .andExpect(jsonPath("$.masterDefendantId").value(MASTER_DEFENDANT_ID.toString()))
            .andExpect(jsonPath("$.name").value("John Doe"))
            .andExpect(jsonPath("$.offences[0].code").value("TH68001"))
            .andExpect(jsonPath("$.offences[0].status").value("GUILTY"));
}

@Test
void getDefendant_should_return404_whenDefendantIdNotFound() throws Exception {
    stubGetHearing(HEARING_ID, HTTP_OK, """
            {"hearing":{"id":"%s","prosecutionCases":[{"prosecutionCaseIdentifier":{"caseURN":"%s"},"defendants":[
                {"id":"%s","masterDefendantId":"%s"}
            ]}]}}
            """.formatted(HEARING_ID, CASE_URN, DEFENDANT_ID_2, OTHER_MASTER_DEFENDANT_ID));

    mockMvc.perform(get("/hearings/{hearingId}/cases/{caseURN}/defendants/{defendantId}",
                    HEARING_ID, CASE_URN, DEFENDANT_ID)
                    .accept(MediaType.APPLICATION_JSON))
            .andDo(print())
            .andExpect(status().isNotFound());
}

@Test
void getDefendant_should_return404_whenHearingDoesNotExist() throws Exception {
    stubGetHearingNotFound(HEARING_ID);

    mockMvc.perform(get("/hearings/{hearingId}/cases/{caseURN}/defendants/{defendantId}",
                    HEARING_ID, CASE_URN, DEFENDANT_ID)
                    .accept(MediaType.APPLICATION_JSON))
            .andDo(print())
            .andExpect(status().isNotFound());
}
```

- [ ] **Step 2: Run the integration tests in isolation first**

```bash
./gradlew test --tests 'uk.gov.hmcts.cp.integration.HearingControllerIntegrationTest.getDefendant_should_returnOk_withDefendantFields'
```

Expected: PASS (all layers from Tasks 3–5 are in place).

- [ ] **Step 3: Full build**

```bash
./gradlew build -x apiTest
```

Expected: BUILD SUCCESSFUL. All unit tests, integration tests, and PMD checks pass.

- [ ] **Step 4: Commit**

```bash
cd /Users/srivanimuddineni/HMCTS/APIM/service-cp-crime-hearing
git add build.gradle \
        src/main/java/uk/gov/hmcts/cp/mappers/DefendantMapper.java \
        src/main/java/uk/gov/hmcts/cp/services/HearingService.java \
        src/main/java/uk/gov/hmcts/cp/controllers/HearingController.java \
        src/test/java/uk/gov/hmcts/cp/mappers/DefendantMapperTest.java \
        src/test/java/uk/gov/hmcts/cp/services/HearingServiceTest.java \
        src/test/java/uk/gov/hmcts/cp/controllers/HearingControllerTest.java \
        src/test/java/uk/gov/hmcts/cp/integration/HearingControllerIntegrationTest.java
git commit -m "$(cat <<'EOF'
feat(hearing): implement GET single defendant endpoint (AMP-795)

Adds getDefendant to controller, service, and mapper.
Extracts findDefendantsForCase helper shared with getDefendants.
Covers AC1 (200), AC2 (defendant 404), AC3 (hearing 404).

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Open PRs on Both Repos

- [ ] **Step 1: Push api-cp branch and open PR**

```bash
cd /Users/srivanimuddineni/HMCTS/APIM/api-cp-crime-hearing
git push -u origin dev/AMP-795
gh pr create \
  --title "feat(hearing): add GET single defendant endpoint (AMP-795)" \
  --body "$(cat <<'EOF'
## Summary

- Adds new path to openapi-spec.yml for single defendant lookup
- Reuses existing DefendantView schema — no new types
- Adds examples/defendant.yaml for the 200 response

## Test plan

- [ ] Spectral lint passes
- [ ] ./gradlew test passes
- [ ] Generated HearingsApi contains getDefendant method

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 2: Push service branch and open PR**

```bash
cd /Users/srivanimuddineni/HMCTS/APIM/service-cp-crime-hearing
git push -u origin dev/AMP-795
gh pr create \
  --title "feat(hearing): implement GET single defendant endpoint (AMP-795)" \
  --body "$(cat <<'EOF'
## Summary

- Implements getDefendant on controller, service, and mapper
- Extracts findDefendantsForCase private helper shared with getDefendants
- Adds mapToDefendantView public method to DefendantMapper
- Integration tests cover AC1 (200), AC2 (defendant 404), AC3 (hearing 404)

## Test plan

- [ ] ./gradlew build -x apiTest passes
- [ ] All unit and integration tests pass

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 3: Note PR URLs**

The api-cp PR must be merged and released **before** the service PR is merged (service depends on the published spec artifact).

---

## Task 8: Merge and Release api-cp-crime-hearing → Catalog Publish

- [ ] **Step 1: Merge the api-cp PR once CI is green**

```bash
cd /Users/srivanimuddineni/HMCTS/APIM/api-cp-crime-hearing
gh pr merge --squash --delete-branch
git checkout main && git pull origin main
```

- [ ] **Step 2: Cut the release using the release skill**

In the api-cp-crime-hearing repo context, invoke:

```
/release
```

The skill determines the next version (new endpoint = minor bump → `1.1.0`), creates the GitHub Release with changelog, and triggers the `publish-api-docs.yml` → `publish-swagger-ui.yml@v1` chain which publishes to GitHub Packages / Azure Artifacts.

Verify the release was created:

```bash
gh release list --repo hmcts/api-cp-crime-hearing --limit 3
```

Expected: `v1.1.0` at the top.

- [ ] **Step 3: Verify catalog PR was raised (automatic)**

The `publish-swagger-ui.yml@v1` workflow triggers the catalog publisher. Check:

```bash
gh pr list --repo hmcts/amp-catalog --limit 5
```

Expected: a PR adding/updating the `api-cp-crime-hearing` entry.

---

## Task 9: Update Service Dependency, Merge, Release

> Perform this after `api-cp-crime-hearing:1.1.0` is confirmed published.

- [ ] **Step 1: Update the service dependency to the released version**

In `service-cp-crime-hearing/build.gradle`, change:

```groovy
  implementation('uk.gov.hmcts.cp:api-cp-crime-hearing:0.0.999')
```

to:

```groovy
  implementation('uk.gov.hmcts.cp:api-cp-crime-hearing:1.1.0')
```

- [ ] **Step 2: Verify the build resolves the released artifact**

```bash
cd /Users/srivanimuddineni/HMCTS/APIM/service-cp-crime-hearing
./gradlew build -x apiTest
```

Expected: BUILD SUCCESSFUL, resolving `1.1.0` from GitHub Packages / Azure Artifacts.

- [ ] **Step 3: Commit the dependency bump and push**

```bash
git add build.gradle
git commit -m "$(cat <<'EOF'
chore(deps): update api-cp-crime-hearing to 1.1.0 (AMP-795)

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
git push
```

- [ ] **Step 4: Merge the service PR once CI is green**

```bash
gh pr merge --squash --delete-branch
git checkout main && git pull origin main
```

- [ ] **Step 5: Cut the service release**

In the service-cp-crime-hearing repo context, invoke:

```
/release
```

Expected: a new GitHub Release (e.g., `v1.1.0`) is created with changelog, and the SIT deployment pipeline is triggered.

---

## Self-Review

- **Spec coverage:** AC1 → Task 6 `getDefendant_should_returnOk_withDefendantFields`. AC2 → Task 6 `getDefendant_should_return404_whenDefendantIdNotFound`. AC3 → Task 6 `getDefendant_should_return404_whenHearingDoesNotExist`. Catalog publish → Task 8 Step 3. Service release → Task 9 Step 5.
- **No placeholders:** All code blocks are complete. Commands include expected output.
- **Type consistency:** `mapToDefendantView(DefendantEntry)` defined Task 3, consumed in Task 4 mock and Task 4 `HearingService`. `getDefendant(UUID, String, UUID) → DefendantView` defined Task 4, consumed in Task 5 mock and `HearingController`. `HearingsApi.getDefendant` generated Task 2, implemented Task 5.
- **Dependency order enforced:** Task 8 (api-cp release) explicitly blocks Task 9 (service PR merge).