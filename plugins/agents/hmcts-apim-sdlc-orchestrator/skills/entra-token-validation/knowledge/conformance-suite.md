# The per-repo conformance suite

There is deliberately **no shared authentication library** across CP services. The agreed model is a
common standard plus a **conformance suite in each repo** that proves the service meets it.

That makes the tests the contract. A service that validates correctly but cannot demonstrate it is
not conformant, because the next refactor has nothing to fail against.

---

## How to audit the suite

Look for a test class that exercises the validator directly against a locally-minted JWKS — signing
test tokens with a key the test controls, so signature, issuer, audience, expiry and claim rules all
run for real. Stubbing the validator, or asserting only on happy-path acceptance, does not count.

For each case below, decide: **present**, **missing**, or **present but vacuous** (asserts nothing
that would fail if the check were removed).

Do not require the exact names used here. Match on what the test *does*.

---

## Required cases

### Acceptance

| Case | What it proves |
|---|---|
| A well-formed app-only token is accepted and yields the caller's client id | The happy path, and that identity comes from the right claim |
| A token **without `idtyp`** is accepted | Guards against someone "hardening" the app-only check into an outage. **This is the highest-value regression test in the suite** |
| The client id is the authorised-party claim, never the object id | The registry-seeding trap |
| Expiry inside the configured clock skew is tolerated | Skew is actually applied |

### Header and scheme handling

| Case | What it proves |
|---|---|
| Missing `Authorization` header rejected | |
| Blank `Authorization` header rejected | |
| Non-Bearer scheme rejected | |
| Empty bearer token rejected | |
| The Bearer scheme is matched **case-insensitively** | RFC 6750 §2.1 — a case-sensitive match rejects legitimate clients |
| Structurally malformed tokens rejected | |
| A token whose payload is not JSON rejected | |

### Signature — the attack cases

These are the reason the suite exists. All must be present.

| Case | What it proves |
|---|---|
| An **unsigned** token (`alg: none`) is rejected | |
| **HS256 signed with the JWKS RSA public key** is rejected | Algorithm confusion. The single most important negative test |
| A token signed by an unrelated key is rejected | |
| A tampered signature is rejected | |
| An unknown `kid` is rejected | |
| An unsupported **critical header** is rejected | |
| **Key material supplied in the token header is ignored** | `jku`/`jwk`/`x5u` cannot nominate the verifying key |

### Audience and issuer

| Case | What it proves |
|---|---|
| A **Microsoft Graph** token is rejected on audience | The standard onboarding mistake |
| A token minted for a **sibling CP API** is rejected on audience | The spike-GUID mistake |
| A wrong issuer is rejected | |
| An issuer that merely **starts with** the expected value is rejected | Prefix-match vulnerability |

### Time and tenancy

| Case | What it proves |
|---|---|
| An expired token is rejected | |
| A token **without** `exp` is rejected | `exp` is required, not optional |
| A not-yet-valid token is rejected | |
| A wrong tenant id is rejected | |
| A **v1.0** token is rejected | |

### Identity and app-only

| Case | What it proves |
|---|---|
| A missing authorised-party claim is rejected | |
| A non-UUID authorised-party claim is rejected | |
| A **delegated token is rejected on `sub != oid`** | |
| A **token carrying `scp` is rejected** | |
| A token without roles is rejected | |
| A token with an empty roles array is rejected | |

### Non-enforcing modes and leakage

| Case | What it proves |
|---|---|
| The unverified extraction path validates nothing and flags the caller unverified | The `OFF`/`OBSERVE` path cannot be mistaken for a verified one |
| **The exception never carries token material** | Leakage guard |

---

## Beyond the validator

| Case | Where |
|---|---|
| Every exempt path is exempt, and near-miss paths (`/thing/x`, `/thingx`) are **not** | Authorization-policy test |
| The contract's paths are **enumerated**, so a new endpoint fails until classified | Policy or contract test |
| Startup **fails** when the audience is blank and the mode is enforcing | Configuration test |
| Startup **fails** for a non-enforcing mode in a deployed environment | Configuration test |
| Clock skew is capped | Configuration test |
| Exempt infrastructure endpoints answer **without** a token, through the real filter chain | Integration test |
| Protected endpoints reject an absent or invalid token, through the real filter chain | Integration test |

Integration tests must run with enforcement **on**, supplying the signing key in-process as the
application's JWKS. Running them with validation disabled stops them covering the authentication
path at all — a common and quiet regression.
