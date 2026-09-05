---
name: entra-token-validation
description: Use when the user wants to audit, review, add or fix Microsoft Entra JWT access token validation in a service-cp-* Spring Boot service — checks signature and algorithm pinning, aud/iss/exp/tid/ver claims, app-only enforcement, endpoint exemption coverage, AUTH_MODE rollout config, and the per-repo conformance suite. Returns a scored report with Critical/Warning/Info findings, then offers to apply the fixes.
---

# Skill: Entra Token Validation

The runtime counterpart to `openapi-spec-reviewer`. That skill checks what a spec **declares** in
`components/securitySchemes`; this one checks what the service actually **enforces** at request time.

## Trigger

Invoke when a user asks to:

- Audit, review or check token validation, JWT validation, or authentication in a `service-cp-*` repo
- Confirm a service is conformant with the Entra access token standard
- Add token validation to a service that trusts an unverified claim
- Diagnose why tokens are being rejected (or accepted when they should not be)

Invocation command: `/entra-token-validation`

**Scope: `service-cp-*` runtime services only.** For a spec's declared security schemes, use
`openapi-spec-reviewer` instead.

---

## Prerequisites

Load and internalise both knowledge documents before auditing. They are bundled with this skill in
its `knowledge/` directory (resolve relative to this `SKILL.md`):

- `knowledge/validation-standard.md` — the decisions and traps behind each check
- `knowledge/conformance-suite.md` — the test cases a conformant repo must carry

Then locate the service's own auth code. Do not assume package names — find them:

```bash
grep -rn "azp\|JWKSource\|DefaultJWTProcessor\|NimbusJwtDecoder\|Authorization" src/main --include='*.java' -l
```

If the service has **no** token validation at all, say so plainly, report it as a single Critical
finding, and go straight to the Remediation stage — do not emit five empty lenses.

---

## Audit process

Work through five lenses. For each finding record the **file and line**, so the report is
navigable and so the remediation stage has an anchor.

Read the code before judging it. Several checks in the standard are deliberate *omissions* with a
recorded rationale — flagging those as gaps is a false positive, and the standard names them.

### Lens 1 — Signature and algorithm

