# hmcts-sdlc-orchestrator

Bundled Claude Code plugin that ships the **HMCTS SDLC pipeline** for the Crime Common Platform (CPP) — agents, skills, hooks, commands, context docs, and the orchestrator `CLAUDE.md` in one installable plugin.

## What's inside

| Component | Items |
|---|---|
| **Agents** (`agents/`) | requirements-analyst, architecture-designer, story-writer, test-engineer, implementation, code-reviewer, ci-orchestrator, deployer, plus auxiliaries (doc-generator, event-flow-mapper, helm-config-validator, migration-reviewer, rbac-auditor, research, test-analyzer) |
| **Skills** (`skills/`) | springboot-service-from-template, springboot-api-from-template, cpp-test-authoring, context-service-guide, context-scaffold, api-contract-check, architecture-design, dependency-audit, pipeline-debug, review-pr, terraform-validate, openspec-* |
| **Hooks** (`hooks/`) | guard-bash, guard-paths, block-pii, block-secrets |
| **Commands** (`commands/`) | opsx/* |
| **Context** (`context/`) | tech-stack, hmcts-standards, azure-cloud-native, azure-sdk-guide, cloud-adoption-rationale, coding-standards, logging-standards |
| **Orchestration** | `CLAUDE.md` — the 8-stage pipeline definition |

## Installation

```
/plugin marketplace add hmcts/agentic-plugins-marketplace
/plugin install hmcts-sdlc-orchestrator
```

Every repo where this is enabled inherits the SDLC orchestrator CLAUDE.md, all sub-agents, all HMCTS-specific skills, and the guard hooks.

## Source

Mirrored from `github.com/hmcts/cpp-claude` (`.claude/` + root `CLAUDE.md`).
