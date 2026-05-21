---
name: context-scaffold
description: Scaffold new modules, commands, queries, events, or viewstore entities within an existing legacy cpp-context-* WildFly service. LEGACY ONLY — must not be applied to new Spring Boot work.
---

> ⚠️ **Legacy WildFly context services only.** The CQRS scaffolding here — `-command-api`, `-query-api`, `-domain-event`, viewstore + Liquibase, subscriptions-descriptor — is **specific to the WildFly-era `cpp-context-*` stack**. Do **not** copy these patterns into a Spring Boot service. Spring Boot services are layered (Controller → Service → Repository with MapStruct), not CQRS.
>
> For **new Spring Boot services**, use `skills/springboot-service-from-template/`.
> For **new HMCTS Marketplace API specs**, use `skills/springboot-api-from-template/`.
> If a domain genuinely needs CQRS in a new Spring Boot service, that is an ADR-worthy deviation — raise it explicitly rather than importing this skill's patterns.

# Context Service Scaffold

Generates boilerplate for new CQRS components within an existing `cpp-context-*` repository — commands, queries, domain events, viewstore entities, and Liquibase migrations.

## When to Use

- User asks to "add a new command", "create a query", "add a domain event"
- User wants to add a new aggregate or entity to the domain
- User needs a new viewstore table with Liquibase migration
- User wants to add event subscription from another context

## Component Templates

### New Command

When the user wants to add a new command:

1. **Command API** (`{name}-command/{name}-command-api/`)
   - RAML definition under `src/raml/`
   - JSON schema under `src/raml/json/schema/`
   - Follow existing naming: `{context}.command.{verb}-{noun}.json`

2. **Command Handler** (`{name}-command/{name}-command-handler/`)
   - Handler class implementing the command processing
   - Follow pattern: `{Verb}{Noun}CommandHandler.java`
   - Must validate invariants via the aggregate
   - Must produce domain events on success

Example command schema naming:
```
hearing.command.schedule-hearing.json
hearing.command.update-hearing-details.json
hearing.command.cancel-hearing.json
```

### New Query

When the user wants to add a new query:

1. **Query API** (`{name}-query/{name}-query-api/`)
   - RAML definition
   - Response JSON schema

2. **Query Handler** (`{name}-query/{name}-query-handler/`)
   - Handler class that reads from the viewstore
   - Must use `readOnly=true` transactions
   - Never modify state

### New Domain Event

1. **Event Schema** (`{name}-domain/{name}-domain-event/src/main/resources/json/schema/`)
   - JSON schema file: `{context}.events.{noun}-{past-tense-verb}.json`
   - Example: `hearing.events.hearing-scheduled.json`, `hearing.events.hearing-cancelled.json`

2. **Event naming convention**: Events are past-tense facts — something that happened.
   - `material-added` (not `add-material`)
   - `hearing-scheduled` (not `schedule-hearing`)
   - `defendant-validation-passed` (not `validate-defendant`)

### New Viewstore Entity

1. **JPA Entity** (`{name}-viewstore/`)
   - Entity class with `@Entity`, `@Table` annotations
   - Repository interface extending `JpaRepository`

2. **Liquibase Migration** (`{name}-viewstore-liquibase/`)
   - New changeset in `db/changelog/`
   - Follow sequential numbering from existing changesets
   - Include rollback section

Example Liquibase changeset:
```xml
<changeSet id="YYYYMMDD-01" author="developer-name">
    <createTable tableName="new_entity">
        <column name="id" type="uuid">
            <constraints primaryKey="true" nullable="false"/>
        </column>
        <column name="created_at" type="timestamp with time zone">
            <constraints nullable="false"/>
        </column>
    </createTable>
    <rollback>
        <dropTable tableName="new_entity"/>
    </rollback>
</changeSet>
```

### New Event Subscription (from another context)

When this service needs to react to events from another bounded context:

1. **Add dependency** in root `pom.xml`:
   ```xml
   <dependency>
       <groupId>uk.gov.moj.cpp.{other-context}</groupId>
       <artifactId>{other-context}-event</artifactId>
       <version>${other-context.version}</version>
   </dependency>
   ```

2. **Event source handler** in `{name}-event-sources/`:
   - Handler method annotated to process the external event
   - Must be idempotent — check if event already processed
   - Transform external event data into local viewstore updates

## Process

1. Ask the user what component they want to add
2. Read the existing repo structure to understand naming patterns and conventions
3. Read at least one existing example of the same component type in the repo
4. Generate the new component following the exact same patterns
5. If adding a viewstore entity, also generate the Liquibase migration
6. If adding a command, also create the corresponding domain event(s)
7. Remind the user to run `mvn clean install` to verify the build

## Validation

After scaffolding, verify:
- `mvn clean compile` — all modules compile
- `mvn test -pl {affected-module}` — existing tests still pass
- JSON schemas validate against the framework's meta-schema
- RAML files reference the correct schemas
- Liquibase changesets have unique IDs and include rollback
