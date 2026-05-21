# HMCTS Engineering Standards

## Overview
All work on this project must comply with the following standards.
Agents must check against these before producing any artefact or code.

---

## GDS Service Manual principles
All services must follow the GDS Service Standard. Key requirements:
- Understand users and their needs before building
- Use simple, clear language — Plain English, reading age ≤9
- Make the service accessible (WCAG 2.1 AA minimum)
- Design for the full journey, including assisted digital
- Test with real users, including those with access needs

Reference: https://www.gov.uk/service-manual

---

## Accessibility
- **Standard**: WCAG 2.1 AA — non-negotiable for all user-facing output
- **Components**: Use GOV.UK Frontend — do not rebuild what already exists
- **Testing**: axe-core automated + manual keyboard and screen reader check
- **Audit**: HMCTS requires an accessibility statement for public-facing services

---

## Security
- **Classification**: Treat all case data as OFFICIAL-SENSITIVE unless told otherwise
- **PII**: No personally identifiable information in logs, error messages, or test data
- **Court references**: No real case numbers, hearing dates, or party names in artefacts
- **Auth**: All services behind IDAM (HMCTS Identity and Access Management)
- **Secrets**: Azure Key Vault only — no `.env` files committed to repos
- **OWASP**: All services must be assessed against OWASP Top 10

## Coding in the Open
- New HMCTS repositories are created **public**. This is an MoJ/HMCTS policy, not a default to override casually.
- Do not create a private repo, and do not pass `--private` to `gh repo create`, unless an ADR has been accepted that documents a legal or classification constraint requiring it.
- Because the code is public from day one, secrets, credentials, connection strings, tokens, and PII must never be committed — not in code, config, env vars, fixtures, test data, or commit history. Treat every commit as publicly searchable forever.

## Repository ownership
- Every new HMCTS repository must be owned by a GitHub team in the `hmcts` org. The owning team is captured **before** the repo is created, validated via `gh api /orgs/hmcts/teams/{slug}`, and granted `admin` on the repo immediately after creation.
- Unowned repos are forbidden. If no owning team exists yet, the team must be created first (an org-owner action) — the repo creation halts until that is done.
- User-only ownership (no team grant) is not acceptable even transiently, because it leaves the repo orphaned when the user leaves or loses access.

## API-first design (API repo precedes service)
- Every HMCTS Spring Boot service has a matching **API repo** (`api-...`) that owns the contract. The API repo comes **first**. Create and publish the API spec before — or in parallel with, but ahead of — the service that implements it.
- The split is deliberate. The contract evolves on its own cadence, driven by consumer needs and cross-team agreement, not by the implementation team's sprint. Collapsing them into one repo couples contract design to service delivery and creates pressure to ship whatever the service happened to build.
- The service repo consumes the API artefact as a build dependency — see the `apiSpec` configuration in `service-hmcts-crime-springboot-template/build.gradle`. The published artefact coordinate replaces the template placeholder `uk.gov.hmcts.cp:api-hmcts-crime-template:X.Y.Z` with the service's own API repo coordinate.
- **Resist jumping to code.** If a team proposes starting service implementation before an API spec exists and has been reviewed by consumers, halt and insist on the API repo first. Use `skills/springboot-api-from-template/` before `skills/springboot-service-from-template/`.
- Repo-pair naming convention: `api-{source-system}-[case-type]-{business-domain}-{entity}` and `service-{source-system}-[case-type]-{business-domain}-{entity}` share the suffix. The pair is obvious from names alone.

---

## Coding standards
- Java: Google Java Style Guide + HMCTS team conventions
- Commits: Conventional Commits format (`feat:`, `fix:`, `test:`, `chore:`)
- Branch names: `feature/PROJ-NNN-short-description`
- PR titles must include the Jira ticket number
- No direct commits to `main` — all changes via PR with ≥1 human approval

---

## Test pyramid and coverage
| Layer         | Coverage target       | Framework             |
|---------------|-----------------------|-----------------------|
| Unit          | ≥80% on new code      | JUnit 5 + Mockito     |
| Integration   | All AC happy paths + top 3 failures | Spring Boot Test |
| Contract      | All inter-service calls | Pact              |
| Accessibility | Zero violations       | axe-core              |
| Smoke         | Critical path only    | Cucumber @smoke       |

---

## Story and ticket conventions
- Stories must be in the Jira project board before implementation starts
- ACs must be in Given/When/Then format
- Definition of Done must be checked before transitioning to Done
- `claude-generated` label applied to all AI-generated artefacts for audit purposes

---

## Cloud-Native posture
- HMCTS services run on Azure. Design and build to take advantage of Azure, not to treat it as a generic VM host.
- The Shared Responsibility Model governs where team accountability ends and Azure's begins. Managed services reduce what the team owns and are preferred when they cover the requirement. See `context/azure-cloud-native.md` for the full posture.
- Azure SDK + Managed Identity are the default integration path. Connection strings, SAS tokens, and account keys are not permitted. See `context/azure-sdk-guide.md`.
- "Vendor lock-in" and "cloud is too expensive" objections have specific rebuttals in `context/cloud-adoption-rationale.md` (on-demand reference, not auto-loaded). TCO is the only honest framing for cost debates.

---

## Architecture decision records
An ADR is required for:
- Any new external dependency
- Any deviation from this tech stack
- Any security or data handling decision
- Any integration pattern not previously used on the project

ADRs are stored in `docs/pipeline/adrs/` and reviewed by the tech lead.

---

## Data protection
- Data Protection Act 2018 and UK GDPR apply
- Do not store or process personal data beyond what the service requires
- Data retention periods must be defined and enforced
- Subject access requests must be supportable by the service design
