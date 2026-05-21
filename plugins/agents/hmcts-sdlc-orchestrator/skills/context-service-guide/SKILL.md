---
name: context-service-guide
description: Navigate and understand any legacy cpp-context-* WildFly/Maven service. LEGACY ONLY — must not be applied to new Spring Boot work. Use when onboarding to a context service, exploring its modules, or understanding its CQRS structure and integrations.
---

> ⚠️ **Legacy WildFly context services only.** The patterns in this skill — `cpp-context-*` Maven multi-modules, `-command-api` / `-query-api` / `-domain-event`, RAML, custom CQRS plumbing, `subscriptions-descriptor.yaml` — are **WildFly-era patterns and must not be applied to new Spring Boot services**. They exist here to help engineers onboard to existing services.
>
> For **new Spring Boot services**, use `skills/springboot-service-from-template/`.
> For **new HMCTS Marketplace API specs**, use `skills/springboot-api-from-template/`.
> Cross-pollinating these patterns into a Spring Boot service is a design regression — the master source for Spring Boot is the HMCTS template (see `context/tech-stack.md`).

# Context Service Guide

Provides a structured walkthrough of any CP context service repository to help developers quickly understand its purpose, structure, integrations, and development workflow.

## When to Use

- User asks to "explain this context service", "walk me through this repo", "what does this service do"
- User is new to a `cpp-context-*` repo and wants to understand it
- User asks about a service's domain events, commands, queries, or integrations

## Process

### Step 1: Identify the Context Service

Determine which `cpp-context-*` repo the user is asking about. If they're in a subdirectory, resolve to the repo root.

### Step 2: Read Key Files

Read these files in parallel to build a complete picture:

1. **`pom.xml`** (root) — parent POM, modules list, properties, dependency versions
2. **`README.md`** — if present, provides an overview
3. **`*-domain/*-domain-event/src/main/resources/json/schema/`** — domain event schemas reveal what the service publishes
4. **`*-command/*-command-api/src/raml/`** — command API RAML definitions reveal what operations the service accepts
5. **`*-query/*-query-api/src/raml/`** — query API definitions reveal what data the service exposes
6. **`*-viewstore-liquibase/`** — Liquibase changelogs reveal the read-model database schema
7. **`*-event-sources/`** — event source configurations reveal what events from other contexts this service subscribes to

### Step 3: Map Integrations

From the POM dependencies and event sources, identify:
- **Upstream contexts** — which other context services publish events this service consumes
- **Downstream contexts** — which contexts consume this service's domain events
- **Shared components used** — audit, auth, reference data, file service, notifications, etc.
- **External systems** — any SOAP/REST integrations with systems outside CP

### Step 4: Identify Module Structure

Map the standard CQRS module layout:

| Module | Purpose | Key classes to look at |
|--------|---------|----------------------|
| `-command-api` | Command definitions | RAML files, JSON schemas |
| `-command-handler` | Command processing | `*CommandHandler.java`, `*Aggregate.java` |
| `-query-api` | Query definitions | RAML files |
| `-query-handler` | Query processing | `*QueryHandler.java` |
| `-domain-event` | Domain events | JSON schemas in resources |
| `-domain-value-schema` | Value objects | JSON schemas |
| `-event-sources` | Event subscriptions | `*EventSource.java` |
| `-viewstore` | JPA read models | `*Entity.java`, `*Repository.java` |
| `-viewstore-liquibase` | DB migrations | `db/changelog/` XML/YAML files |
| `-service` | App orchestration | WildFly deployment descriptors |
| `-integration-test` | Integration tests | Cucumber features, step definitions |

### Step 5: Generate Summary

Output a structured summary:

```
## [Service Name]

### Purpose
One paragraph describing what this bounded context manages.

### Domain Events Published
- event.name.one — description
- event.name.two — description

### Commands Accepted
- command.name.one — description

### Queries Exposed
- query.name.one — description

### Upstream Dependencies
- cpp-context-X — consumes events from...

### Downstream Consumers
- cpp-context-Y — publishes events consumed by...

### Database
- Schema summary from Liquibase

### Development
- mvn clean install
- mvn test -pl {module}
- Integration tests: mvn verify -pl {name}-integration-test
```

## Common Module Patterns

### Event Source Subscription
Look in `*-event-sources` for `@Handles` annotations or event handler methods — these show which domain events from other contexts trigger processing in this service.

### Interceptor Chain
Check for `*InterceptorChainProvider.java` — custom interceptor chains may override default audit/auth behaviour. If absent, the service uses the framework default (audit + access control on all APIs).

### View Store Projections
The `-event-sources` module typically contains projection logic that transforms domain events into viewstore entities. This is the CQRS projection — the bridge between the event store and the read model.
