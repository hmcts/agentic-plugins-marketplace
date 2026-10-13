# Spring Boot Modern-by-Default — implementation gotchas

Stack-specific, hard-won lessons for `cp-*` / `cpp-mbd-*` services on Spring Boot 4.x / Java 25 that use
cp-task-manager, the Azure SDK, and Testcontainers. These are **reference notes to consult while
implementing** — narrow and non-obvious by design (they fail far from their cause), which is exactly why
they live here rather than in an agent's instruction body. Consult when the work touches the relevant
area; not every service needs every note.

---

## cp-task-manager (persistent jobs / async tasks)

- **`@EnableScheduling` is required or the job poller never runs.** Without it there is no error — tasks
  are simply never picked up and nothing executes. Silent, misleading feedback loop.
- **`@EntityScan("uk.gov.hmcts.cp")`** so the task-manager `@Entity` classes are discovered alongside
  your own; otherwise the `jobs` table mapping is missing at startup.
- **App Flyway migrations must be `V1000`+.** cp-task-manager owns `V1`/`V2`; starting your own at `V1`
  collides and Flyway fails validation. Reserve low numbers for the library.
- **`ExecutionStatus` has only `STARTED` / `INPROGRESS` / `COMPLETED` — no `FAILED`.** Model failure in
  your own domain column (e.g. `notification.status = FAILED`); do not expect the task framework to carry
  a failed state.
- **`ExecutableTask.getRetryDurationsInSecs()` returns `Optional<List<Long>>`.** Return
  `Optional.of(List.of(...))` for a fixed backoff list; empty Optional for framework default.

## Atomicity — INSERT + task enqueue in one transaction

- The domain row insert and the task enqueue must commit together. Configure Hikari
  `auto-commit: false` **and** Hibernate `provider_disables_autocommit: true` so both share the local
  transaction; if either fails, neither persists. In tests that write directly (cleanup, seeding) with
  auto-commit off, wrap the writes in a `TransactionTemplate`, or they silently do nothing.

## Azure SDK — credential switching (NFR-002)

- **Connection strings only for the emulator / local / test** path; **`DefaultAzureCredential`
  (Workload Identity) for real environments.** No SAS tokens / account keys / connection strings in
  code, config, env, or Helm for deployed envs. Mirror the `cpp-context-reference-data` BYO-filestore
  producer: `configuration.hasConnectionString() ? builder.connectionString(cs)
  : builder.credential(new DefaultAzureCredentialBuilder().build()).endpoint(ep)`. Same pattern for both
  Blob and Service Bus clients.
- **IMDS (169.254.169.254) does not work for AKS Workload Identity** — use the federated-token exchange
  the SDK's `DefaultAzureCredential` performs; do not hand-roll IMDS calls.

## Jackson 3 (Spring Boot 4)

- Spring Boot 4 ships **Jackson 3**, whose package is **`tools.jackson.*`** (e.g.
  `tools.jackson.databind.JsonNode`), **not** `com.fasterxml.jackson.*`. Importing the old package
  compiles against the wrong (transitive) Jackson and misbehaves at runtime. Add the JSON-P provider
  (`parsson`) as `runtimeOnly` when a library needs `jakarta.json`.

## Testcontainers (integration/acceptance harness)

- **Azurite needs `--skipApiVersionCheck`.** The `azure-storage-blob` SDK defaults to a newer
  `x-ms-version` than the emulator build recognises; without the flag every call 4xxs with a version
  error unrelated to the test.
- **The Service Bus emulator needs an MSSQL backing container**, and MSSQL has no ARM image — make the
  image overridable (`-Dcp.test.mssql.image` / `CP_TEST_MSSQL_IMAGE`, `asCompatibleSubstituteFor`) so
  Apple-silicon developers can substitute an ARM-compatible image.
- **Shared JVM-singleton emulators leak state across tests.** Drain the DLQ / purge queues between
  tests and apply `@DirtiesContext` where an auto-started ASB consumer would otherwise linger in the
  context cache and race another test's consumer for the shared queue.
- **Awaitility `untilAsserted` only retries `AssertionError`.** A `NoSuchElementException`
  (`optional.orElseThrow()`) or WireMock `VerificationException` inside the block is rethrown immediately
  and fails the poll. Use AssertJ assertions on the not-yet-there path
  (`assertThat(repo.findById(id)).hasValueSatisfying(...)`, `.isNotEmpty()`).
