---
name: test-stub-dsl
description: |
  How to author test doubles for external boundaries (HTTP providers, blob storage, message brokers) in
  CPP Modern-by-Default services as fluent, fixture-backed stub services layered over reusable
  container/emulator support. Use when writing or reviewing WireMock/Azurite/Service-Bus test support,
  boundary integration tests, or Cucumber step glue that drives a stubbed boundary. Consumed by the
  test-engineer and implementation agents (read by path) and invokable directly.
---

# Test stub DSL (CPP Modern by Default)

Boundary tests and BDD scenarios drive real external boundaries through test doubles. Keep two layers
strictly separate, and make the stub layer a **fluent, fixture-backed DSL** so tests read in domain
terms and never touch WireMock/SDK/JSON mechanics.

---

## 1. Two layers — never one class

**Layer A — container/emulator support (lifecycle only).** One class per backing technology (WireMock,
Azurite, Service Bus emulator, Postgres). It owns *only*: the JVM-wide singleton container/server, its
connection string / base URL, Spring `@DynamicPropertySource` registration, and a `reset()` hook. No
domain operations. These may be static (they are pure infrastructure). One shared instance per
technology, so multiple clients reuse it — e.g. one WireMock server stands in for every HTTP provider
the service integrates with (one today, more later), not one server per client.

**Layer B — DSL stub service (behaviour).** A fluent façade that *composes* Layer A and expresses what
the boundary does in domain language. This is where `stubFor(...)`, response JSON, blob uploads, and
request verification live — never in the test.

The two must not be merged: a container-support class that also builds responses, or a test that calls
`wireMockServer.stubFor(...)` directly, is the anti-pattern this split exists to prevent.

---

## 2. DSL stub service contract

- **Static factory, domain-named:** e.g. `aProviderStub()`, `aBlobStore()`. No `new`, no exposed
  constructor.
- **Chainable:** every stubbing and verification method returns `this` (builder style), so a scenario
  reads as one fluent chain.
- **Encapsulates stubbing *and* verification** in the same object — a `...WillReturnSuccess(ref)` stub
  method and a `...WasCalled()` verification method sit together; the test never reaches past the façade.
- **Domain vocabulary only:** methods take domain values (an external reference id, a blob name), never
  file paths, URLs, JSON strings, or WireMock builders. The caller is unaware of the internal response
  shape, the fixture files, or the endpoint paths — all of that is private to the stub service.
- **Infra wiring stays static** (`registerProperties(DynamicPropertyRegistry)`) because
  `@DynamicPropertySource` runs before any instance exists; it delegates the base URL / connection
  string to Layer A. Only the per-test stubbing/verification is instance/fluent.

## 3. Payloads always from fixtures — never inline

Response bodies, attachment bytes, **and expected-request/expected-output documents** load from
`src/test/resources/fixtures/…`, never hard-coded in Java (only truly trivial one-liners may be inline).
Use a small fixture loader with `${token}` substitution for the few per-test values (e.g. the external
reference id, generated notification/template ids) that must vary. This keeps the stub service readable and
lets the fixture double as living documentation of the provider contract. The caller passes domain values;
the stub service loads the fixture and substitutes tokens internally.

## 4. Verify the received request field by field — not just "a call happened"

A stub that only returns a canned response, or a verification that only asserts a call occurred, proves
nothing about what the service actually sent. Verification methods **must assert the received request
field by field, where feasible**:

- **URL / path & method** — exact path including path variables (e.g. the provider's resource id on a
  status poll) and the HTTP verb / queue name.
- **Headers** — especially auth (e.g. `Authorization: Bearer <jwt>`).
- **Body** — every field the scenario controls: scalars compared exactly; encoded payloads **decoded
  and compared to the source** (e.g. base64 attachment == the original fixture bytes); fields that must
  be absent asserted absent (e.g. no `reply_to` when the command carries none).
