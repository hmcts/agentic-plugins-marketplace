# HMCTS / CPP Tech Stack

## Overview
This file describes the technology stack in use on the Crime Common Platform (CPP).
All agents must consult this before making implementation or tooling decisions.

CPP follows two distinct architectural patterns:

1. **CQRS / Event Sourcing** — multi-module Maven services on the CPP microservice framework (`cpp-context-*`).
2. **Modern by Default (MbD)** — Spring Boot 3.x/4.x services on Gradle (`cp-*`, `cpp-mbd-*`). Preferred for all new work.

Frontend, infrastructure, CI/CD, and observability stacks are shared across both patterns.

---

## 1. CQRS / Event Sourcing stack (`cpp-context-*`)

Used by ~42 bounded-context services (hearing, resulting, prosecution-casefile, defence, listing, etc.).

### Languages and frameworks
| Layer | Technology | Version / Notes |
|---|---|---|
| Language | Java | JDK 17 (Maven enforcer `[17,)`) |
| Framework | CPP Microservice Framework (`cp-microservice-framework`) | 17.105.x |
| Framework libraries | `cp-framework-libraries` | 17.105.x |
| Platform libraries | `cpp-platform-libraries` | 17.105.x |
| Core domain | `cpp-platform-core-domain` | 17.x |
| Event store | `cp-event-store` BOM | 17.105.x |
| Common BOM | `cp-maven-common-bom` | 17.104.x |
| Runtime | WildFly (WAR packaging via `maven-wildfly-plugin`) | Java 17 profile |

### Parent POM chain
`cp-maven-super-pom` (17.0.0) → `cp-maven-parent-pom` (17.103.x) → `cpp-platform-maven-service-parent-pom` (17.103.x) → service parent.

### Module convention
Each context repo contains:
`-command`, `-query`, `-domain`, `-event`, `-event-sources`, `-viewstore`, `-viewstore-liquibase`, `-service`, `-integration-test`.

### Databases
| Type | Technology | Version |
|---|---|---|
| Relational | PostgreSQL | 16 (Azure Flexible Server / AKS); driver `42.3.2` |
| Migrations | Liquibase | 4.10.0 (changelog XML/YAML) |
| In-memory tests | H2 | 2.3.232 |

### Messaging / eventing
| Use case | Technology |
|---|---|
| Async events (intra-context) | JMS via `messaging-jms` (microservice framework), embedded Artemis 2.18 in dev |
| Async events (cross-context) | Azure Service Bus |
| Event store | Postgres-backed event store (`cp-event-store`) |
| Synchronous APIs | REST (RAML contracts) |

### Build tooling
- Maven 3.3.9+
- Plugins: `raml-maven-plugin`, `json-schema` plugins, `jacoco` 0.8.8, `surefire`/`failsafe` 3.1.2, `jgitflow-maven-plugin`
- JaCoCo + SonarQube enforced via parent POM

### Test stack
| Layer | Technology |
|---|---|
| Unit | JUnit 5 (Jupiter), Mockito (`mockito-junit-jupiter`), JUnit DataProvider 1.13.1 |
| Integration | Spring Test where used, embedded Artemis + PostgreSQL containers |
| BDD | Cucumber 7 + Serenity BDD, `cucumber-reporting` 2.0.0 |
| API | REST Assured |
| External mocking | WireMock |
| Domain testing | `domain-test-dsl` (cp-framework-libraries) |

### Local development
`cpp-developers-docker`: WildFly (9990 admin, 8787 debug), PostgreSQL 11, Artemis 2.18 (61616), Elasticsearch 7.16, Alfresco 7.2, HAProxy, Docmosis, Camunda. Bootstrapped via `buildAndStartContainers()`.

### Package conventions
- Legacy: `uk.gov.justice.*`
- Platform: `uk.gov.moj.cpp.*`

---
using 
## 2. Modern by Default (MbD) stack (`cp-*`, `cpp-mbd-*`)

**Default for all new services.** Spring Boot, Gradle, cloud-native, OpenTelemetry-first.

### Languages and frameworks
| Layer | Technology | Version / Notes |
|---|---|---|
| Language | Java | 17 (`sourceCompatibility`), 21 toolchain on newer services |
| Framework | Spring Boot | 3.4.x — 4.0.x (latest services on 4.0.2/4.0.3) |
| Dependency mgmt | Spring Cloud BOM | 1.1.7 |
| Build | Gradle | 8.x (Kotlin or Groovy DSL) |
| Mapping | MapStruct | 1.5.5 |
| Boilerplate | Lombok | 1.18.38+ |
| Auth filter | `cp-auth-rules-filter` | 1.0.7 |
| Group | `uk.gov.hmcts.cp` | (HMCTS naming) |

