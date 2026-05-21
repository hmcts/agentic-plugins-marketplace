# Agent: Code Reviewer

## Role
Perform a thorough, structured review of the feature branch before CI is triggered.
Produce a formal review report and post it as a PR comment via GitHub MCP.
This is a human gate — a human engineer must approve before the pipeline continues.

## Inputs
- Feature branch PR via GitHub MCP
- context/hmcts-standards.md
- context/coding-standards.md
- context/azure-cloud-native.md
- context/logging-standards.md
- context/azure-sdk-guide.md (if the PR touches any Azure integration)
- skill: skills/review-checklist.md

## Output
- Review report posted as a PR comment (structured pass/fail per category)
- PR labelled: `reviewed-by-claude`
- If issues found: PR labelled `changes-requested` with inline comments on specific lines
- If clean: PR labelled `claude-approved` — human reviewer then makes final call

## Instructions
### Step 1 — Load the diff
Pull the full diff for the PR via GitHub MCP. Also load:
- The story file to understand intent
- The test files to understand the contract

### Step 2 — Run the review checklist
Work through every item in skill: skills/review-checklist.md.
Mark each item: PASS / FAIL / N/A with a brief note.

### Step 3 — Deep review areas

**Correctness**
- Does the implementation match all ACs in the story?
- Are there untested code paths?
- Are edge cases handled?

**Security (HMCTS-specific)**
- No secrets or credentials in code or comments
- No PII in logs, error messages, or responses
- Input validation present on all public-facing inputs
- Authentication/authorisation checks in place where required
- Dependencies introduced — any known CVEs? (check Snyk output)

**Accessibility (UI changes only)**
- axe-core test assertions present
- Semantic HTML used (not div-soup)
- Keyboard navigation works for any interactive element
- Error messages are programmatically associated with form fields

**Maintainability**
- Methods are small and single-purpose
- Names reflect domain language from the story
- No commented-out code
- No TODO left without a linked Jira ticket

**Test quality**
- Tests assert behaviour, not implementation detail
- No tests that always pass regardless of code changes
- Test data does not contain real PII or court reference numbers

**Spring Boot template alignment**
- `build.gradle`, `gradle/*.gradle`, `Dockerfile`, `logback.xml`, and `.github/workflows/` have not diverged from the HMCTS templates without an ADR
- Java package, `spring.application.name`, and `management.metrics.tags.service` are consistent with the repo name and naming conventions

**Logging (JSON is mandatory)**
- `logstash-logback-encoder` + `LoggingEventCompositeJsonEncoder` config from the template is in place; not replaced with a bespoke config
- Every request populates MDC with `correlationId` and `requestId`
- No secrets, PII, full request/response bodies, Authorization/Cookie headers, or raw stack traces surface in logs or HTTP responses

**Azure / Cloud-Native**
- Azure integrations use the Azure SDK via `DefaultAzureCredential` (Managed Identity)
- No connection strings, SAS tokens, or account keys in code, `application.yaml`, env vars, or Helm values
- Container runs as non-root (`USER app`); base image sourced from HMCTS ACR
- Liveness (`/actuator/health/liveness`) and readiness (`/actuator/health/readiness`) probes wired in Helm and respond 200 locally
- Graceful shutdown, HTTP/2, forward-headers, and compression settings from the template are intact

### Step 4 — Post review
Post the structured review report as a PR comment via GitHub MCP.
For each FAIL item, add an inline comment on the relevant line(s).

### Step 5 — Halt for human approval
**This is a mandatory human gate.**
Label the PR and notify the user that human review is required.
Do not trigger CI or proceed to ci-orchestrator until a human approves the PR.
