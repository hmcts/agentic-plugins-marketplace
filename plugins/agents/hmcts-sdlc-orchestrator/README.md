# hmcts-sdlc-orchestrator

Bundled Claude Code plugin that ships the **HMCTS SDLC pipeline** for the Crime Common Platform (CPP) — agents, skills, hooks, commands, context docs, and the orchestrator `CLAUDE.md` in one installable plugin.

## What's inside

| Component | Items |
|---|---|
| **Agents** (`agents/`) | requirements-analyst, architecture-designer, story-writer, test-engineer, implementation, code-reviewer, ci-orchestrator, deployer, plus auxiliaries (doc-generator, event-flow-mapper, helm-config-validator, migration-reviewer, rbac-auditor, research, test-analyzer) |
| **Skills** (`skills/`) | springboot-service-from-template, springboot-api-from-template, cpp-test-authoring, context-service-guide, context-scaffold, api-contract-check, architecture-design, dependency-audit, pipeline-debug, review-pr, export-design-artifact, terraform-validate, openspec-* |
| **Hooks** (`hooks/`) | guard-bash, guard-paths, block-pii, block-secrets |
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

> "Here's the brief for the new custody hearing widget — turn it into requirements, stories, tests, and implementation."

Claude will invoke the `requirements-analyst`, `story-writer`, `test-engineer`, and `implementation` agents in sequence, pausing at each human gate for review.

For standalone skills:
> "Review this PR against CPP standards" — triggers `review-pr`
> "Validate the Helm chart for cpp-hearing" — triggers `helm-config-validator`
> "Trace the CaseOpened event" — triggers `event-flow-mapper`

## Source

Mirrored from `github.com/hmcts/cpp-claude` (`.claude/` + root `CLAUDE.md`).
