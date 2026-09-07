## Alerting & Monitoring — Dimension Catalogue

Generic, pattern-driven reference backing the `wire-alerting-monitoring` skill. This doc
defines *which integration dimensions exist* and *what signal matters for each* — it is the
only place dimension knowledge lives. The skill's own procedure (`skills/wire-alerting-monitoring/SKILL.md`)
must never encode a dimension's detection test or signal list inline; it reads this doc instead,
so a new dimension is added here, not by rewriting the skill.

Nothing in this doc's detection tests or KQL shape may depend on any single repo's names,
queue names, or literals — everything is discovered from whichever repo the skill runs
against, at run time. Real precedent repos are cited below for provenance only, never as
values the skill's logic depends on.

### Mechanism (the "how")

The AMP platform's established observability mechanism — proven first in
`service-cp-crime-hearing-results-document-subscription` (AMP-174) — is:

- Repo-local KQL under `support/alerts-kql/` (paging) and, where a dimension below defines
  dashboard-worthy signals, `support/dashboard-kql/` (visibility) — one `.kql` file per signal.
- Log-based KQL queries `ContainerLogV2`, `parse_json(LogMessage)`, filtered by
  `PodName startswith "<this repo's fullnameOverride>"` and `ContainerName == "springboot-app"`.
  This shape generalizes safely across every `service-cp-*` because they all share the same
  HMCTS logback JSON encoder — it is not specific to any one service.
- Metric-based KQL queries the `AzureMetrics` table in the same shared Log Analytics workspace
  (platform metrics forwarded via the resource's own diagnostic settings), for signals a log
  line can never carry (see Pattern C below).
- Onboarding happens in the shared `cp-amp-terraform-alerts` repo: drop the `.kql` file under
  `queries/`, add an entry to each environment's `vars/*.tfvars`, reuse the existing 3 action
  groups (`developer-emails`, `developer-emails-and-sms`, `full`) — never create a new action
  group per service.
- A contract test (generic name: `AlertKqlLogMessageContractTest`) in the target repo asserts
  each alert KQL's `contains "..."` literal still exists in the Java source file it's cited
  against, so a log-message rename can't silently break an alert.
- Dashboard-worthy KQL under `support/dashboard-kql/` is mastered in the app repo and onboarded
  into the separate shared `cp-amp-terraform-az-dashboard` repo (a distinct repo from
  `cp-amp-terraform-alerts` — dashboards are visualised, not paged) via the `wire-azure-dashboard`
  skill. That repo auto-discovers one dashboard per `configs/<name>.json` + `queries/<name>/*.kql`
  pair — see `skills/wire-azure-dashboard/SKILL.md` for the onboarding procedure; this doc only needs
  to know that dashboard-worthy signals feed it, not its mechanics.

The real pod name comes from `hmcts/cp-vp-aks-deploy`'s `vp-config/services_values.yml` — never
inferred or hardcoded. If a service isn't registered there yet, the skill stops and asks rather
than guessing.

### Dimensions — detected independently, not mutually exclusive

A service can exhibit more than one dimension at once (e.g. a service can have both a
downstream-HTTP-client dimension and a Service-Bus dimension). Detect each independently;
generate alert/dashboard content only for dimensions actually present in the code under review.

#### Dimension: Downstream HTTP client

- **Detection**: a `clients/` package with a `RestClient` bean, or a Redis client wrapper.
- **Alert-worthy**: a call that fails repeatedly / exhausts its retry budget — the log literal
  marking the point a downstream call's failure becomes a final, business-level failure (not
  a per-attempt transient log).
- **Dashboard-worthy**: call volume, error rate, latency percentile per downstream dependency —
  "is this dependency healthy," not just "is it currently failing."

#### Dimension: Service Bus queue consumer — Pattern B (application-provisioned)

- **Detection**: the queue-provisioning class calls a queue-*create* API — see
  `service-shared.md`'s Pattern B test.
- **Alert-worthy**: DLQ dead-letters, retry-exhaustion, processor-level errors, provisioning/
  create failure at startup.
- **Dashboard-worthy**: queue depth over time, message age, throughput (messages/min). If the
  consumer applies a business-logic eligibility/filtering decision after successful ingestion
  (not every message that arrives results in a persisted/produced outcome), add a *second*,
  separate signal for the accepted/consumed count, distinct from the received/throughput count
  above — see "Incoming vs. consumed" below.

#### Dimension: Service Bus queue consumer — Pattern C (Terraform-provisioned shared queue, Event Grid-fed)

- **Detection**: the queue-provisioning class only calls an *existence-check* API, never create
  — see `service-shared.md`'s Pattern C test — and the consumed payload is a generated event
  model (an Event Grid-originated shape).
