---
name: test-authoring-conventions
description: |
  Conventions for authoring unit / integration / acceptance tests in CPP Modern-by-Default services —
  test naming and traceability (no requirement/AC ids in names), granularity (test behaviour, not
  structure), no comments/javadoc in tests, test data via factories/builders, DB access via
  TestRepository helpers, and external boundaries via stub services over container support. Consumed by
  the test-engineer, implementation, and code-reviewer agents (read by path) and invokable directly.
---

# Test authoring conventions (CPP Modern by Default)

Applies to every unit, integration, and acceptance test. Goal: tests that read as behaviour, stay
maintainable, and don't leak infrastructure into the test class.

---

## 1. Naming & traceability — no requirement ids in tests

- Name tests after **behaviour, in domain language**. Unit: `should_<outcome>_when_<condition>`;
  integration/boundary/acceptance: a behaviour sentence, e.g. `saves_and_reads_back_a_notification`.
- **Never embed a requirement / AC / FR / ticket identifier** (`ac001`, `AC-004`, `FR-005`, `NFR-009`,
  `PEG-1234`) in a test name — and never anywhere else in the test (there are no comments; see §2).
  Traceability lives in the story and `docs/pipeline`, not the test. AC-numbered names rot when ACs
  renumber and hide what the test actually asserts.

## 2. No comments, no javadoc in tests

Add **zero comments** to test code and **no javadoc** to test classes or methods. Well-named tests,
factories, and helpers are the documentation. (Same rule as production code: never add comments.)

## 3. Granularity — test behaviour, not structure

- Write the **fewest tests that prove the behaviour and its key failure modes** — one meaningful
  behaviour per test.
- Do **not** write a test per AC, per column, per field, or per getter/setter.
- Do **not** assert schema shape (exact column lists, DDL, index/constraint names) in behaviour tests —
  a save→fetch round-trip proves the mapping; the DDL is the migration's concern and column-list
  assertions are brittle.
- Worked example — a repository / persistence boundary test needs only:
  - one **round-trip**: build a fully-populated entity via its factory, save, fetch, assert the fields
    came back;
  - optionally one **minimal-required-fields** persist: build with only the required fields set, save,
    confirm no constraint violation.
  Per-field assertions, `existsById` / `count` micro-tests, and column-introspection tests add noise,
  not coverage — leave them out.

## 3a. Group related tests with `@Nested`

- When a test class covers **more than one distinct behavioural group**, wrap each group in a
  `@Nested` inner (non-static) class named for the behaviour, in domain language and PascalCase
  (`Sending`, `CheckingStatus`, `DeadLettering`, `WhenSendingFails`, `WhenPollingSucceeds`). The
  grouping is the documentation — no `@DisplayName`, no comments.
- Group by **behaviour/scenario**, not by method-under-test or by field. Typical groups: the happy
  path vs each failure mode; one operation vs another (`Sending` vs `CheckingStatus`); parse-failure
  vs validation-failure vs redelivery.
- **Don't nest for the sake of it.** A class with a single cohesive theme or only two or three tests
  about one operation stays flat — a `@Nested` block that contains the whole class adds ceremony, not
  clarity. Nest only when there are genuinely ≥2 separable groups.
- Shared `@Mock`/`@InjectMocks`/`@MockitoBean` fields, `@BeforeEach`/`@AfterEach`, and helper methods
  live on the **outer** class; non-static `@Nested` classes inherit them (Mockito's
  `@ExtendWith(MockitoExtension.class)` and Spring's `@SpringBootTest` both apply to nested classes,
  and a single Spring context is still cached and shared across them). `@DynamicPropertySource` stays
  `static` on the outer class.

## 4. Test data via factories/builders — never `new` a DTO in a test

- DTOs and entities are created through **builders or factories**, never instantiated directly in a
  test. Add Lombok `@Builder` to the DTO/entity (the house convention; for a JPA entity pair it with
  `@NoArgsConstructor @AllArgsConstructor`).
- Provide a **static factory per type** (e.g. `aFooCommand()`, `aFooEntity()`) in a dedicated
  `…integration.testdata` package that returns a **builder pre-filled with sensible defaults**; each
  test overrides only the fields it asserts on. Randomised ids / timestamps as defaults keep tests
  independent.

## 5. Database access via TestRepository helpers — no JDBC in test classes

