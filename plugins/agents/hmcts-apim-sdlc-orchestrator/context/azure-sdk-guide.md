## Azure SDK and Cloud-Native Guide

### Posture

HMCTS services run on Azure. Build to take advantage of it — not to treat Azure as a
generic VM host. The Shared Responsibility Model applies: Azure owns the platform
layers below the service boundary; the team owns identity, data, configuration, code,
and dependencies.

---

### Authentication — Managed Identity only

Every Azure integration uses `DefaultAzureCredential`:
- **In AKS**: resolves to the workload's User-Assigned Managed Identity
- **Locally**: resolves to developer credentials (Azure CLI, VS Code)

```java
BlobServiceClient client = new BlobServiceClientBuilder()
    .endpoint("https://%s.blob.core.windows.net".formatted(accountName))
    .credential(new DefaultAzureCredentialBuilder().build())
    .buildClient();
```

Assign each service its own User-Assigned Managed Identity. No shared identities.
Least privilege: a service that only reads secrets gets `Key Vault Secrets User`, not
`Contributor`.

**Forbidden — in code, `application.yaml`, Helm values, env vars, `.env`, or commit history:**
connection strings, account keys, SAS tokens, SAS URLs, long-lived credentials of any kind.
If one appears during migration, treat it as an incident and rotate immediately.

---

### Azure Key Vault

- Starter: `azure-spring-cloud-starter-keyvault-secrets` or direct `SecretClient`
- Cache secret reads — do not call Key Vault on every request
- Never log a secret value, a Key Vault URL combined with a version, or any env var that
  contains one
- Key rotation is Key Vault's responsibility — Shared Responsibility in action

---

### Azure Service Bus

- Starter: `com.azure.spring:spring-cloud-azure-starter-servicebus`
- Authenticate with Managed Identity; no namespace connection string

**At-least-once delivery — handlers must be idempotent:**
Service Bus delivers each message at least once. Handlers must detect and skip duplicates.
Silent duplicate skips are not permitted — log at INFO at the skip site (per `service-shared.md`
explicit idempotency rule).

**Dead-letter queue — wire it explicitly:**
Do not silently drop failed messages. Configure dead-letter handling for every subscription.
Failed messages that exhaust delivery attempts land in the DLQ; they must be monitored.

**Correlation propagation:**
Emit the `correlationId` (from MDC) into message application properties on every outbound
Service Bus message so downstream services can link traces.

**Tuning (in Helm, not code):**
Consumer concurrency, max-delivery-count, lock duration, and prefetch are configured in Helm
values per topic/subscription. Do not hardcode these in `application.yaml`.

---

### Azure App Configuration

- Starter: `spring-cloud-azure-starter-appconfiguration`
- Use for values that must change without a redeploy (feature flags, runtime tunables)
- Static service configuration stays in Spring's own config — App Configuration is for
  runtime-changeable values only

---

### Observability wiring

- **Application Insights**: wired via the Azure Monitor Java agent at container start
  (`lib/applicationinsights.json` in the template Dockerfile). Do not embed the App Insights SDK.
- **OpenTelemetry**: `spring-boot-starter-opentelemetry` is the in-process API for custom
  spans and metrics.
- **Micrometer**: custom metrics go through Micrometer. Metric tags must include `service`,
  `cluster`, `region` — the template wires these via `management.metrics.tags`.
- **W3C Trace Context**: honoured on ingress and propagated on outbound calls via OTEL
  auto-instrumentation. `TRACING_SAMPLER_PROBABILITY` controls sampling.

---

### Kubernetes — container and cluster hygiene

- **Non-root container**: `USER app` in Dockerfile (template enforces this)
- **Base image**: `eclipse-temurin:25-jre` (template); carries the HMCTS trust store
- **Resource requests and limits**: must be set on every Helm deployment — no uncapped containers
- **Liveness and readiness probes**: wired to `/actuator/health/liveness` and
  `/actuator/health/readiness` in Helm; both must return 200 locally before PR is raised
- **Forward headers**: `server.forward-headers-strategy: framework` (template default) —
  honours `X-Forwarded-*` from the ingress controller
- **HTTP/2**: `server.http2.enabled: true` (template default)
- **Graceful shutdown**: `server.shutdown: graceful` (template default) — handles SIGTERM
  within `terminationGracePeriodSeconds`
- **CycloneDX SBOM**: produced at build time by the template's Gradle config; do not remove

---

### SDK vs. Spring Cloud Azure starter

Use the **Spring Cloud Azure starter** when the integration fits standard Spring idioms
(messaging listeners, Spring Data repositories, property-based config binding) and you want
Managed Identity auto-configured.

Use the **raw `com.azure:*` SDK** when you need a feature the starter does not expose or
when writing code outside the Spring lifecycle.

**Do not mix both** for the same integration — pick one and stay with it.

---

### Managed service selection (prefer managed; justify self-host with ADR)

| Need | Prefer | Justify with ADR |
|---|---|---|
| Secrets | Azure Key Vault | Anything else |
| Async messaging | Azure Service Bus | Kafka in AKS, RabbitMQ |
| Relational DB | Azure Database for PostgreSQL Flexible | Postgres in AKS |
| Feature flags | Azure App Configuration | Config map / bespoke service |
| Identity | Entra ID / Managed Identity | Bespoke auth |
| Blob storage | Azure Blob Storage | MinIO in AKS |
| Observability | Azure Monitor / App Insights | Self-hosted ELK / Grafana |

---

### Forbidden patterns (full list)

- Connection strings, SAS tokens, account keys, storage keys in `application.yaml`, env vars, Helm values, `.env`, or code
- SAS URLs embedded in images or committed to git
- Secret values printed to logs, exception messages, or error responses
- Bespoke HTTP clients against Azure service endpoints when an official SDK covers it
- Treating any scoped connection string as "safe" — rotation is impossible at scale
- Shared Managed Identities between services