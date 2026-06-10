# hmcts-apim-sdlc-orchestrator — Team Demo

**Audience:** APIM engineering team
**Duration:** ~6 minutes
**Repo used:** `service-cp-crime-hearing-results-document-subscription`

---

## What we built and why

We looked at `hmcts-sdlc-orchestrator` — great plugin, but built for the CQRS stack.
Our world is API-first, Modern by Default — different CI, different deploy chain, different
rules. So we built a dedicated one.

The idea is simple: describe what you want to build, Claude drives the pipeline, you
approve at the key decisions. Requirements, stories, tests, code review, SIT release —
those are yours. Everything else is guided.

---

## Live Command Flow

### 1. Install — one command

```
/plugin install hmcts-apim-sdlc-orchestrator@agentic-plugins-marketplace
/reload-plugins
```

Done. Works for every `api-cp-*` and `service-cp-*` repo in the org.

---

### 2. Open a repo — context loads automatically

Open `service-cp-crime-hearing-results-document-subscription` in Claude.
The status bar shows:

```
hmcts-apim-sdlc-orchestrator: context bootstrapped for service-cp-crime-hearing-results-document-subscription
```

No manual wiring. The `SessionStart` hook creates the gitignored `.claude/CLAUDE.md`
with the correct imports every time you open the repo. `/bootstrap-context` is available
if you ever need to force an update, but you won't need it day-to-day.

---

### 3. Kick off the pipeline — one sentence

```
I want to add a filter by document type to the subscription service
```

Claude identifies this as **Path B** (service feature), confirms the `api-cp-*` spec is
published, and kicks off `requirements-analyst`.

---

### 4. Human gate 1 — Requirements

Claude produces `docs/pipeline/requirements.md` and stops:

> *"Here are the requirements. Review and confirm before I move to stories."*

Review it, then:

```
looks good, proceed
```

---

### 5. Stories

`story-writer` produces user stories linked to the actual OpenAPI endpoint:

```
Implements: GET /subscriptions/{id}/documents
from api-cp-crime-hearing-results-document-subscription v1.2
```

Not generic stories — grounded in the published contract.

---

### 6. Human gate 2 — Tests

`contract-test-engineer` scaffolds failing Pact + Spring Boot tests and stops:

> *"Test scaffolding ready. Approve to start implementation."*

```
approved
```

---

### 7. Implementation — TDD

Claude confirms tests are failing first:

```bash
./gradlew test 2>&1 | tail -20
```

Then implements in the correct order — mapper → service → controller. Runs tests again:

```bash
./gradlew test        # green
./gradlew pmdMain     # zero violations
```

---

### 8. Human gate 3 — Code review

`code-reviewer` runs the 11-category checklist and surfaces findings:

```
✓ Controller implements DocumentSubscriptionApi (generated interface)
✓ CJSCPPUID set on MaterialClient backend call
✓ No .builder() in service layer
✓ Jakarta EE imports only — no javax.*
✓ Feature toggle T1–T5 rules satisfied
```

```
approved, raise the PR
```

---

### 9. PR raised and deployed

```bash
gh pr create --title "feat(HRDS-042): filter subscriptions by document type"
```

Merged to main → CI runs automatically → dev deploys via ADO pipeline 460/434.
No extra steps. SIT deploys on GitHub Release when you're ready.

---

### 10. Catalog sync — bonus

If the spec title or description changed in the merge:

```
the spec title changed in the latest merge — sync the catalog
```

`catalog-publisher` reads the live spec from GitHub Pages, compares against
`amp-catalog/docs/apis.json`, and raises a PR to the catalog automatically.

> *"PR raised to amp-catalog with updated title. Done."*

---

## What the pipeline looks like end-to-end

```
Path B (service-cp-* feature)

requirements-analyst  →  [YOU APPROVE]
story-writer          →  stories linked to OpenAPI endpoints
contract-test-engineer →  [YOU APPROVE]  ← failing tests first
implementation        →  TDD: red → green → refactor
code-reviewer         →  [YOU APPROVE]
ci-orchestrator       →  GHA + ADO pipeline (auto)
deployer              →  dev (auto on merge) / SIT (YOU trigger via release)
catalog-publisher     →  syncs amp-catalog if spec metadata drifted (auto)
```

---

## Key rules baked in

| Rule | Why |
|---|---|
| Contract-first | Service build blocked until `api-cp-*` spec is published |
| TDD | Failing tests before any implementation code |
| Mapper-first | All object construction in MapStruct mappers — no `.builder()` in services |
| Generated interface | Controllers must `implement` the generated API interface |
| CJSCPPUID | Set on every CP backend call |
| PMD not SonarQube | Correct quality gate for this stack |
| Jakarta EE | No `javax.*` imports |
| T1–T5 toggle rules | Feature toggle placement enforced |

---

## Roadmap

- `catalog-sync.yml` — true GHA automation for catalog registration (no Claude session needed)
- `authentication-auditor` — TBD pending authZ/authN design
- `api-dependency-analyzer` — breaking-change detection across `api-cp-*` versions
- AMP-428 (`openapi-spec-reviewer`) — TBD, pending discussion with @Samir.garg

---

*Still evolving — feedback welcome. Ping the team channel or raise an issue in `agentic-plugins-marketplace`.*