- **Messaging (ASB producer)** — assert the published message's body **and** application properties
  field by field, not merely that a message arrived.

Parse the captured request (WireMock `LoggedRequest`, the received `ServiceBusMessage`) and assert with
AssertJ; prefer this over loose `matchingJsonPath` presence-only checks where an exact value is known.

## 4b. JSON bodies — compare the whole document against a fixture with json-unit

For a JSON request/response body, prefer a **single whole-document comparison against an expected fixture**
over a pile of per-field `assertThat(node.path("x"))` calls. Use **json-unit** (`json-unit-assertj`, the
AssertJ-native flavour — the house assertion library is AssertJ, never Hamcrest):

```java
assertThatJson(actualBody).isEqualTo(expectedRequestJson);   // expected loaded from a fixture
```

- json-unit's **default mode is strict on object keys**, so unexpected extra fields (e.g. a `reply_to` that
  should be absent) fail the compare for free — you no longer assert absence field by field.
- **Ignore only genuinely volatile nodes, declaratively in the fixture** with a placeholder —
  `"file": "${json-unit.ignore}"` (also `${json-unit.any-string}`, `${json-unit.regex}…`), or code-side
  `whenIgnoringPaths("personalisation.material_url.file")`. The fixture then documents exactly what is not
  pinned. Do **not** hand-normalise the actual JSON (stripping whitespace, re-encoding) to force equality —
  that hack is what json-unit replaces.
- **Keep encoded-content fidelity as a separate targeted check**, not folded into the JSON compare: ignore
  the encoded node in the document compare, then decode it once and compare bytes to the source fixture
  (`assertThat(getMimeDecoder().decode(fileNode)).isEqualTo(expectedAttachment)`). Byte comparison is robust
  to base64 chunking differences; string comparison of the encoded blob is not.

## 4a. Verification must be Awaitility-safe

Verification methods assert with **AssertJ** (throw `AssertionError`) so they can be used inside
`Awaitility.untilAsserted(...)`, which only *retries* `AssertionError` — any other exception
(`NoSuchElementException`, WireMock `VerificationException`) is rethrown immediately and fails the poll.
Prefer `assertThat(server.findAll(...)).isNotEmpty()` and `assertThat(optional).hasValueSatisfying(...)`
over anything that throws a non-assertion exception on the not-yet-there path.

## 5. Resetting shared state

Layer A exposes a `reset()` method; a **test hook** calls it between tests — a JUnit `@BeforeEach` for
JUnit boundary tests, a **Cucumber `@Before`** for acceptance scenarios (the JUnit lifecycle does not
fire between Cucumber scenarios — see the `bdd-test-strategy` skill, anti-pattern "shared-stub bleed").
For a shared broker emulator also drain the DLQ / purge queues and apply `@DirtiesContext` where an
auto-started consumer would otherwise race across tests.

## 6. Emulator & credential specifics

The connection-string-for-emulator / Managed-Identity-for-real switch, the Azurite
`--skipApiVersionCheck` flag, and the ASB-emulator-needs-an-MSSQL-backing-container (ARM-overridable
image) details are in `context/springboot-mbd-gotchas.md`. The stub/support classes are where those
decisions are embodied, but the reasoning lives there to avoid duplication.

---

## Shape (illustrative, not copy-paste)

```
Layer A — lifecycle only, shared, may be static
  <WireMock support>.server() / .baseUrl() / .reset()
  <blob-emulator support>.getConnectionString() / .registerProperties(registry)

Layer B — fluent, fixture-backed, domain language
  aProviderStub()
      .<action>WillReturnSuccess(reference)   stub → returns this
      .<query>WillReturnSuccess(reference)     stub → returns this
      .<action>WasCalled();                    verify (AssertionError) → returns this

  aBlobStore()
      .containing(blobName, loadFixtureBytes("fixtures/<file>"))   returns this
      .uriOf(blobName);                                            domain value out
```