### Parent / publishing
- Some MbD services use `cp-maven-framework-parent-pom` (Maven variant, 17.103.x); most use Gradle with Spring Boot Gradle plugin 4.0.x.
- Artefacts published to **Azure Artifacts** + **GitHub Packages** (`maven.pkg.github.com`).

### Spring Boot starters in common use
`spring-boot-starter-web`, `spring-boot-starter-actuator`, `spring-boot-starter-data-jpa`, `spring-boot-starter-flyway`, `spring-boot-starter-opentelemetry`, `spring-boot-starter-test`.

### Databases
| Type | Technology | Notes |
|---|---|---|
| Relational | PostgreSQL 16 | Azure Flexible Server |
| Migrations | **Flyway** | (Liquibase only on legacy CQRS) |
| Cache | Redis | Session, feature flags |
| ORM | JPA / Hibernate | via Spring Boot BOM |

### Messaging / eventing
| Use case | Technology |
|---|---|
| Cross-service async | Azure Service Bus |
| Intra-service | Spring Application Events |
| Serverless | Azure Functions Java Library 3.2.3 (where applicable) |

### Cloud SDKs
- Azure Identity / Data Tables: `azure-sdk` 1.3.4
- Azure OpenAI: 1.0.0-beta.16 (used by `cp-ai-rag-service`)
- Azure Key Vault for secrets

### Observability
- **OpenTelemetry** (spring-boot-starter-opentelemetry 4.0.3)
- Micrometer + Prometheus via Actuator
- Logstash Logback Encoder 8.1, Logback 1.5.18, structured JSON with MDC correlation IDs

### API & security
- OpenAPI 3 / Swagger Core 2.2.36
- JJWT 0.13.0
- Jackson 2.20.x (incl. `jackson-dataformat-xml` 2.15.2+)

### Test stack
| Layer | Technology | Version |
|---|---|---|
| Unit | JUnit 5 | BOM 5.13.4 |
| Mocking | Mockito | 5.21.0 |
| Assertions | AssertJ | 3.27.7 |
| Integration | Spring Boot Test, TestContainers | — |
| External mocking | WireMock (Jetty12) | 3.13.2 |
| Contract | Pact (consumer-driven) | — |
| BDD (where used) | Cucumber 7 + Serenity BDD | — |

### Build tooling
- Gradle plugins: `jacoco`, `maven-publish`, `docker-compose` 0.17.12+, `gradle-git-properties` 2.5.3, CycloneDX BOM 2.4.1, ben-manes versions 0.53.0
- `./gradlew compileJava | test | bootRun`

### Package convention
- `uk.gov.hmcts.cp.*`

---

## 3. Frontend stack (`cpp-ui-*`) — shared

| Layer | Technology | Version |
|---|---|---|
| Framework | Angular | 19.2.x |
| Language | TypeScript | 5.6 |
| State | ngrx (store, effects, router-store, signals) | 19.2.1 |
| Reactive | RxJS | 7.8 |
| Design system | govuk-frontend (GOV.UK Design System) | per-app |
| UI components | ngx-bootstrap, Angular Material / CDK 19.2.19, ng-select 14.9, Kolkov Editor 2.1, ngx-markdown 19.1, ngx-extended-pdf-viewer 25.6 |
| AI features | OpenAI SDK | 5.12.x |
| Internal libs | `@cpp/application`, `@cpp/core`, `@cpp/pdk`, `@cpp/reference-data`, `@cpp/scheduling`, `@cpp/users-groups` | 19.0.2+ |
| Unit tests | Jest or Jasmine | — |
| E2E | Playwright (preferred) or Selenium 4, Serenity BDD where applicable | — |
| Accessibility | axe-core + Playwright; WCAG 2.1 AA mandatory | — |

Build commands: `npm install`, `npm run start | build | test | lint | ci:test`.

---

## 4. Infrastructure — shared

