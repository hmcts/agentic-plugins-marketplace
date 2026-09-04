# Entra access token validation — the standard

The reference model for in-application validation of Microsoft Entra **app-only** (client
credentials) access tokens in a `service-cp-*` service.

This document records **decisions and traps**. It does not restate what the code says — a service's
own validator and its conformance suite are the authority on behaviour, and they cannot drift from
it. What follows is the part neither can express.

---

## 1. Why in-application validation exists at all

APIM's `validate-jwt` policy already rejects bad tokens from the internet. In-application validation
**duplicates the gateway deliberately**, because it covers the paths the gateway does not see:
in-cluster callers, a port-forward, a misrouted ingress, and any Service Bus path that never
traverses APIM.

The failure mode it closes is specific and severe: where a service base64-decodes a token payload
and trusts a claim from it without a signature check, and that claim is the tenancy key for
repository queries, forging it impersonates any registered client.

**Audit consequence:** "APIM validates it" is not a valid answer to a missing in-app check.

---

## 2. The algorithm must be pinned in code

`alg` appears in three places and only one is trustworthy:

| Where | Present? | Trustworthy? |
|---|---|---|
| The token's JOSE header | Always | **No** — it is part of the token the caller supplies |
| The JWKS key entries | **No** — Entra publishes `kty, use, kid, n, e, x5c, x5t` and no `alg` | Would be, but absent |
| The verifier's own configuration | Pinned | Yes |

The header's `alg` is the *input to the attack*, not a defence. An attacker sets `alg: none` and
strips the signature, or sets `alg: HS256` and signs with the RSA public key from the JWKS as an
HMAC secret — that key is public. A validator that reads `alg` from the header and verifies
accordingly accepts both.

Some providers let you constrain this from the key set, rejecting any token whose header disagrees
with the JWKS entry's `alg`. **Entra does not publish that field, so that route is closed.**

The correct construction is a key selector built for exactly one algorithm:

```java
setJWSKeySelector(new JWSVerificationKeySelector<>(JWSAlgorithm.RS256, jwkSource))
```

A token declaring any other algorithm finds no candidate key and fails before verification is
attempted. This makes `alg: none`, algorithm confusion, and token-supplied key material
(`jku` / `jwk` / `x5u`) **structurally impossible rather than separately defended** — the selector
consults only the configured JWKS.

`"use": "sig"` on the keys separates signing from encryption but says nothing about which signature
algorithm, so it is not a substitute.

---

## 3. Claims: what must be checked, and the trap in each

| Claim | Requirement | The trap |
|---|---|---|
| `aud` | Must equal **this API's own** audience | **The single highest-value check.** It is the only thing that rejects a genuine, correctly signed, unexpired token minted for a *different* resource — a Microsoft Graph token, or a sibling CP API's. A blank or unset audience must fail startup, never mean "accept any" |
| `iss` | **Exact string match** | Never prefix or `contains` — those admit `…/v2.0.attacker.example` |
| `exp` | Required, in the future within the configured skew | Must be *required*, not merely checked when present. A large skew turns `exp` into a no-op, so cap it |
| `nbf` | Checked when present, same skew | — |
| `tid` | Exact match against the issuing tenant | Strictly redundant while `iss` is exact-matched (the issuer contains the tenant). Keep as defence in depth but **do not count it as independent coverage** |
| `ver` | Must be `2.0` | A v1.0 token is rejected by `iss` anyway (`sts.windows.net`), so this documents the decision not to build the v1.0 path |
| `azp` | The caller's identity; must parse as a UUID | **Not `oid`/`sub`.** See §4 |
| `roles` | Present, non-empty, and containing a role this API recognises | A *declared* role is not an *assigned* one — see §6 |
| `scp` | **Prohibited** | Its presence means a delegated (user) token |

### Deliberately not checked

Recorded so they are not re-litigated. Each lacks a threat model in this context: in-app TLS
enforcement (terminates at the ingress, so it degrades to trusting `X-Forwarded-Proto`), token size
limits (the servlet container caps header size first), duplicate JSON keys (the signature covers the
payload), `iat` max age (`exp` already bounds validity; Entra sets `iat == nbf`), `typ` (permitting
what Entra emits rejects nothing an attacker would send), timing-uniform failures (incompatible with
distinct 401/403 semantics), and replay/nonce tracking (bearer tokens are replayable until `exp` by
design; Entra emits `uti`, not `jti`).

Flagging any of these as a finding is **wrong** unless the service has a threat model that justifies
it.

### Never validate, depend on, or log

`aio`, `rh`, `xms_ftd` — undocumented Entra internals that change without notice.

---

## 4. `azp` is the identity, `oid`/`sub` is not

`azp` is the **calling application's client id** and the tenancy key for repository queries.
`oid`/`sub` is the service principal object id for that application in the tenant.

Seeding a client registry with `oid` instead of `azp` produces a signature-valid token that then
403s or 404s — a confusing failure to debug, because nothing is wrong with the token.

---

## 5. App-only is proven by `sub == oid`, never by `idtyp`

`idtyp: app` would be the direct check, but **Entra omits it unless it is explicitly enabled as an
optional claim on the app registration**. Requiring it today rejects all legitimate traffic.

App-only is therefore inferred from three things together:

1. `sub == oid` — for an app-only token Entra sets `sub` to the service principal object id, so they
   are equal. For a delegated token `sub` identifies the user and they differ.
2. `roles` present and non-empty.
3. `scp` absent.

A service should carry a **regression test asserting a token without `idtyp` is accepted**, so that
nobody later "hardens" this into an outage.

---

