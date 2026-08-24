---
name: add-audit-to-service
description: >
  Rolls out CPP endpoint auditing to a service-cp-* Spring Boot repo using the
  cp-audit-springboot-annotations starter: adds the dependency, the cp.audit.* properties
  and the Artemis autoconfiguration excludes, agrees a per-endpoint audit contract with the
  service owner, annotates every controller method with @AuditDetail or @AuditExclude, wires
  domain IDs (materialId, caseId, hearingId, courtDocumentId, clientId) into MDC, adds the
  payload contract tests, and raises the cp-vp-aks-deploy PRs that supply the per-environment
  Artemis broker hostnames. The starter BLOCKS every unannotated endpoint with a 403, so this
  is a breaking rollout that must be completed in one change, not left half-done. Invoke when
  asked to add audit / auditing / audit annotations / Artemis audit events to a service.
---

# Skill: Add Audit To A Service

## When to invoke

- A `service-cp-*` repo needs CPP endpoint auditing and has none today.
- An existing audited service is adding new endpoints and needs them classified (jump
  straight to Step 4 and Step 5).
- Invocation command: `/add-audit-to-service`

Exemplar: `hmcts/service-cp-crime-hearing-results-document-subscription` (hrds) on `main` —
the first service through this. Copy from it, do not re-derive.

## Background

`uk.gov.hmcts.cp:cp-audit-springboot-annotations` is a Spring Boot starter that publishes two
audit events per audited request (`REQUEST` before the handler, `RESPONSE` after) to the
ActiveMQ Artemis topic `jms.topic.auditing.event`, with the JMS property
`CPPNAME = audit.events.audit-recorded` for broker-side routing. The downstream consumer is
`audit2dls`.

Everything is wired by a single `@AutoConfiguration` — there is no component scanning and
nothing to `@Import`. The library owns the broker connection, the `JmsTemplate`, its own
`ObjectMapper`, and a servlet filter at `HIGHEST_PRECEDENCE + 10`.

> **This is a breaking rollout.** Any endpoint with neither `@AuditDetail` nor `@AuditExclude`
> returns **403**, as does an audited request with no resolvable `X-Correlation-Id`. A partial
> rollout takes endpoints offline. Do not merge Step 2 without Steps 3–5 in the same PR.

## Step 1 — Preflight

Confirm all four, in the target repo. Stop and report if any is missing — they are
prerequisites, not things this skill installs.

| Check | How | Why it matters |
|---|---|---|
| A tracing filter puts `X-Correlation-Id` in MDC | `grep -rn "X-Correlation-Id" src/main/java` — look for a filter at `Ordered.HIGHEST_PRECEDENCE` | Without it every client must send the header or get a 403 |
| The MDC key is literally `X-Correlation-Id` | Read the filter's constant | The library reads that exact key — a `correlationId` key is not found |
| Spring Boot major version | `grep -rn "springBootVersion\|org.springframework.boot" build.gradle gradle/*.gradle` | Decides the autoconfigure-exclude class names in Step 3 |
| Every controller is enumerable | `grep -rln "@RestController" src/main/java` | Step 4 needs the complete endpoint list; a missed controller is a 403 in production |

Also list the caller-identity source: the library reads the audited user from the inbound
`CJSCPPUID` header (case-insensitive), falling back to MDC key `cp.audit.user-id`. If the
service resolves the caller itself (e.g. a JWT claim), plan to set that MDC key in Step 6.

## Step 2 — Add the dependency

In `build.gradle`, in the `dependencies` block (never in an `apply from` file — Dependabot
does not track those):

```gradle
  // Audit
  implementation('uk.gov.hmcts.cp:cp-audit-springboot-annotations:2.0.0')
```

Check for a newer version before pinning:

```bash
gh api repos/hmcts/cp-audit-springboot-annotations/releases/latest --jq .tag_name
```

Do **not** add `spring-boot-starter-artemis` here. The library declares it as
`implementation`, so it is on your runtime classpath already. You only need it explicitly if
you also add the optional connectivity checker in Step 10.

## Step 3 — Configuration

`src/main/resources/application.yaml` — add the `cp.audit` block, going through env-var
placeholders so the Helm values file in Step 9 stays readable:

```yaml
cp:
  audit:
    enabled: ${AUDIT_ENABLED:true}
    block-on-failure: ${AUDIT_BLOCK_ON_FAILURE:false}
    hosts:
      - ${ARTEMIS_HOST_PRIMARY:localhost}
      - ${ARTEMIS_HOST_SECONDARY:localhost}
```

| Property | Library default | Set it to | Why |
|---|---|---|---|
| `cp.audit.enabled` | `true` | `${AUDIT_ENABLED:true}` | Lets an environment kill auditing without a redeploy of code. A `WARN` is logged at startup when disabled |
| `cp.audit.block-on-failure` | **`true`** | `${AUDIT_BLOCK_ON_FAILURE:false}` | The library default fails the request with a 403 when the broker is unreachable. Roll out non-blocking; only consider `true` once the broker has proven stable in that environment |
| `cp.audit.hosts` | *(required)* | two env placeholders | Startup **throws** if unset. Two hosts turns on Artemis HA failover automatically; one host is single-broker |

Port, credentials, SSL, retries and timeouts are hard-coded in the library and are not
configurable — do not add properties for them.

Two more entries in the same file:

```yaml
spring:
  autoconfigure:
    exclude:
      - org.springframework.boot.jms.autoconfigure.JmsAutoConfiguration
      - org.springframework.boot.artemis.autoconfigure.ArtemisAutoConfiguration

management:
  health:
    jms:
      enabled: false
```

The excludes stop Spring Boot's own JMS autoconfiguration from colliding with the library's
`auditConnectionFactory` bean. **The class names above are the Spring Boot 4 packages** (as
used by hrds). On Spring Boot 3 they are `org.springframework.boot.autoconfigure.jms.JmsAutoConfiguration`
and `org.springframework.boot.autoconfigure.jms.artemis.ArtemisAutoConfiguration` — verify
against the version found in Step 1 rather than copying blind; a wrong exclude name is
silently ignored and the bean clash appears at startup.

The JMS health indicator is disabled because it probes the audit connection factory and can
fail readiness on a broker blip, taking healthy pods out of service for a non-critical path.

## Step 4 — Agree the audit contract (HUMAN GATE — do not skip)

This is the part that cannot be inferred from code. Build the table below from the full
controller inventory and get explicit sign-off from the **service owner** before annotating
anything. Auditing the wrong things is a data-protection problem; auditing nothing is a
compliance problem.

```
| Endpoint | Audit? | eventName | action | pathParams | Domain IDs to emit |
|---|---|---|---|---|---|
| GET /client-subscriptions/{id} | yes | hrds.get-client-subscription | View | clientSubscriptionId | — |
| POST /notifications            | no (machine-to-machine ingest) | — | — | — | — |
```

Fill in one row per handler method, then agree:

1. **`origin`** — one value for the whole service, e.g. `hearing-results-document`. **The
   annotation's default is `"hearing-results-document"`, which is hrds's value.** Any other
   service that omits `origin` files its audit records under hrds. Set it explicitly on
   every `@AuditDetail`.
2. **`component`** — the default is `QUERY_API`. Agree whether write endpoints should be
   `COMMAND_API` for this service, and be consistent.
3. **`eventName`** — `<short-service-prefix>.<kebab-operation>`, e.g.
   `hrds.create-client-subscription`. Stable forever once consumed downstream: renaming one
   breaks whoever queries it.
4. **`action`** — the default is `View`. hrds uses `Create` / `Update` / `Delete` / `View`,
   with `Download` for document retrieval.
5. **Which endpoints are excluded, and the stated reason.** hrds excludes the
   machine-to-machine notification ingest, the document/hearing-event fetches, the `/` health
   route, and the dev-only mock callback controller. "Excluded" needs a reason in the PR
   description, not just an annotation.
6. **Which domain IDs each audited endpoint should emit** — see Step 6. This is the "useful
   backend ids" decision: `materialId`, `caseId`, `hearingId`, `courtDocumentId` are the
   supported fields, and an endpoint that could emit one and does not is a gap in the audit
   trail.

Report the agreed table back before continuing.

## Step 5 — Annotate every endpoint

`@AuditDetail` and `@AuditExclude` both work on a method **or** a class. Method beats class.
Because `eventName` is per-operation, class level is only useful for `@AuditExclude`.