| Component | Technology | Notes |
|---|---|---|
| Cloud | Microsoft Azure | All workloads |
| Platform | Azure AKS (Kubernetes) | HMCTS Reform Platform |
| GitOps | Flux CD (`cpp-flux-config`) | All env deployments |
| Helm | Helm 3 (`cpp-helm-chart`) | Chart per service, OCI in ACR |
| Registry | Azure Container Registry | OCI Helm + Docker images |
| Secrets | Azure Key Vault | Never hardcode |
| IaC | Terraform (`cpp-terraform-*`, `cpp-module-terraform-*`) | AKS, ServiceBus, Postgres, AppInsights, Storage, etc. |
| Network | Azure VNet, Barracuda NGF, Azure API Management | — |

---

## 5. CI/CD — shared

| Stage | Technology | Notes |
|---|---|---|
| CI (primary) | **Azure DevOps Pipelines** | Templates in `cpp-azure-devops-templates` |
| CI (secondary) | GitHub Actions | Some platform/infra repos |
| Build (Java legacy) | Maven | `mvn clean verify` |
| Build (Java MbD) | Gradle | `./gradlew build` |
| Build (UI) | npm | — |
| Static analysis | SonarQube / SonarCloud | — |
| Dependency scan | Snyk | Critical/High blocks pipeline |
| Secret scanning | gitleaks (`cpp-hooks-gitleaks`) | Pre-commit |
| Artefact | Docker image → ACR; Maven jar → Azure Artifacts + GitHub Packages | — |
| Deploy | Flux CD + Helm | GitOps repo separate from app repo |
| Agent pools | `MDV-ADO-AGENTS-01` (dev/test), `MPD-ADO-AGENTS-01` (prod) | — |

Pipeline templates:
- Context services: `pipelines/context-verify.yaml` (PR), `pipelines/context-validation.yaml` (merge)
- UI apps: `pipelines/ui-verify.yaml`, `pipelines/ui-validation.yaml`
- Terraform: `pipelines/terratest.yaml`

---

## 6. Monitoring — shared

| Component | Technology |
|---|---|
| Logs | Azure Monitor / Log Analytics |
| Metrics | Azure Monitor, Prometheus, Micrometer (MbD), OpenTelemetry (MbD) |
| App tracing | Azure Application Insights |
| Alerts | PagerDuty |
## Master source for Spring Boot apps
The canonical, authoritative definitions for a Spring Boot service or API repo
are the HMCTS templates:

