# Azure SDK Guide

## Overview
Azure is the chosen cloud for HMCTS services. When a service integrates with
Azure, it uses the official Azure SDKs — `com.azure:*` and the
`com.azure.spring:spring-cloud-azure-*` starters — authenticated with Managed
Identity. This file is referenced on-demand by skills and agents working on
Azure integrations; it is not auto-loaded.

For the overall cloud-native posture, see `azure-cloud-native.md`.

---

## Authentication — Managed Identity only

- Default credential chain: `DefaultAzureCredential` (Managed Identity in AKS,
  developer credentials locally).
- Assign each workload its own User-Assigned Managed Identity via the Helm
  chart. No shared identities between services.
- Least privilege at the role assignment level: a service that only reads
  secrets gets `Key Vault Secrets User`, not `Contributor`.
- **Connection strings, account keys, and SAS tokens are not permitted** in
  code, `application.yaml`, Helm values, environment variables, or commit
  history. If one appears during migration work, treat it as an incident and
  rotate immediately.

```java
// Typical SDK client construction
BlobServiceClient client = new BlobServiceClientBuilder()
    .endpoint("https://%s.blob.core.windows.net".formatted(accountName))
    .credential(new DefaultAzureCredentialBuilder().build())
    .buildClient();
```

---

## Secrets — Azure Key Vault

- Resolve secrets via `azure-spring-cloud-starter-keyvault-secrets` or direct
  `SecretClient` calls. Cache reads; do not hammer Key Vault on every request.
- Never log a secret value, a Key Vault URL combined with a version, or a
  header/environment variable that contains one.
- Rotation is Key Vault's responsibility once you stop using long-lived
  credentials — this is Shared Responsibility in action.

---

## Dynamic configuration / feature flags — Azure App Configuration

- Use `spring-cloud-azure-starter-appconfiguration` for values that need to
  change without a redeploy (feature flags, tunables).
- Keep static service configuration in Spring's own config — App Configuration
  is for runtime-changeable values.

---

## Messaging — Azure Service Bus

- Starter: `com.azure.spring:spring-cloud-azure-starter-servicebus`.
- Authenticate with Managed Identity; no namespace connection string.
- Handlers must be **idempotent** — Service Bus is at-least-once.
- Wire dead-letter handling explicitly. Do not silently drop failed messages.
- Emit the correlation / request ID into the message application properties
  so downstream services can link traces.
- Consumer concurrency, max-delivery-count, lock duration, and prefetch are
  tuned per topic/subscription in Helm values, not in code.

---

## Observability

- **Application Insights** is wired via the Azure Monitor Java agent at
  container start (see the template Dockerfile — `lib/applicationinsights.json`
  travels with the image). Services do not embed the App Insights SDK.
- **OpenTelemetry** is the in-process API for custom spans and metrics. The
  Spring Boot `spring-boot-starter-opentelemetry` is already on the template's
  dependency list.
- **Custom metrics** go through Micrometer. Tag with `service`, `cluster`,
  `region` (template already sets these).
- **Trace context propagation**: W3C Trace Context headers are honoured on
  ingress and propagated on outbound calls via the OTEL auto-instrumentation.

---

## Storage, Cosmos DB, Event Hubs, Event Grid

- Prefer the official `com.azure:*` SDKs over raw HTTP.
- For Cosmos DB: `spring-cloud-azure-starter-cosmos` if using Spring data
  repositories; direct `CosmosClient` otherwise.
- Pagination, retry, and back-off come from the SDK — do not reimplement them.
- Lifecycle (`close()`) is handled by the Spring container when beans are
  defined properly; avoid holding SDK clients in static fields.

---

## Forbidden patterns

- Connection strings, SAS tokens, account keys, storage keys in
  `application.yaml`, env vars, Helm values, `.env` files, or code.
- SAS URLs embedded in images or committed to git.
- Secret values printed to logs, exception messages, or error responses.
- Bespoke HTTP clients against Azure service endpoints when an official SDK
  covers the scenario.
- Treating any connection string as "safe because it's scoped" — rotation is
  impossible at scale.

---

## When to reach for the SDK vs. the Spring starter

Use the Spring Cloud Azure starter when:
- The integration fits standard Spring idioms (messaging listeners, Spring
  Data repositories, property-based config binding).
- You want auto-configuration for Managed Identity resolution.

Use the raw SDK when:
- You need a feature the starter does not expose.
- You're writing something outside the Spring lifecycle.

Both are acceptable. Mixing them inside one integration is not — pick one per
integration and stay with it.

---

## Related
- `context/azure-cloud-native.md` — cloud-native posture and Shared Responsibility.
- `context/logging-standards.md` — JSON logging mandate.
- `context/tech-stack.md` — version pins.
- Template: `service-hmcts-crime-springboot-template/build.gradle`, `application.yaml`, `Dockerfile` — see for concrete wiring.
