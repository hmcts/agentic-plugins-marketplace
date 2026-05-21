# Cloud Adoption Rationale — On-Demand Reference

## Why this file exists
Two arguments surface regularly against adopting Azure services:

1. "Using managed Azure services creates vendor lock-in."
2. "Cloud services are too expensive; let's self-host."

Both are usually wrong for HMCTS, for the reasons captured below. This file is
**not auto-loaded**. Pull it in explicitly when the argument appears in an
ADR, a design discussion, or a review — or reference it from another
context file by name.

This file does not exist to shut down debate. It exists so the counter-
arguments are already written down rather than being reconstructed each time.

---

## "Vendor lock-in" — why it is usually a weak argument

### The weak form of the argument
"If we use Azure Service Bus / Key Vault / Cosmos DB, we can't ever leave
Azure." Stated this way, the argument treats portability as a goal in itself.

### Why it usually does not hold

- **Portability has a real cost that is almost always paid.** Anti-lock-in
  patterns — hexagonal ports around every managed service, generic
  abstractions that pretend Service Bus is Kafka is SQS — add code, hide the
  strengths of the underlying service, and accumulate bugs in the adapter
  layer. That cost is paid every sprint. The migration-from-Azure cost is
  paid zero times in the typical lifetime of an HMCTS service.

- **Abstractions create their own lock-in.** A bespoke messaging abstraction
  that the team owns becomes a proprietary framework that new joiners must
  learn. Switching away from it is every bit as disruptive as switching
  clouds — often more so, because the bespoke layer is undocumented.

- **The cloud-exit scenario is narrower than it sounds.** A serious exit is
  rare; a re-platform within Azure (from one managed service to another) is
  common. Designing for the common case (use the managed service well) beats
  designing for the rare case (escape the cloud intact).

- **Shared Responsibility reduces what the team owns.** Adopting a managed
  service offloads patching, failover, scaling, and key rotation to Azure.
  In a public-sector team with constrained headcount, that is a material
  security and reliability uplift — not a neutral trade.

- **HMCTS has already chosen Azure.** The platform, the GitOps tooling, the
  observability stack, the CA trust chain, and the deployment automation are
  all Azure-native. "Stay portable" as a design principle inside a consciously
  Azure-first estate is design without a target.

### Where portability genuinely matters

This is a real concern when:

- Data gravity locks a service to a specific region or residency regime that
  Azure cannot meet. (Rare for HMCTS workloads in UK regions.)
- A service exists at the seam between HMCTS and a partner organisation that
  cannot accept an Azure-specific integration.
- Legislation or procurement rules mandate multi-cloud capability.

If one of these applies, write an ADR stating so and design accordingly. If
none apply, use the managed service.

---

## "Cloud is expensive" — why this needs TCO, not service price

### The weak form of the argument
"Look at the monthly Azure bill, we could self-host for a fraction of that."
Stated this way, the argument compares service line items against hypothetical
infrastructure costs and stops there.

### Why Total Cost of Ownership is the only honest comparison

- **People are the most expensive resource, by a wide margin.** A single
  engineer's fully-loaded cost for a year dwarfs most HMCTS Azure service
  bills. If "save £X/month on Service Bus" consumes one engineer-week per
  month in operational overhead, the business is losing money.

- **Self-hosting is rarely just "run the OSS equivalent".** It is: provision
  it, harden it, patch it, monitor it, back it up, plan and test DR, rotate
  credentials, manage upgrades, handle noisy-neighbour issues, be on-call
  for it, document it, onboard new engineers to it. Every item is
  engineering time that is not spent on the service's actual purpose.

- **Availability SLAs have real value.** When a managed service meets its
  SLA, that is availability the team did not have to engineer. Comparing
  service price to "we'll just run it cheaper" usually doesn't price in
  availability to parity.

- **Security patching cadence is a ticking clock.** Managed services patch
  on the provider's schedule. Self-hosted equivalents patch on whoever has
  time this sprint. The gap between the two shows up in security
  incidents, not on any cost sheet.

- **Opportunity cost.** Every hour spent babysitting a self-hosted thing is
  an hour not spent shipping user value. For public services this matters —
  it's the difference between the service improving and the service stalling.

### A proper TCO comparison includes

- Service / infrastructure bill (the visible number).
- Fully-loaded engineering cost to operate, patch, and on-call.
- Cost of the availability delta if the self-hosted option has a weaker SLA.
- Cost of the security patching delta.
- Data transfer and egress costs (often forgotten in self-host proposals).
- Amortised cost of the eventual cloud migration when the self-host option
  runs out of runway.

If a cost conversation cannot produce those numbers, it is not a TCO
discussion — it is a service-price discussion, and it is not sufficient to
overturn the default posture.

---

## How to use this file

- Link to this file from an ADR that discusses cloud adoption trade-offs.
- Quote the relevant section when the argument appears in design review.
- Do not auto-load it. Dragging this file into every Spring Boot conversation
  is noise; pull it in when the argument actually surfaces.

## Related
- `context/azure-cloud-native.md` — the default posture that these arguments
  push against.
- `skills/adr-template.md` — the place to record a decision once these
  arguments have been weighed.