- Test classes **must not** use `JdbcTemplate`, raw SQL, `EntityManager`, or the production repository
  directly for setup, verification, or cleanup. Encapsulate every DB interaction behind dedicated
  `*TestRepository` helpers (one per table/aggregate) in a separate `…integration.repository` package
  (`@Component`, autowired). They expose intent-named methods (`save`, `findById`, `countForTask`,
  `deleteAll`) and own transaction handling and any auto-commit concerns.
- **Exception — the repository's own boundary test.** The production repository *is* the subject under
  test there, so its `@DataJpaTest` boundary test autowires and exercises the **production repository
  directly** (a save→fetch round-trip). Never route a repository boundary test through its
  `*TestRepository` wrapper — that only proves the wrapper delegates. The `*TestRepository` helpers are for
  *other* tests' setup/verification, not for testing the repository itself.

## 6a. Coverage — every production class has a test, and boundary tests mock collaborators

- **Every production class is covered by exactly one kind of test:**
  - a **unit test** (all collaborators mocked) for non-boundary classes — services, orchestrators,
    mappers, validators, factories, domain logic;
  - a **boundary integration test** for a boundary class (controller, ASB consumer/producer, repository,
    REST/HTTP client, blob client) — start **only that boundary's** container/emulator, and wire it with
    the **narrowest mechanism that still exercises the real dependency — never a full `@SpringBootTest`**:
    - **no Spring at all** where the class can just be constructed (e.g. a blob/HTTP client built with the
      emulator connection string) — the fastest option, a "heavyweight unit test";
    - a **Spring test slice** where one exists — `@DataJpaTest` (repository, `replace=NONE` + real
      Testcontainer + Flyway), `@WebMvcTest` (controller);
    - a **minimal `@Import` context** for boundaries with no slice (e.g. an ASB consumer): the boundary's
      own `@Configuration` + the class under test + `@MockitoBean` collaborators + only the needed
      `@ImportAutoConfiguration` (Jackson/Validation) — no datasource/web/scheduler pulled in. Give such a
      boundary its **own isolated resource** (e.g. a dedicated queue) so its live consumer never competes
      with the full-context suite.
    A full-application `@SpringBootTest` is reserved for the **single wiring/sanity test**, which shares one
    cached context with the BDD suite (same profile, no mocks, no `@DirtiesContext`).
- A service/orchestration class with **no test is a gap, not an acceptable omission.** Before finishing,
  enumerate the production classes the change adds/touches and confirm each maps to a unit **or** boundary
  test. (e.g. two collaborating services each need their own unit test — do not assume a higher-level
  integration test covers them.)
- **A boundary test mocks the boundary's immediate collaborators** (the services/repositories it
  delegates to) and asserts the boundary's *own* behaviour: it consumes/parses/validates the input,
  **delegates to its collaborator with the right arguments**, and handles the outcome (acks / commits /
  settles / maps the response). It does **not** re-verify what the collaborator does — persistence,
  business rules, downstream side effects belong to the collaborator's own test. Example: an ASB consumer
  test starts the Service Bus emulator, **mocks the service it delegates to**, and verifies "message
  consumed → the collaborator is invoked with the right arguments → message completed / dead-lettered /
  abandoned" — it does not talk to a real database.

## 6. External boundaries via stub services over container support

- Keep the reusable **container/emulator support** (lifecycle only — Postgres / Azurite / WireMock /
  Service Bus) separate from the **fluent stub service / test client** that expresses behaviour (one per
  external system — HTTP provider, blob store, message broker). The stub/client **composes** the support;
  never merge the two, and never call the SDK / WireMock / broker directly from a test. Payloads load
  from fixtures, not inline. Full recipe: skill `test-stub-dsl`.

## 7. Assertions — AssertJ everywhere; json-unit for JSON documents

- **AssertJ is the house assertion library** (`org.assertj.core.api.Assertions.assertThat`). Do **not**
  introduce Hamcrest matchers (it is only ever a transitive dependency).
- For a **JSON body/payload**, compare the whole document against an expected fixture with **json-unit**
  (`json-unit-assertj`: `assertThatJson(actual).isEqualTo(expectedFixture)`) rather than a stack of
  per-field `path(...)` assertions. Ignore only volatile nodes declaratively — `"${json-unit.ignore}"` in
  the fixture, or `whenIgnoringPaths(...)` — and never hand-normalise the actual JSON to force equality.
  Full recipe (incl. keeping encoded-attachment byte fidelity as a separate check): skill `test-stub-dsl` §4b.

---

## Related skills
- `test-stub-dsl` — how to build the stub services / test clients, container support, and fixtures.
- `bdd-test-strategy` — when a story warrants BDD, and feature/step-definition conventions.
