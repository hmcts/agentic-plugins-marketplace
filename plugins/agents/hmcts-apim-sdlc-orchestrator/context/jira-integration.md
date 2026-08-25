## JIRA integration

Scope: how the orchestrator's agents/skills interact with JIRA in this workspace. This
complements the pipeline's "Raise PR" stage (Path B, stage 10) — once a PR exists for a story's
linked Jira ticket, a comment on that ticket is how the pipeline's outcome reaches JIRA. It is
never a substitute for the ticket's own description, status, or fields.

### Access

- This workspace's JIRA is a self-hosted Jira Server/Data Center instance at
  `https://tools.hmcts.net/jira`, not Atlassian Cloud — use REST API **v2**
  (`https://tools.hmcts.net/jira/rest/api/2/...`), not v3.
- Auth: `Authorization: Bearer $AMP_JIRA_TOKEN` (a Personal Access Token env var, not a
  Basic email:token pair). The env var name may carry a numeric suffix in a given environment
  (e.g. `AMP_JIRA_TOKEN_1`) — check what's actually set (`env | grep -i AMP_JIRA_TOKEN`) rather
  than assuming the bare name.
- **Never use the Atlassian MCP connector** for JIRA or Confluence access in this workspace,
  even if it becomes authenticated/available. Only ever use the `AMP_JIRA_TOKEN*` env var(s).
- Comment bodies use Jira wiki markup, not Markdown — `h4. Heading`, `{{monospace}}`,
  `*bullet*`. Confirm this against the target instance before assuming Markdown renders.

### Hard rule: create-only

The only permitted JIRA-writing actions are:
- Posting a **new** comment on an existing ticket
- Creating a **new** ticket

Never edit or delete existing ticket content: no editing existing comments/descriptions, no
transitioning/changing status, no overwriting fields, no deleting comments or tickets. JIRA
history is a shared audit trail across teams — mutating or removing existing content destroys
that record for everyone else relying on it. If a task implies editing or deleting existing
JIRA content, stop and confirm explicitly with the user first — prior approval to post a comment
is not approval to edit anything.

### When to post a comment

Only when the user explicitly asks for a JIRA update, or approves one you've proposed — never
proactively. A natural point is once a PR (or PRs, for a cross-repo change) exists for the
story's linked ticket: summarise the change and link the PR(s) so the ticket reflects what
shipped, without duplicating the ticket's own description/ACs.

### Comment format

Keep it concise, professional, and structured with only the headings that apply:

- **Summary** — for an enhancement/feature: what changed, key implementation details, expected
  behaviour.
- **RCA** — for a defect/bug: the root cause and the fix/approach taken.
- **Implementation** — key technical decisions worth surfacing (schema/contract changes,
  cross-repo dependencies) — not a restatement of the diff.
- **PR** — link every relevant PR (multiple, for a cross-repo change spanning an `api-cp-*` spec
  and its `service-cp-*` consumer).

Don't repeat information already in the ticket's description unless needed for context. Don't
pad with implementation detail that doesn't help a reader decide whether the ticket is resolved.
