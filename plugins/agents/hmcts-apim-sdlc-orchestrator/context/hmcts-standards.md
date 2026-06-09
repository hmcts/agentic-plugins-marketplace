## HMCTS Engineering Standards (API Marketplace)

Cross-cutting HMCTS standards that apply to all `api-cp-*` and `service-cp-*` work.
These complement `shared-code-rules.md`, `service-shared.md`, and `api-spec-shared.md` —
do not duplicate rules that already live in those files.

No accessibility standards apply here — the API Marketplace has no user-facing UI.

---

### Security classification

Treat all case data as **OFFICIAL-SENSITIVE** unless explicitly told otherwise.
- No PII in logs, error messages, API responses, test data, or spec examples
- No real case reference numbers, hearing dates, or party names in artefacts, commits, or fixtures
- Every new external dependency assessed against OWASP Top 10 before merging
- OWASP ZAP DAST scan is wired in `codeql.yml` — treat findings as blockers for Critical/High

---

### Coding in the Open

New HMCTS repos are **public** by default. This is MoJ/HMCTS policy, not a preference.
- Do not pass `--private` to `gh repo create` without an ADR recording a legal or classification constraint
- Because code is public from day one: secrets, credentials, connection strings, tokens, and PII must **never** be committed — not in code, config, env vars, fixtures, test data, or commit history
- Treat every commit as publicly searchable forever

---

### Repository ownership

A GitHub team in the `hmcts` org must own every new repo **before** it is created:
1. Validate: `gh api /orgs/hmcts/teams/{team-slug} --jq '.slug, .name'`
2. If the team does not exist, halt — ask an org-owner to create it first
3. Immediately after repo creation: `gh api --method PUT /orgs/hmcts/teams/{slug}/repos/hmcts/{repo} -f permission=admin`

User-only ownership is not acceptable, even transiently.

---

### Architecture decision records (ADRs)

An ADR (`docs/pipeline/adrs/<NNN>-<title>.md`) is required before proceeding for:
- Any new external dependency
- Any deviation from the HMCTS template (`build.gradle`, `gradle/*.gradle`, `Dockerfile`, `logback.xml`, `.github/workflows/`)
- Any security or data handling decision
- Any integration pattern not previously used (e.g. self-hosted queue vs Service Bus)
- Any breaking change to an `api-cp-*` contract
- Any private repo creation

ADRs are reviewed by the tech lead before the relevant stage begins.

---

### Data protection

- Data Protection Act 2018 and UK GDPR apply to all case, hearing, and party data
- Do not store or process personal data beyond what the service requires
- Data retention periods must be defined and enforced via Flyway migrations or explicit delete jobs
- Subject access requests must be supportable by the service design — log what data is held and where
- No PII in API spec examples, test fixtures, or log output

---

### Conventional Commits

All commits must follow the [Conventional Commits](https://www.conventionalcommits.org/) format:

```
<type>(<scope>): <short summary>

[optional body — wrap at 72 chars]

[optional footer — Jira ticket, breaking change note]
```

Types: `feat`, `fix`, `test`, `refactor`, `chore`, `docs`, `ci`, `revert`

```
feat(subscription): add HMAC signing for outbound callbacks

Signs each callback payload with the client's stored HMAC key.
Key is fetched from ClientHmacEntity; rotation via KeyVault when
AZURE_VAULT_ENABLED=true.

AMP-123
```

Breaking change footer: `BREAKING CHANGE: <description>` — triggers major version bump.

---

### Branch naming

```
feature/PROJ-NNN-short-description
fix/PROJ-NNN-short-description
chore/PROJ-NNN-short-description
```

No direct commits to `main` or `master` — all changes via PR with ≥1 human approval.

---

### Pull request hygiene

- **Title**: must include the Jira ticket — `[PROJ-123] Add HMAC signing for callbacks`
- **Description**: what changed, why, how to test
- **Size**: maximum 400 lines changed per PR; split larger changes
- **Conversations**: all review conversations resolved before merge
- **Branch**: deleted after merge
- `claude-generated` label applied to all AI-generated artefacts for audit trail

---

### Test pyramid (API Marketplace — no UI)

| Layer | Coverage target | Framework |
|---|---|---|
| Unit | ≥80% on new code | JUnit 5 + Mockito |
| Integration | All AC happy paths + top 3 failures | `@SpringBootTest` + Testcontainers |
| Contract | All inter-service calls | Pact |
| API | Full stack via docker-compose | `./gradlew dockerTest` |

No accessibility tests — there is no UI surface in this pipeline.
Smoke test in deployment: `/actuator/health/readiness` returns 200.

---

### Naming conventions

| Element | Convention | Example |
|---|---|---|
| Class | PascalCase, noun or noun phrase | `SubscriptionService`, `CallbackClient` |
| Method | camelCase, verb or verb phrase | `submitCallback`, `findByClientId` |
| Constant | SCREAMING_SNAKE_CASE | `MAX_RETRY_ATTEMPTS` |
| Package | lowercase, domain-first | `uk.gov.hmcts.cp.subscription.services` |
| Unit test class | suffix `Test` | `SubscriptionServiceTest` |
| Integration test class | suffix `IT` | `SubscriptionControllerIT` |
| Test methods | `subject_should_doOutcome` or `subject_should_doOutcome_whenCondition` | `service_should_skipDuplicate_whenEventAlreadyProcessed` |

Mixed test method naming styles within one class are not permitted.

---

### Method size

- Target: ≤20 lines per method
- Hard limit: 40 lines — extract if exceeded
- If a method needs an inline comment to explain a section, that section should be its own method