The verifier must pin exactly one algorithm in its own configuration, not read `alg` from the token
header and not infer it from the key set (Entra's JWKS entries carry no `alg`).

Confirm the key selector is constructed for a single algorithm against the configured JWKS, and that
nothing in the token can influence which key is used. If so, `alg: none`, algorithm confusion and
header-supplied key material are structurally impossible — record that as the reason, rather than
looking for three separate defences.

### Lens 2 — Claims

Check each claim in §3 of the standard: `aud` against this API's own audience, `iss` by **exact**
match, `exp` **required**, `nbf` when present, `tid`, `ver` = `2.0`, the authorised-party claim as a
UUID identity, `roles` non-empty, `scp` prohibited.

Two things to check specifically, because they are the common real defects:

- An issuer matched by prefix or `contains` rather than exactly.
- An identity taken from `oid`/`sub` rather than `azp`.

App-only must be proven by `sub == oid` plus roles plus absent `scp` — **not** by `idtyp`. If the
code requires `idtyp`, that is Critical: it rejects all legitimate traffic.

### Lens 3 — Endpoint coverage

Find the exemption list. A **prefix rule is a Critical finding** — it silently leaves endpoints
outside the prefix unprotected and cannot be enumerated against the contract.

Verify exemptions are matched exactly, that each is justified, and that a test enumerates the
contract's paths so a new endpoint fails until classified.

Check for a mock or test callback controller registered without a profile condition.

Where an internal producer endpoint is exempt because producers send no `Authorization` header at
all: that is a **gateway segregation** problem, not a code defect. Report it as Info with the
consequences made explicit (no attribution; protected by network controls only), and do not propose
an internal role — requiring any role stops the integration.

### Lens 4 — Configuration and rollout

Confirm startup **fails** rather than degrades: a blank audience must never mean "accept any", and a
non-enforcing mode must be rejected in deployed environments.

Check the clock skew is capped, that the tenant configured is the **issuing** tenant, and that
per-environment values are actually set — defaults that are non-blank but belong to one environment
start everywhere and reject every token elsewhere.

If the service is running in a non-enforcing mode in any deployed environment, that is Critical.

### Lens 5 — Conformance suite, errors and observability

Walk `knowledge/conformance-suite.md` and mark each case present, missing, or vacuous. Report
missing signature-attack cases as Critical — they are the reason the suite exists.

Also check: 401 vs 403 mapped deliberately; RFC 6750 error codes; the exception carries a coarse
reason and never token material; success and failure counters exist **and are actually scrapeable**.

---

## Output Format

---

### Entra Token Validation Report

**Service:** `<repo name>`
**Auth mode:** `<configured mode, and the mode in each deployed environment if determinable>`
**Review date:** `<today's date>`

---

#### Lens 1: Signature and Algorithm

| Severity | Location | Issue | Recommended Fix |
|----------|----------|-------|-----------------|
| Critical / Warning / Info | `path/to/File.java:NN` | Description of issue | What to change |

*(Repeat rows per finding. If none: "No issues found.")*

---

#### Lens 2: Claims

| Severity | Location | Issue | Recommended Fix |
|----------|----------|-------|-----------------|

---

#### Lens 3: Endpoint Coverage

| Severity | Location | Issue | Recommended Fix |
|----------|----------|-------|-----------------|

---

#### Lens 4: Configuration and Rollout

| Severity | Location | Issue | Recommended Fix |
|----------|----------|-------|-----------------|

---

#### Lens 5: Conformance Suite

| Severity | Case | Status | Recommended Fix |
|----------|------|--------|-----------------|
| Critical / Warning / Info | Case name from the conformance suite | Missing / Vacuous | What to add |

---

### Summary

| Lens | Verdict | Critical | Warning | Info |
|------|---------|----------|---------|------|
| Signature and Algorithm | PASS / FAIL | N | N | N |
| Claims | PASS / FAIL | N | N | N |
| Endpoint Coverage | PASS / FAIL | N | N | N |
| Configuration and Rollout | PASS / FAIL | N | N | N |
| Conformance Suite | PASS / FAIL | N | N | N |

**Overall Conformance Score: XX / 100**

Score calculation:
- Start at 100
- Deduct 10 points per Critical finding
- Deduct 3 points per Warning finding
- Deduct 1 point per Info finding
- Minimum score is 0

A lens is **PASS** if it has zero Critical findings, **FAIL** otherwise.

---

### Entra prerequisites to confirm

List any finding that **cannot be fixed in code** — role assignment and admin consent,
`requestedAccessTokenVersion`, optional claims, per-environment audience values, APIM product
segregation. Say explicitly who owns each. Code cannot compensate for a claim the token does not
carry, and reporting these as code defects wastes the reader's time.

---

## Remediation

After presenting the report, offer to apply the fixes:

> I can fix N of these in code. M require Entra or APIM changes and are listed separately.
> Shall I apply the code fixes?

**Wait for confirmation. Never apply fixes as part of the audit.**

When applying:

1. **Order by severity** — Critical first. Stop and re-report if a fix turns out to need a decision
   the user has not made.
2. **A fix is not complete without its conformance test.** Every behaviour change lands with the
   corresponding case from `knowledge/conformance-suite.md`.
3. **Verify each test fails without the fix.** A conformance test that passes against the unfixed
   code is asserting nothing. Check it, and say so in the summary.
4. **Never widen the audience, relax the issuer match, or add a claim to the exempt list** to make a
   test pass. If a legitimate caller is rejected, the token or the Entra registration is wrong, not
   the validator.
5. **Never introduce a non-enforcing mode as a fix.** `OBSERVE` is a diagnostic step for finding
   broken clients before enforcing; it provides no protection and is not a remediation.
6. Follow the repo's existing conventions — the plugin's `context/service-shared.md` and
   `context/shared-code-rules.md` apply.
7. **Keep the prose terse.** See below. This is not a stylistic nicety — code shipped with
   paragraph-length rationale gets hand-edited back down every time, so writing it is rework.

Report honestly at the end: what was fixed, what was skipped and why, and which items remain open
with Entra or APIM.

### House style — write it short the first time

The standard in `knowledge/` is long because it records decisions and traps. **The code you write
from it is not.** Everything that document explains has already been written down; repeating it in
Javadoc duplicates it in the place that ages worst.

| Where | Write |
|---|---|
| Class and method Javadoc | **One summary line.** No `<p>` rationale paragraphs, no explanatory `@param` prose |
| A check whose *removal* would be a security regression | One short line at the point of the check — e.g. that `idtyp` must not be required, that `sub == oid` is what proves app-only, that the issuer is matched exactly |
| `build.gradle` dependency comments | One short line — `// Entra access token validation` |
| `application.yaml` | One comment line above the `auth:` block |
| `docs/Authentication.md` (or equivalent) | The operational reference only: config table, claims table, exempt path list, Entra prerequisites, how to run locally |
| `README.md` | **One line** under `### Key Documentation` linking the doc. Nothing else |
| PR description | The repo template's sections, one short paragraph, a few bullets, and anything operationally load-bearing — deployment prerequisites and the breaking-change box. Point at the doc in the repo instead of restating it |

Do **not** write:

- A section justifying a design choice ("Why Nimbus rather than Spring Security"). It is a
  legitimate either-way decision — state it in the chat reply, not in the repo.
- A table or list inventorying the test suite and what each test covers. The test names do that.
- A paragraph explaining why exact matching beats prefix matching, why a counter is separate from
  another counter, or why an exception does not carry a cause. One line, or nothing.
- A `> **Before this is deployed...**` callout in `README.md`. Deployment prerequisites belong in
  the doc and in the chat reply.

The rationale is wanted — in the **chat response**, where it informs the reviewer and then goes
away. It is not wanted in the source tree.

---

## Severity Definitions

| Severity | Meaning |
|----------|---------|
| **Critical** | A caller can be impersonated, an unintended token accepted, or a protected endpoint reached without one. Also: a non-enforcing mode in a deployed environment, and missing signature-attack conformance cases. Must be resolved. |
| **Warning** | Meaningful risk or a real gap in the conformance suite, but not directly exploitable as configured. Resolve before the next release. |
| **Info** | Improvement, or a known gap owned elsewhere (gateway segregation, role assignment). Does not block. |
