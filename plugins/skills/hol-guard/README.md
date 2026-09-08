# HOL Guard Skill

Use HOL Guard as a local security layer for Claude Code and other AI harnesses before tools run. The skill guides installation, Guard-owned harness setup, dry-run verification, approval review, and local evidence checks.

## Installation

Install the marketplace skill:

```text
/plugin install hol-guard@agentic-plugins-marketplace
```

HOL Guard is a separate CLI. Prefer an isolated install:

```bash
pipx install hol-guard
hol-guard status
hol-guard detect --json
```

## Protect Claude Code

```bash
hol-guard install claude-code
hol-guard run claude-code --dry-run
hol-guard run claude-code
hol-guard doctor claude-code --json
```

For other supported harnesses, the skill uses the same `hol-guard install <harness>` and `hol-guard run <harness>` workflow rather than editing user-level harness configuration directly.

## Approval and evidence workflow

When Guard blocks or queues a request, inspect it before approving:

```bash
hol-guard approvals
hol-guard receipts
hol-guard diff claude-code
```

The skill never bypasses Guard approvals or marks a workspace protected without a Guard status/doctor check.

## Upstream

HOL Guard project: https://github.com/hashgraph-online/hol-guard

Canonical Agent Skill: https://github.com/hashgraph-online/hol-guard-plugin/tree/main/skills/hol-guard

License: Apache-2.0