```java
@Override
@AuditDetail(
        origin = "hearing-results-document",
        eventName = "hrds.get-client-subscription",
        action = "View",
        pathParams = {"clientSubscriptionId"})
public ResponseEntity<ClientSubscription> getClientSubscription(final UUID clientSubscriptionId, ...) {
```

Whole controller excluded (health/root, dev-only mocks):

```java
@RestController
@AuditExclude
public class RootController {
```

`@AuditDetail` reference:

| Attribute | Default | Notes |
|---|---|---|
| `eventName` | *(required)* | Business event name, into `content.eventName` |
| `origin` | `"hearing-results-document"` | **Always set explicitly** — see Step 4.1 |
| `component` | `"QUERY_API"` | |
| `action` | `"View"` | |
| `pathParams` | `{}` | Path-variable names to extract into `content.pathParams`. Parsed as UUIDs |
| `expectedMdcFields` | `{}` | MDC keys that **must** be populated by the time the response event is built. Any missing one turns the response into a **403 after the handler already ran** — see Step 6 |

Decision table the filter applies per request:

| Condition | Outcome |
|---|---|
| `@AuditExclude` on method or class | Pass through, no audit |
| `@AuditDetail` + correlation id resolvable | Audit request + response |
| `@AuditDetail`, no correlation id in header or MDC, or not a UUID | **403** |
| Neither annotation | **403** |

Actuator endpoints are not Spring MVC handler methods, so the filter passes them through
untouched. Any `@RestController` route — including `/` used by Helm probes — is in scope and
must be annotated.

Verify nothing was missed before moving on:

```bash
grep -rn "@GetMapping\|@PostMapping\|@PutMapping\|@DeleteMapping\|@PatchMapping\|@RequestMapping" src/main/java --include="*.java" | wc -l
grep -rn "@AuditDetail\|@AuditExclude" src/main/java --include="*.java" | wc -l
```

Controllers implementing a generated `*Api` interface carry no mapping annotations of their
own — count `@Override` methods in those classes instead, and check the generated interface
for the route list.

## Step 6 — Wire domain IDs into MDC

The library reads domain IDs from MDC when it builds the **response** event, using the keys in
`uk.gov.hmcts.cp.audit.model.AuditMdcKeys`:

| Constant | MDC key | Emitted as |
|---|---|---|
| `USER_ID` | `cp.audit.user-id` | `_metadata.context.user` (fallback for the `CJSCPPUID` header) |
| `CLIENT_ID` | `clientId` | `content.clientId` |
| `MATERIAL_ID` | `cp.audit.material-id` | `content.materialId` |
| `CASE_ID` | `cp.audit.case-id` | `content.caseId` |
| `HEARING_ID` | `cp.audit.hearing-id` | `content.hearingId` |
| `COURT_DOCUMENT_ID` | `cp.audit.court-document-id` | `content.courtDocumentId` |

`clientId` is deliberately the plain key, not a `cp.audit.*` one — auth filters already put
the resolved calling client there for log correlation, and the audit message reuses that
entry. Set the rest from the service layer, once the ID is known:

```java
MDC.put(AuditMdcKeys.CASE_ID, caseId.toString());
```

All are parsed as UUIDs; absent or unparseable yields `null` rather than failing the request.

Enforce the ones the team agreed are mandatory with `expectedMdcFields`, but only where the
endpoint sets the field on **every** path:

```java
@AuditDetail(
        origin = "...", eventName = "...", action = "Download",
        pathParams = {"documentId"},
        expectedMdcFields = {"cp.audit.material-id"})
```

A missing expected field is logged and the response becomes a 403 *after* the handler has
run — side effects have already happened. Never list a field that an early-return or
not-found path skips.

### Filter ordering

The audit filter runs at `HIGHEST_PRECEDENCE + 10`. Any filter that populates MDC for audit
must sit between the tracing filter and it, and must not clear its MDC entry before the audit
filter regains control on the way out:

```
TracingFilter            HIGHEST_PRECEDENCE       puts X-Correlation-Id in MDC
<auth / client-id filter> HIGHEST_PRECEDENCE + 5  puts clientId in MDC
AuditFilter              HIGHEST_PRECEDENCE + 10  request event → chain → response event
```

