# Skill: Code Review Checklist (HMCTS overlay)

The generic checklist has moved to the [agentic-plugins-marketplace](https://github.com/hmcts/agentic-plugins-marketplace).

Install the generic plugin first:

```
/plugin install review-checklist@agentic-plugins-marketplace
```

The generic plugin covers: Correctness, Test quality, Security, Code quality, Dependencies, Documentation, and Scoring. Accessibility is handled by the separate `accessibility-check` plugin.

This overlay adds HMCTS-specific additions the `code-reviewer` agent must apply on top of the generic checklist.

---

## HMCTS-specific additions

### Test quality (extra)
- [ ] No real PII or court reference numbers in test data

### Integration tests (extra — backend features & bugfixes)
- [ ] At least one integration test per new/changed endpoint (REST resource, `@Handles` action, message-driven entry point)
- [ ] The IT exercises the real persistence/SQL + event path — not just unit tests that mock the repository
- [ ] Integration-test suite is green locally (`mvn clean && ./runIntegrationTests.sh` when present); summary pasted in the PR

### Pipeline artifacts (extra)
- [ ] An implementation-plan HTML artifact exists at `docs/pipeline/artifacts/` (exported via `skills/export-design-artifact/`) and the change matches it
- [ ] Decisions made and design gaps found during the work were captured as artifacts and surfaced at a gate

### Security (extra)
- [ ] No connection strings, SAS tokens, or account keys — Managed Identity only (see `context/azure-sdk-guide.md`)
- [ ] No PII in log statements
- [ ] No new Critical or High Snyk findings introduced

### Spring Boot template alignment (Spring Boot services)
- [ ] `build.gradle`, `gradle/*.gradle`, `Dockerfile`, `logback.xml`, `.github/workflows/` unchanged from template (or ADR recorded)
- [ ] `spring.application.name` and `management.metrics.tags.service` match the repo name
- [ ] Java package consistent with naming convention; no template placeholder left behind
- [ ] Template sample code (e.g., `ExampleController`) removed if not kept intentionally

### Logging (JSON mandatory)
- [ ] Logs are JSON to stdout via `logstash-logback-encoder` (see `context/logging-standards.md`)
- [ ] MDC contains `correlationId` and `requestId` on every request
- [ ] No Authorization/Cookie headers, secrets, or PII in log output
- [ ] Log levels used correctly: WARN for expected business errors, ERROR for unexpected failures

### Cloud-Native / Azure
- [ ] Container runs as non-root (`USER app`); base image from HMCTS ACR
- [ ] Liveness/readiness probes wired to Spring Boot Actuator health groups
- [ ] Graceful shutdown, HTTP/2, forward-headers strategy unchanged from template
- [ ] All config via env vars; no hardcoded endpoints or credentials
- [ ] Managed Identity assigned via Helm; workload identity annotation present

### Accessibility (UI stories only)
Run the `accessibility-check` skill (install `accessibility-check@agentic-plugins-marketplace` + apply the HMCTS overlay at `.claude/skills/accessibility-check.md`).

### Dependencies (extra)
- [ ] Licence compatible with HMCTS/MOJ policy — no GPL

### HMCTS scoring overrides
- Any FAIL in **Accessibility** (UI story) → **block merge, must fix** (HMCTS treats a11y failures as equivalent to security failures)
- Any unresolved **PII leak** in logs or test data → **block merge, must fix**
- Any **new/changed endpoint without an integration test**, or an IT suite that is not green → **block merge, must fix**
- **No implementation-plan artifact** at `docs/pipeline/artifacts/` for a backend feature/bugfix → **block merge, must fix**
