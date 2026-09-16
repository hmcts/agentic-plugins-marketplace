# hmcts-sdlc-orchestrator

Bundled Claude Code plugin that ships the **HMCTS SDLC pipeline** for the Crime Common Platform (CPP) — agents, skills, hooks, commands, context docs, and the orchestrator `CLAUDE.md` in one installable plugin.

## What's inside

| Component | Items |
|---|---|
| **Agents** (`agents/`) | requirements-analyst, architecture-designer, story-writer, test-engineer, implementation, code-reviewer, ci-orchestrator, deployer, plus auxiliaries (doc-generator, event-flow-mapper, helm-config-validator, migration-reviewer, rbac-auditor, research, test-analyzer) |
| **Skills** (`skills/`) | springboot-service-from-template, springboot-api-from-template, cpp-test-authoring, context-service-guide, context-scaffold, api-contract-check, architecture-design, dependency-audit, pipeline-debug, review-pr, export-design-artifact, terraform-validate, openspec-* |
| **Hooks** (`hooks/`) | guard-bash, guard-paths, block-pii, block-secrets, enforce-gate, harness-telemetry, record-gate, `git/post-commit`, `git/post-rewrite`, `git/pre-push` |
| **Commands** (`commands/`) | opsx/* |
| **Context** (`context/`) | tech-stack, hmcts-standards, azure-cloud-native, azure-sdk-guide, cloud-adoption-rationale, coding-standards, logging-standards |
| **Orchestration** | `CLAUDE.md` — the 8-stage pipeline definition |

## Prerequisites

- Claude Code with the [agentic-plugins-marketplace](https://github.com/hmcts/agentic-plugins-marketplace) registered
- For `openspec-*` commands: the `openspec` CLI on your `PATH` (see `commands/opsx/` for details)
- GitHub MCP or Jenkins MCP configured if using the CI/CD pipeline agents

## Installation

```
/plugin install hmcts-sdlc-orchestrator@agentic-plugins-marketplace
```

To enable the SDLC orchestrator in a repo, copy `CLAUDE.md` from the plugin into your project root after installation:
```bash
cp ~/.claude/plugins/hmcts-sdlc-orchestrator/CLAUDE.md ./CLAUDE.md
```
This loads the 8-stage pipeline definition, context file references, and hard rules into every Claude session for that project.

## Usage example

After copying `CLAUDE.md` into your project root, start the pipeline by describing what you need:

> "Here's the brief for the new custody hearing widget — turn it into a requirements document."

Claude runs **one gated stage at a time**. It will invoke `requirements-analyst`, write
`docs/pipeline/requirements.md`, and stop. The next stage is blocked by hook until you
review the artefact and run:

```
/gate approve requirements
```

Ask for several stages at once ("requirements, stories, tests and implementation") and you
will still get only the first — the rest are blocked until each gate is approved in turn.
That is deliberate: the gates are the point of the pipeline, and prose instructions alone
were not holding them.

| `/gate` decision | Effect |
|---|---|
| `/gate approve <stage>` (or `accept`/`edit`) | next stage unblocks |
| `/gate skip <stage>` | stage does not apply to this change — treated as satisfied |
| `/gate reject <stage> <reason>` | stage stays locked, **all downstream stages reset to pending** |

`record-gate.sh --status` shows where you are. Gate state is per repo **and branch**.

If you also run another SDD framework (superpowers, BMAD, Spec-Kit), the HMCTS gate state
takes precedence over its phase-advance workflow.

### Telemetry and commit attribution

This version also enables the harness measurement hooks. They write anonymous, local JSONL
to `~/.cpp-harness/` — session lifecycle, which skills and agents ran, artefact writes under
`docs/pipeline/`, and gate decisions. **Not** recorded: prompt text, file contents, absolute
paths, developer identity, or any free text. Opt out with `CPP_HARNESS_TELEMETRY=off`.

Commit attribution is opt-in per machine and needs one command:

```bash
git config --global core.hooksPath ~/.claude/plugins/hmcts-sdlc-orchestrator/hooks/git
```

Nothing about AI assistance is written into git history — attribution is a local SHA index,
not a commit trailer, because most CPP repos are public and that marker would be permanent.

For standalone skills:
> "Review this PR against CPP standards" — triggers `review-pr`
> "Validate the Helm chart for cpp-hearing" — triggers `helm-config-validator`
> "Trace the CaseOpened event" — triggers `event-flow-mapper`

## Source

Mirrored from `github.com/hmcts/cpp-claude` (`.claude/` + root `CLAUDE.md`).