Record the trade-off in the PR: with auth ahead of audit, requests rejected `401` produce no
audit event. hrds accepted that and logs those rejections instead. Putting audit first
instead means auditing unauthenticated traffic — that is the choice being made, so make it
deliberately.

## Step 7 — Test configuration

The starter throws at startup when `cp.audit.hosts` is unset, so every Spring context in the
test suite needs it. Add to the shared integration test base (or
`src/test/resources/application.properties`):

```java
@TestPropertySource(properties = {
        "cp.audit.enabled=false"
})
```

with `cp.audit.hosts=localhost` in test properties. Auditing stays **off** for the existing
suite — otherwise every test needs a correlation id and a broker — and audit tests opt back
in individually:

```java
@TestPropertySource(properties = "cp.audit.enabled=true")
class AuditFilterIntegrationTest extends IntegrationTestBase {
```

## Step 8 — Payload contract tests

Copy `src/test/java/uk/gov/hmcts/cp/audit/integration/AuditFilterIntegrationTest.java` and
`AuditJmsSenderIntegrationTest.java` from hrds and adapt. Minimum coverage:

- an excluded endpoint sends **no** event — `verify(auditSenderService, never()).send(any())`
- an audited endpoint sends **exactly two** — `times(2)`, `REQUEST` then `RESPONSE`
- both payloads asserted with `JSONAssert` in `JSONCompareMode.STRICT` against a literal
  expected JSON block
- the user is `null` when `CJSCPPUID` is absent, and populated when present
- with `block-on-failure=false`, a throwing sender still returns the real response
- the JMS property: `verify(mockMessage).setStringProperty("CPPNAME", "audit.events.audit-recorded")`

Two things that matter more than they look:

1. **Serialise with the production mapper**, not a locally-configured one:

   ```java
   private static final ObjectMapper MAPPER = new ArtemisAuditAutoConfiguration().auditObjectMapper();
   ```

   A local mapper with `WRITE_DATES_AS_TIMESTAMPS` disabled is what previously hid a
   numeric-timestamp bug that `audit2dls` rejected at runtime. `timestamp` must serialise as
   an ISO-8601 **string**.

2. **Freeze the clock** with `@MockitoBean(name = "auditClockService")` so the expected JSON
   can be a literal.

The consumer schema (`audit.events.audit-recorded.json`) requires `timestamp`, `origin` and
`content`; `content` is `additionalProperties: true`, so new `content` fields do not need a
schema change. `_metadata.name` must stay `audit.events.audit-recorded` — consumers dispatch
on it. The business event name lives in `content.eventName`.

Message shape produced per request:

```json
{
  "_metadata": { "id": "<uuid>", "name": "audit.events.audit-recorded",
                 "createdAt": "2026-01-01T10:00:00Z", "context": { "user": "<uuid|null>" } },
  "origin": "hearing-results-document",
  "component": "QUERY_API",
  "timestamp": "2026-01-01T10:00:00Z",
  "content": {
    "eventName": "hrds.get-client-subscription", "eventType": "REQUEST",
    "action": "View", "clientId": "<uuid|null>", "correlationId": "<uuid>",
    "responseStatus": null, "materialId": null, "caseId": null,
    "hearingId": null, "courtDocumentId": null,
    "pathParams": { "clientSubscriptionId": "<uuid>" }
  }
}
```

`responseStatus` is `null` on the `REQUEST` event and the HTTP status on the `RESPONSE` event.

## Step 9 — Supply the broker hostnames via Helm

