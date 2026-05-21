# Cloud-Native Posture (Azure)

## Overview
HMCTS services run on Azure. Design and build services to take maximum advantage
of the cloud rather than treating Azure as a generic VM host. This document
captures the stable posture — the Azure-specific mechanics live in
`azure-sdk-guide.md`, Spring Boot scaffolding lives in
`skills/springboot-service-from-template/` and `skills/springboot-api-from-template/`.

---

## Shared Responsibility Model

HMCTS engineering operates under the Azure Shared Responsibility Model: the
cloud provider is accountable for the security and reliability of the platform
layers below the service boundary (hardware, hypervisor, managed service runtime,
physical network), and service teams are accountable for everything above
(identity, data, configuration, code, dependencies).

The service-hmcts-crime-springboot-template README states the posture plainly:

> "As HMCTS services are hosted on Azure, the included dependencies reflect this.
> Our aim is to stay as close to the cloud as possible in order to maximise
> alignment with the Shared Responsibility Model and achieve optimal security
> and operability."

Translated into day-to-day decisions:

- Prefer managed Azure services over self-hosted equivalents when the managed
  option covers the required capability. Offloading operational concerns to
  Azure shrinks the team's responsibility surface.
- Authenticate to Azure services with Managed Identity — the platform handles
  key rotation and credential storage. Connection strings and SAS tokens push
  responsibility the wrong way.
- Emit logs, metrics, and traces in the formats the Azure observability stack
  already understands. Do not invent a parallel pipeline.
- If a shared-responsibility ownership question cannot be answered clearly,
  write an ADR before proceeding.

---

## Cloud-Native principles for HMCTS services

### 12-Factor app on AKS
- **Config** comes from environment variables only. No environment-specific
  files, no hardcoded URLs/ports/credentials.
- **Stateless processes.** Any persistent state lives in Postgres, Redis, or
  Azure storage. No filesystem state beyond ephemeral scratch.
- **Disposable.** Graceful shutdown on SIGTERM within the Kubernetes
  `terminationGracePeriodSeconds` window. `server.shutdown: graceful` is
  configured in the Spring Boot template.
- **Logs as event streams.** JSON to stdout — never files, never syslog
  appenders. See `logging-standards.md`.
- **Port binding.** The service listens on the port from `SERVER_PORT`.

### Kubernetes-native health and lifecycle
- Liveness and readiness probes are wired to Spring Boot Actuator's health
  groups (`/actuator/health/liveness`, `/actuator/health/readiness`). The
  template exposes these by default.
- Resource requests and limits set on every Helm deployment — no uncapped
  containers.
- Forward headers honoured (`server.forward-headers-strategy: framework`) so
  the ingress controller's `X-Forwarded-*` are trusted.
- HTTP/2 enabled end-to-end (`server.http2.enabled: true`).
- Response compression enabled for JSON (`server.compression`).

### Container hygiene
- Non-root user in the container (`USER app` in the template Dockerfile).
- Base image from HMCTS Azure Container Registry — carries the HMCTS
  self-signed CA in the truststore.
- No secrets baked into images. No SAS tokens. No long-lived credentials.
- CycloneDX SBOM produced at build time (already wired in the template).

### Observability by default
- Metrics via Micrometer + Prometheus endpoint on `/actuator/prometheus`.
- Distributed tracing via OpenTelemetry (OTLP exporter). Sampling controlled
  by `TRACING_SAMPLER_PROBABILITY`.
- Application Insights via the Java agent — not a hand-rolled SDK wiring. The
  template references `lib/applicationinsights.json` at image build time.
- Metric tags always include `service`, `cluster`, `region` so the observability
  stack can slice by deployment topology.

---

## Choosing a managed service vs. building your own

Before writing code that replicates something Azure already offers, check the
managed option. The presumption is to use the managed service.

| Need                              | Managed Azure service (prefer)           | Self-host (justify with ADR)        |
|-----------------------------------|------------------------------------------|--------------------------------------|
| Relational database               | Azure Database for PostgreSQL Flexible   | Postgres in AKS                      |
| Secrets                           | Azure Key Vault                           | Anything else                        |
| Dynamic config / feature flags    | Azure App Configuration                   | Config map / bespoke service         |
| Async events / queues             | Azure Service Bus                         | Kafka in AKS, RabbitMQ               |
| Identity                          | Entra ID / Managed Identity + IDAM        | Bespoke auth                         |
| Blob storage                      | Azure Blob Storage                        | MinIO in AKS                         |
| Search                            | Azure AI Search                           | Elasticsearch in AKS                 |
| Observability (logs/metrics/traces)| Azure Monitor / Log Analytics / App Insights | Self-hosted ELK / Grafana stack |
| Cache                             | Azure Cache for Redis (or in-cluster Redis if simple) | Bespoke caching layer |

If a team proposes the right-hand column, an ADR is required. See
`skills/adr-template.md`.

---

## Rebuttals to common anti-cloud arguments

The "vendor lock-in is a reason to avoid Azure services" and "cloud is too
expensive" arguments surface regularly. Both are addressed in a dedicated
on-demand reference: `context/cloud-adoption-rationale.md`. That file is not
auto-loaded — pull it in explicitly when the conversation or an ADR needs it.

---

## Related context
- `context/tech-stack.md` — versions and technology choices.
- `context/azure-sdk-guide.md` — concrete Azure SDK usage patterns.
- `context/logging-standards.md` — mandatory JSON logging.
- `context/hmcts-standards.md` — overarching HMCTS engineering standards.
- `context/cloud-adoption-rationale.md` — on-demand rebuttals to lock-in and cost.
