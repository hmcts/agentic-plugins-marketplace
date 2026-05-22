---
name: api-contract-check
description: Validate API contracts (RAML/JSON Schema/OpenAPI) against their implementations. Use when checking for API drift, reviewing schema changes, or verifying contract consistency.
---

# API Contract Check

Validates that API definitions (RAML, JSON Schema, OpenAPI) match their implementations across CP services.

## When to Use

- User asks to "check API contracts", "validate schemas", "find API drift"
- User has changed a RAML/schema file and wants to verify consistency
- User wants to understand the API surface of a context service
- Before integrating with another context service's API

## Process

### Step 1: Identify API Definitions

#### Legacy Context Services (RAML + JSON Schema)

API definitions live in predictable locations:

```
{name}-command/{name}-command-api/src/raml/
    json/                           # Request payloads
    json/schema/                    # JSON Schema definitions
    {context}.command.{action}.raml # RAML endpoint definitions

{name}-query/{name}-query-api/src/raml/
    json/                           # Response payloads
    json/schema/                    # JSON Schema definitions
    {context}.query.{action}.raml   # RAML endpoint definitions
```

#### Modern by Default Services (OpenAPI/Swagger)

API definitions are generated from annotations:
- `@Operation`, `@ApiResponse` on controller methods
- springdoc-openapi auto-generates `/v3/api-docs`
- Check `src/main/resources/application.yaml` for springdoc config

### Step 2: Cross-Reference with Implementations

For each API definition found:

1. **Command APIs** — verify the command handler processes all fields defined in the schema
2. **Query APIs** — verify the query handler returns all fields defined in the response schema
3. **Event schemas** — verify domain events contain all fields defined in the event schema
4. **Inter-service contracts** — verify consuming services use the same schema version as the producing service

### Step 3: Check Schema Consistency

For JSON Schemas, verify:
- `$ref` references resolve to existing schema files
- Required fields are enforced in handler code
- Enum values match actual usage in code
- Date/time formats follow ISO 8601

For RAML definitions, verify:
- Base URI and resource paths match actual deployment
- Request/response types reference correct schemas
- Media types are correct (`application/vnd.{context}.command.{name}+json`)

### Step 4: Cross-Context Contract Verification

When context A consumes events from context B:

1. Read B's event schema from `{b}-domain/{b}-domain-event/src/main/resources/json/schema/`
2. Read A's event handler that processes B's events
3. Verify A correctly handles all required fields from B's schema
4. Flag any fields A ignores that might be important
5. Check version alignment — A's dependency version of B's event artifact

### Step 5: Generate Report

```
## API Contract Report: [service-name]

### Commands
| Command | Schema | Handler | Status |
|---------|--------|---------|--------|
| {context}.command.{name} | ✅ defined | ✅ implemented | OK |
| {context}.command.{name} | ✅ defined | ❌ missing field X | DRIFT |

### Queries
| Query | Schema | Handler | Status |
|-------|--------|---------|--------|
...

### Domain Events
| Event | Schema | Producer | Status |
|-------|--------|----------|--------|
...

### Cross-Context Contracts
| Consumer | Event | Producer Version | Consumer Version | Status |
|----------|-------|-----------------|-----------------|--------|
...

### Issues Found
- [severity] [description] — suggested fix
```

## Common Content-Type Patterns

CP uses custom media types for command routing:

```
application/vnd.{context}.command.{action-name}+json
application/vnd.{context}.query.{query-name}+json
```

Examples:
```
application/vnd.hearing.command.schedule-hearing+json
application/vnd.usersgroups.command.set-user-details+json
application/vnd.listing.query.get-court-schedule+json
```

The framework routes commands/queries to the correct handler based on the `Content-Type` header. Mismatched content types will cause silent routing failures.

## Use Alongside `cpp-apitests`

When extending tests in `cpp-apitests`, the response assertions in a `*IT.java` are contract checks in disguise. Before adding or changing an assertion:

1. Locate the producing service's contract (RAML for legacy contexts, OpenAPI for Modern by Default services)
2. Confirm the asserted field, type, enum value, and required/optional status match the contract
3. If the test diverges from the contract, the test — not the contract — is wrong; fix the test or open a contract-change ADR

For authoring guidance in `cpp-apitests`, see `cpp-test-authoring`.
