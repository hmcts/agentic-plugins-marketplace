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

---

## Two traps that cost real time

### The in-process JWKS must be proven to be in use

Supplying the test key set by **overriding the production bean's name** is unreliable: which
definition wins depends on registration order, and when the override silently loses, *every test
still passes*. Each negative case gets its rejection — but from a failed lookup against the real
Entra endpoint, not from the check it was written to exercise. The suite goes green while
asserting nothing, and the tests quietly make network calls.

Two things fix it:

- Register the test key set under **its own bean name, marked `@Primary`**, rather than overriding
  by name with `spring.main.allow-bean-definition-overriding`.
- Carry **one positive case** in the integration test — a token minted by the test is accepted.
  That is the only assertion that can fail when the wrong key set is in use, because every other
  test in the class expects a rejection either way. Without it the trap is undetectable.

### `openapi/openapi-spec.yml` collides across api-cp artefacts

Every api-cp artefact packages its spec at the same resource path. A service that depends on more
than one — its own contract plus any API it calls — has two files with identical names on the
classpath, and `getResourceAsStream` returns whichever the classloader reaches first. That is
usually the wrong one, so the contract-enumeration test reads a spec belonging to a different API
and fails for a reason that has nothing to do with the endpoints.

Enumerate `getResources()` and select the spec by `info.title`, failing with the list of titles
found when there is no match.

The same collision applies to the generated classes — `ErrorResponse` in particular is emitted by
every api-cp artefact under the same FQN, so which definition the service binds against is decided
by classpath order. Worth reporting as an Info observation; it is not a token validation defect.