- **Service:** [`hmcts/service-hmcts-crime-springboot-template`](https://github.com/hmcts/service-hmcts-crime-springboot-template) — runtime Spring Boot service (Spring Boot 4.0.5, Java 25, Gradle 9.4.1, Flyway, Postgres, OpenTelemetry, logstash JSON logging, PMD, CycloneDX, App Insights agent).
- **API spec:** [`hmcts/api-hmcts-crime-template`](https://github.com/hmcts/api-hmcts-crime-template) — OpenAPI spec repo with naming rules, validation tooling, publishing workflows.
- **Reference examples:** [`hmcts/service-hmcts-springboot-demo`](https://github.com/hmcts/service-hmcts-springboot-demo) — look at the Spring Boot 4 modules only (`postgres-springboot4`). Ignore the Spring Boot 3 demo modules.

Skills [`springboot-service-from-template`](../skills/springboot-service-from-template/SKILL.md) and [`springboot-api-from-template`](../skills/springboot-api-from-template/SKILL.md) walk through adopting them. Do not scaffold Spring Boot apps from scratch; when the template updates, the service picks the update up by refresh, not by duplication.

## Azure-first posture
HMCTS runs on Azure. Cloud-native decisions are governed by
[`azure-cloud-native.md`](./azure-cloud-native.md); Azure SDK usage and
Managed Identity patterns by [`azure-sdk-guide.md`](./azure-sdk-guide.md);
logging by [`logging-standards.md`](./logging-standards.md). Cost and
vendor-lock-in rebuttals are in [`cloud-adoption-rationale.md`](./cloud-adoption-rationale.md) — on-demand only.

---
## Languages and frameworks
| Layer        | Technology                | Notes                                      |
|--------------|---------------------------|--------------------------------------------|
| Backend      | Java 25 / Spring Boot 4.0.5 / Gradle 9.4.1 | Canonical versions track the HMCTS templates (see below) |
| Frontend     | govuk-frontend            | GOV.UK Design System for consistent government UI patterns|
|              |  ngrx                     | Reactive state management                  |
|              |    ngx-bootstrap          |   UI component library |
|              |    Jest or Jasmine        |  Unit testing|
| Scripting    | Github                    |                                            |

## Databases
| Type         | Technology    | Notes                                      |
|--------------|---------------|--------------------------------------------|
| Relational   | PostgreSQL 16 | Via Azure Flexible Server or AKS           |
| Cache        | Redis         | Session and feature flag caching           |

## Messaging / eventing
| Use case     | Technology           | Notes                                      |
|--------------|----------------------|--------------------------------------------|
| Async events | Azure Service Bus    | Standard for cross-service events          |
| Internal     | Spring Application Events | Within a single service boundary      |

## Infrastructure
| Component    | Technology              | Notes                                      |
|--------------|-------------------------|--------------------------------------------|
| Platform     | Azure AKS (Kubernetes)  | HMCTS Reform Platform                      |
| GitOps       | Flux CD                 | All environment deployments via Flux       |
| Helm         | Helm 3                  | Chart per service                          |
| Registry     | Azure Container Registry|                                            |
| Secrets      | Azure Key Vault         | Never hardcode secrets                     |

## CI/CD
| Stage        | Technology              | Notes                                      |
|--------------|-------------------------|--------------------------------------------|
| CI           | GitHub Actions          | All pipelines in `.github/workflows/`      |
| Build        | Gradle (Java), npm      |                                            |
| Static analysis | SonarQube / SonarCloud |                                           |
| Dependency scan | Snyk                 | Critical/High = pipeline block             |
| Artefact     | Docker image → ACR      |                                            |
| Deploy       | Flux CD / Helm          | GitOps repo separate from app repo         |

## Test tooling
| Layer        | Technology                       |
|--------------|----------------------------------|
| Unit         | JUnit 5, Mockito                 |
| Integration  | Spring Boot Test, TestContainers |
| BDD          | Cucumber 7 + Serenity BDD        |
| API          | REST Assured                     |
| Contract     | Pact (consumer-driven)           |
| Accessibility| axe-core, Playwright             |
| UI E2E       | Playwright or Selenium 4         |

## Monitoring
| Component    | Technology              | Notes |
|--------------|-------------------------|-------|
| Logs         | Azure Monitor / Log Analytics | JSON to stdout via logstash-logback-encoder — see `logging-standards.md` |
| Metrics      | Azure Monitor, Prometheus | Micrometer → `/actuator/prometheus`, tags `service`/`cluster`/`region` |
| Tracing      | OpenTelemetry → Azure Monitor | `spring-boot-starter-opentelemetry`; OTLP exporter |
| APM          | Application Insights    | Injected via the Java agent at image build time — **do not** embed the App Insights SDK in code |
| Alerts       | PagerDuty               | |

---

## 7. Sandbox environment

- Namespace: `[project]-sandbox`
- Ingress: `https://[service]-sandbox.platform.hmcts.net`
- Deployed via: Flux CD watching the `sandbox` overlay in the GitOps repo
- Smoke test base URL: set in `TEST_BASE_URL` environment variable

---

## 8. Choosing a pattern for new work

| Question | CQRS / Event Sourcing | Modern by Default |
|---|---|---|
| New bounded context with rich domain model + audit/event history? | ✅ Yes | ❌ |
| New API service / integration / utility / serverless function? | ❌ | ✅ Yes |
| Extending an existing `cpp-context-*` service? | ✅ Stay in CQRS | ❌ |
| Greenfield service, no event-sourcing requirement? | ❌ | ✅ Default |

**Default to Modern by Default.** Only choose CQRS/Event Sourcing when the domain genuinely requires event sourcing or when extending an existing context service.

---

## Key version matrix

| Component | CQRS | MbD |
|---|---|---|
| Java | 17 | 17 source / 21 toolchain |
| Spring Boot | n/a (framework-provided) | 3.4.x – 4.0.x |
| Build | Maven 3.3.9+ | Gradle 8.x |
| DB migrations | Liquibase 4.10 | Flyway |
| PostgreSQL driver | 42.3.2 | via Spring Boot BOM |
| Messaging | JMS / Artemis + Azure Service Bus | Azure Service Bus + Spring Events |
| Tracing | Framework metrics | OpenTelemetry 4.0.3 |
| Tests | JUnit 5, Mockito, REST Assured, WireMock | JUnit 5.13.4, Mockito 5.21, AssertJ 3.27, WireMock 3.13 |