- **Alert-worthy**: everything Pattern B has, plus:
  - **Event Grid delivery failure/dead-letter** — a separate Azure resource with its own
    failure surface, independent of whether the Service Bus queue itself is healthy. A purely
    Service-Bus-side alert cannot see this.
  - **Startup failure from the queue not yet existing** — a deployment-ordering problem
    (Terraform hasn't run yet in this environment), not a runtime bug. Distinguish this from a
    genuine processing failure so it doesn't get triaged as one.
  - **A native queue-metric alert** (dead-lettered/active message count via `AzureMetrics`) —
    necessary because a purely log-based alert cannot detect the failure class where the
    consumer never started and produced zero application log activity. Depends on the Service
    Bus namespace's diagnostic settings already forwarding metrics to the shared workspace —
    verify with whoever owns that namespace's Terraform; this skill cannot provision that itself
    from an app repo.
- **Dashboard-worthy**: everything Pattern B has, plus Event Grid delivery success/failure rate.

#### Incoming vs. consumed — a cross-cutting dashboard rule, not its own dimension

Applies to any dimension above where the service applies an eligibility/subscription-matching/
filtering decision between "successfully received" and "actually produced an outcome" (proven
first on `service-cp-crime-results-pcr`'s PCR-eligibility gate). A dashboard that only shows
received/throughput volume cannot distinguish a healthy quiet period from a defect where
messages ingest fine and then get silently filtered out — exactly the shape of AMP-1091. When
this pattern is present:

- Check whether the decision point already logs **both** outcomes. Codebases often only log the
  negative/skip case ("X not required — skipping") because that was the only one anyone thought
  to make observable; the positive/accepted case frequently has no log line at all.
- If only the negative case is logged, add the symmetric positive-case log line at the same
  point (same log level, same keys, mirrored wording) — this is a legitimate, small application
  code change for this skill/its dashboard counterpart to make, same category as
  `wire-alerting-monitoring`'s Step 3 rule about adding a missing alert-worthy log line.
- Add two dashboard tiles: received/incoming count and accepted/consumed count, using the *same*
  granularity for both (e.g. both counting distinct correlation/entity IDs, not one counting raw
  messages and the other counting a finer-grained unit) so they're directly, visually comparable
  side by side — never one per-message and the other per-sub-entity.

#### Dimension: *(future)*

Add a new dimension here only once a real service actually exercises it — do not add a
speculative row for an integration style with no real instance yet (see
`hmcts-standards.md`'s "never invent requirements" rule). When one is added, give it the same
three-part shape as the rows above: detection test, alert-worthy signals, dashboard-worthy
signals.

### Baseline dashboard tiles — every service-cp-*, regardless of which dimensions it exercises

Proven by expanding `service-cp-crime-results-pcr`'s dashboard to match
`service-cp-crime-hearing-results-document-subscription`'s existing tile set — these are
universal Spring Boot / APIM-fronted observability signals, not tied to any dimension above.
Still verify each one's detection test against the target repo before adding it; a service
missing the underlying pattern (e.g. no `GlobalExceptionHandler`) genuinely doesn't get that
tile, rather than shipping a permanently-broken query for it:

- **Today's Summary** — a single table tile unioning today's counts for whichever of the other
  baseline/dimension signals apply to this service (e.g. primary-endpoint requests, errors,
  response exceptions). Compose it last, once the other tiles are decided.
- **Primary endpoint request volume** — by day/hour, both an APIM-level view (App Insights
  `requests`, `name contains "<service's APIM route slug>"`) and, if the controller itself logs
  its own per-request line, an app-level view of the same signal from that log line. Keep both
  even though they measure "the same thing" for a single-endpoint service — they observe from
  different points (edge vs. app) and a gap between them is itself a diagnostic signal (e.g.
  requests reaching APIM but never reaching the app).
- **Error Rate** — by hour. Detection: does `GlobalExceptionHandler` (or equivalent) have a
  handler for `ResponseStatusException` (or the repo's local equivalent of "this became an
  error HTTP response")? If yes, that handler's own log line is the source — filtered to its
  error-level (not warn-level) log calls only, since a well-built handler typically warns on
  4xx/client-mistake outcomes and errors only on genuine 5xx/server-side failures; conflating
  the two would mix client input mistakes into a metric meant to show operational health.
- **Errors (recent)** and **All Logs (recent)** — a generic recent-error table (7d, ~50 rows) and
  a generic all-levels recent table (12h, ~500 rows, converted to local time for on-call
  readability). No detection test needed — every `service-cp-*` has `ContainerLogV2`.
- **Queue depth/size** — *not* automatically includable. Requires either (a) a periodic
  app-side self-report log line (check for one before assuming it exists — don't copy another
  service's queue-size KQL against a log line this repo never emits), or (b) confirmed
  `AzureMetrics` data for this service's Service Bus namespace (query it directly — Pattern C's
  native-metric-alert caveat above applies here too). If neither exists, leave it out and say so
  explicitly rather than shipping a permanently-empty tile.

### Non-goals

- **Investigation (`logs-kql`) and chart (`chart-kql`) tiers** — same mechanism, add later as a
  follow-up once a real investigation need arises; not built by `wire-alerting-monitoring` today.
- **Generation-gate / business-logic-correctness drift** — an audit/drift-detection concern
  (see each repo's own design docs for its equivalent), not an operational alert.
- **Generic HTTP-layer 5xx/latency alerting** — already covered platform-wide by Application
  Insights auto-instrumentation; not a per-service gap this doc or skill needs to close.
