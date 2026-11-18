# hmcts-sdlc-orchestrator

Bundled Claude Code plugin that ships the **HMCTS SDLC pipeline** for the Crime Common Platform (CPP) — agents, skills, hooks, commands, context docs, and the orchestrator `CLAUDE.md` in one installable plugin.

## What's inside

| Component | Items |
|---|---|
| **Agents** (`agents/`) | requirements-analyst, architecture-designer, story-writer, test-engineer, implementation, code-reviewer, ci-orchestrator, deployer, plus auxiliaries (doc-generator, event-flow-mapper, helm-config-validator, migration-reviewer, rbac-auditor, research, test-analyzer) |
| **Skills** (`skills/`) | springboot-service-from-template, springboot-api-from-template, cpp-test-authoring, context-service-guide, context-scaffold, api-contract-check, architecture-design, dependency-audit, pipeline-debug, review-pr, export-design-artifact, terraform-validate, openspec-* |
| **Hooks** (`hooks/`) | guard-bash, guard-paths, block-pii, block-secrets, telemetry-start, telemetry-nudge |
| **Commands** (`commands/`) | opsx/*, telemetry |
| **Telemetry** (`bin/cpp_telemetry/`, `git-hooks/`) | local forwarder, scrubber and spool; pass-through git hook shims (see [Telemetry](#telemetry)) |
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

## Telemetry

The plugin records your Claude Code sessions for the CPP programme. Telemetry is opt-out: once the programme has configured the plugin, it runs in every session until you turn it off. A telemetry failure never stops a session or a git command.

### What is collected

- your prompts and the replies you get;
- tool inputs and outputs (commands, file reads and edits, search results);
- cost and tokens for each request;
- hook and git events: session start, the end of each turn and sub-agent run, session end, and git commits, rewrites (amend, rebase) and pushes. A git event holds the repository name, the branch, the commit SHAs and, for a push, the remote's name. It holds no remote URL, author or email.

The first session after setup is captured as hook snapshots only. Claude Code reads its settings when the session starts, before the plugin applies the telemetry keys, so prompts, tool data and cost are exported from the next session on.

### How it is handled

- Everything is scrubbed on your laptop before it is stored. Your email, user id, account id, organisation id, host name and repository URL are removed. Inside text, your home path becomes `~` and your user name, host name and email become `[REDACTED:self]`. Anything that matches the PII and secret patterns of the plugin's guard hooks is redacted.
- The scrubbed records wait in a local spool in the plugin data directory for up to 30 days. Each batch is deleted as soon as the ingest acknowledges it. A batch that is still unsent after 30 days is deleted.
- The records go to the CPP-internal telemetry ingest configured by the programme (sign in with your Entra account: `/telemetry login`). Until you sign in, they stay in the spool.

### Commands

| Command | What it does |
|---|---|
| `/telemetry status` | Shows the forwarder, the spool, the last acknowledgement, sign-in, roster and opt-out state |
| `/telemetry login` | Signs you in with a device code in your browser |
| `/telemetry optout` | Turns telemetry off until `/telemetry on`: restores your Claude Code settings; signed in, it uploads what was spooled before the opt-out; nothing new is captured; signed out, it deletes the spool |
| `/telemetry on` | Turns telemetry back on after an opt-out |
| `/telemetry uninstall` | Opts out, stops the forwarder, restores your previous `core.hooksPath`, removes the git shims and removes the plugin data directory (spool, sign-in tokens, log). It prints the outcome of each step, including anything it could not restore |

> **CAUTION:** Run `/telemetry uninstall` before you remove the plugin with `/plugin uninstall`. Removing the plugin runs no hook: the telemetry keys stay in your Claude Code settings, `core.hooksPath` keeps pointing at the shims and the data directory stays on disk. `/telemetry uninstall` restores the settings and `core.hooksPath` and removes the data directory.

### Turn it off

- For one session: start Claude Code with `CPP_HARNESS_TELEMETRY=off` in the environment. At session start the plugin then removes the telemetry keys from your Claude Code settings and stops a running forwarder. Any values of your own that the plugin moved aside are put back. Its other hooks and the git shims do nothing in that environment.
  - It does not opt you out: the next session you start without the variable applies the keys again and starts the forwarder.
  - Claude Code reads its settings when a session starts, so the keys can still apply to the session you started with the variable. With the forwarder stopped, nothing receives what that session exports, unless another session starts the forwarder again.
  - Another session that is already running is affected only at its own next start. Until then it keeps the settings it read, and its hooks can start the forwarder again.
- For every session: `/telemetry optout` is the lasting opt-out. It stays in force until you run `/telemetry on`. From the opt-out on, nothing new is captured. Signed in, the forwarder still uploads what was spooled before the opt-out; when that upload cannot finish, the next session start resumes it, and a batch still unsent after 30 days is deleted.

### Git attribution (optional)

To record commits, rewrites and pushes, point your global git hooks at the plugin's shims. Run this line once:

```bash
prev=$(git config --global --get core.hooksPath); [ "$prev" != "$HOME/.cpp-harness/git-hooks" ] && git config --global cpp.previousHooksPath "$prev"; git config --global core.hooksPath ~/.cpp-harness/git-hooks
```

The line saves your current global `core.hooksPath` in `cpp.previousHooksPath`, unless it already names the shims directory, so running it twice is harmless.

> **CAUTION:** Run the line only when `~/.cpp-harness/git-hooks/` exists. The plugin creates it at the start of a session once telemetry is configured and on. While that directory is missing, git runs no hooks at all, not even each repository's own `.git/hooks`.

The global `core.hooksPath` means every git hook in every repository now runs through the plugin's pass-through shims. Each shim runs the hook of the same name from your previous global hooks directory first, then the repository's own `.git/hooks` hook. A failing hook still blocks the commit or push as before. Only commits, rewrites and pushes are recorded. A repository-local `core.hooksPath` (a Husky v9 setup, for example) keeps precedence: git uses it in that repository, so the shims do not run there and its git events are not recorded.

`/telemetry uninstall` restores the previous value: it sets `core.hooksPath` back to `cpp.previousHooksPath`, or unsets it when there was none, before it removes the shims directory.

### Local override (maintainers)

The plugin ships its four ingest constants empty, so an installed plugin is dormant: it starts no forwarder, changes no settings and records nothing. A maintainer can point a laptop at an ingest with an `override.json` file in the plugin data directory (the directory Claude Code passes as `CLAUDE_PLUGIN_DATA`; the fallback is `~/.claude/plugins/data/hmcts-sdlc-orchestrator/`). The file is one JSON object with the keys `ingest_url`, `tenant_id`, `client_id` and `api_app_id`, and optionally `auth_base_url` and `port`. Both URLs must be HTTPS, except to 127.0.0.1 or localhost. An override is for one laptop only; never commit one.

## Source

Mirrored from `github.com/hmcts/cpp-claude` (`.claude/` + root `CLAUDE.md`).