## 6. Entra prerequisites — code cannot compensate

| Item | Why it matters |
|---|---|
| App registration exposing this API's audience | Without it there is no `aud` to match |
| App roles declared **and assigned, with admin consent** | **A declared role is not an assigned one.** Roles declared without admin consent produce a token that looks entirely correct but silently omits `roles`. Verify by minting a token, not by reading the portal |
| `requestedAccessTokenVersion` pinned to `2` | If it drifts to `1`, `aud` becomes the App ID URI and a GUID-based config rejects everything |
| Per-environment tenant and audience values | See the config trap in §7 |

**Client onboarding:** clients request `scope=<this API's audience>/.default` against
`https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token` — not a Graph scope, and not another
CP API's audience. Either the GUID or `api://` form yields the bare GUID as `aud` on a v2.0 token.

---

## 7. Configuration and rollout

| Setting | Purpose |
|---|---|
| Mode (`OFF` / `OBSERVE` / `ENFORCE`) | Rollout state — see below |
| Tenant id | The **issuing** tenant; derives issuer and JWKS URI |
| Audience | This API's own audience |
| Issuer, JWKS URI | Overrides; derived from the tenant when blank |
| Clock skew seconds | Applied to `exp`/`nbf`; must be capped |
| JWKS cache TTL | So verification costs no outbound call per request |

**Fail startup rather than degrade.** A blank audience must never mean "accept any audience".

### The three modes

- `OFF` — no validation; identity from an unverified claim. The pre-remediation behaviour.
- `OBSERVE` — tokens are fully validated and every failure is logged and counted, but **no request
  is rejected** and identity still falls back to the unverified claim. This is a diagnostic for
  finding broken clients before enforcing. **It provides no protection.**
- `ENFORCE` — validated, and invalid requests rejected.

`OFF` and `OBSERVE` must be **rejected at startup in deployed environments**. Treat any deployed
environment running either as a live incident, not a configuration preference.

### Two traps that bite

- **Defaults that are non-blank but wrong.** If tenant and audience default to one environment's
  values, the service starts everywhere and rejects every token in the others. The failure should be
  loud in metrics, not silent.
- **A sibling API's audience.** GUIDs circulated during a spike are frequently another CP API's
  audience. A token minted with one is *correctly* rejected — do not "fix" this by widening the
  audience.

### The hosting tenant is not the issuing tenant

Where the service is hosted in a different Azure tenant from the one issuing tokens, the tenant id
is the **issuing** tenant. The hosting tenant's directory id rejects every token.

---

## 8. Endpoint coverage — enumerate, never prefix-match

Every endpoint requires a validated token, with **enumerated** exemptions. A prefix rule
(`startsWith("/some-prefix")`) is a defect: it silently leaves any endpoint outside the prefix
unprotected, and cannot be enumerated against the contract.

The exemption list must be:

- **Matched exactly**, so that `/thing/x` and `/thingx` stay protected.
- **Justified per entry.** Infrastructure paths (`/actuator/**`, `/`) carry no case data. Internal
  producer endpoints are a different case — see below.
- **Tested by enumerating the contract's paths**, so a newly added endpoint fails the test until
  someone classifies it. This is the property a prefix rule cannot give you.

### Internal producer endpoints

Where platform producers call an endpoint and send **no `Authorization` header at all**, there is no
token to validate and no caller identity to record. An internal-only application role does not solve
this: requiring any role stops the integration.

Be explicit about the consequences rather than implying protection that is not there:

1. It is protected by **network and gateway controls, not by the service**.
2. There is **no attribution** — nothing to audit about who called, beyond correlation id and source
   address.
3. Adding to the exemption list is a **security change** and must be reviewed as one.

The real fix is **gateway-side segregation, not authentication**: internal operations should be
reachable through APIM without a token while not being reachable by consumers at all, which means
moving them onto an internal-only API or product. Until that lands, "internal" describes intent
rather than reachability. **That is an APIM change, not a code change** — do not raise it as a code
finding.

### Non-production controllers

A mock or test callback controller **must not be registered in production**. Assert it with a
profile condition and a test.

---

## 9. Error semantics and leakage

- Distinguish **401** (we do not know who you are) from **403** (we know, and you may not do this).
  Map each failure reason to one deliberately.
- Use RFC 6750 error codes — `invalid_token`, `insufficient_scope`.
- The exception must carry a **coarse reason, never token contents**. A reason is safe to log and to
  expose in `WWW-Authenticate`; the token is not. The raw token must never be held by the exception,
  and there should be a test asserting it does not leak.
- Prefer a **checked** exception for a rejected token: it is an expected outcome a caller must turn
  into a response, not a bug. Declaring it makes that obligation part of every signature on the
  path, so a new call site cannot quietly return 500 in place of 401.

### Observability

Emit counters for success and for failure tagged by reason, plus a separate counter for what
`OBSERVE` mode *would* have rejected. Registering a counter is not enough — confirm it is actually
scrapeable, since a metrics endpoint listed in an exposure allowlist does not exist unless a
registry implementation is on the classpath.

---

## 10. Choosing the library

A thin framework wrapper over a JWT library is not automatically the right choice. Where every hard
requirement — JWKS caching, rate-limited refresh, outage tolerance, single-algorithm pinning — is a
feature of the underlying library, depending on it directly avoids adding a framework to reach it.

Weigh one thing specifically: a security framework's filter chain registers at its own order, which
may place it **after** correlation-id, client-id and audit filters. In a service whose filter order
is load-bearing, that reordering is not free.

This is a legitimate either-way decision. Record it; do not flag it as a finding.