The broker hostnames are **not** in the service repo. They live in
[`hmcts/cp-vp-aks-deploy`](https://github.com/hmcts/cp-vp-aks-deploy), one branch per
environment, in `vp-config/services/<service-name>/<env>.yml` under the `env:` map:

```yaml
env:
  ARTEMIS_HOST_PRIMARY: "DEVCCM01AAUBK01.dev.nl.cjscp.org.uk"
  ARTEMIS_HOST_SECONDARY: "DEVCCM01AAUBK02.dev.nl.cjscp.org.uk"
```

Only the two hostnames go here. `AUDIT_ENABLED` is deliberately absent — the
`${AUDIT_ENABLED:true}` default in Step 3 already turns auditing on, so setting it in the
values file is redundant noise. Add it only to switch auditing *off* in one environment.

One PR per environment branch — `env/dev`, `env/sit`, `env/prp`, `env/prd`. Roll out `dev`
first and confirm events arrive before touching the rest.

**Read the values from `origin/env/<env>`, not a local checkout.** These branches move
independently and local copies go stale by months; `git fetch --all` first, then
`git show origin/env/sit:vp-config/services/<service>/sit.yml`.

hrds precedent as of 2026-08-21 (`origin/env/dev`, `origin/env/sit`):

| Environment | Primary | Secondary |
|---|---|---|
| dev | `DEVCCM01AAUBK01.dev.nl.cjscp.org.uk` | `DEVCCM01AAUBK02.dev.nl.cjscp.org.uk` |
| sit | `SITCCM01AAUBK01.sit.nl.cjscp.org.uk` | `SITCCM01AAUBK02.sit.nl.cjscp.org.uk` |
| prp | *not yet wired* | *not yet wired* |
| prd | *not yet wired* | *not yet wired* |

Those two follow `<ENV>CCM01AAUBK0<1|2>.<env>.nl.cjscp.org.uk`. Use the pattern to *predict*
`prp`/`prd` and then **confirm the pair with the platform team before raising the PR** — the
stack segment (`CCM01`) and the broker count are per-environment facts, and production HA is
not guaranteed to be the same two-broker shape. A wrong hostname fails silently (see below),
so a prediction is a starting point, never the commit.

If the placeholders are left unset the service starts against `localhost`, every send fails,
and — with `block-on-failure=false` — you get an error log per request and no audit trail.
That is the failure mode to watch for after deploy.

The alternative to the env-var indirection in Step 3 is Spring's relaxed binding straight onto
the list (`CP_AUDIT_HOSTS_0`, `CP_AUDIT_HOSTS_1`). Both work; hrds uses the named
`ARTEMIS_HOST_*` form because it reads better in the values file. Pick one per service, not
both.

## Step 10 — Optional: hourly connectivity check

Diagnosing "no audit events" after a deploy is much faster with a scheduled reachability
probe. hrds has `uk.gov.hmcts.cp.artemis.ArtemisConnectivityChecker` — an `@Scheduled(cron =
"0 0 * * * *")` bean that opens a short-timeout TCP/SSL connection to each host on port 61616
and logs OK or FAILED per host. Copy it if the service has no other broker visibility.

This is the one case that needs the explicit dependency, because the checker compiles against
`ActiveMQConnectionFactory`:

```gradle
  // Artemis connectivity checker
  implementation 'org.springframework.boot:spring-boot-starter-artemis'
```

Note it reads `${cp.audit.hosts[0]}` and `${cp.audit.hosts[1]}` via `@Value` and so requires
exactly two hosts configured.

## Step 11 — Verify, then raise the PR

```bash
./gradlew clean build pmdMain
```

Then, before merge:

- [ ] Annotation count matches the endpoint count from Step 5
- [ ] The agreed contract table from Step 4 is in the PR description, with the exclusion reasons
- [ ] `origin` is set explicitly on every `@AuditDetail` and is **not** left as the hrds default
- [ ] `block-on-failure` resolves to `false` for the first rollout
- [ ] A local/dev smoke test of one audited and one excluded endpoint returns the real status, not 403
- [ ] The `cp-vp-aks-deploy` PR for `env/dev` is raised and linked from the service PR

Branch and commit per the repo conventions (`AMP-<n>` branch, no AI-attribution trailers).
The service PR and the `cp-vp-aks-deploy` PR must reference each other — merging the service
change without the values change deploys a service that cannot reach a broker.

## Rules

- Never merge the dependency without the annotations. Unannotated endpoints return 403.
- Never leave `origin` at its default in a service that is not hrds.
- Never guess an environment's Artemis hostnames.
- Never add `expectedMdcFields` for a field an endpoint sets only on its happy path.
- Never re-point `_metadata.name` away from `audit.events.audit-recorded`.
- Never assert audit payloads with a locally-built `ObjectMapper`.
- Never rename an `eventName` that is already flowing to `audit2dls` without agreeing it
  downstream first.
