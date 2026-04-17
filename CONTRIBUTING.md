# Contributing to the Agentic Plugins Marketplace

Thank you for contributing! This guide covers how to add new plugins, what files each plugin needs, and how the review process works.

---

## Table of contents

- [Local development setup](#local-development-setup)
- [Before you start](#before-you-start)
- [Plugin types overview](#plugin-types-overview)
- [General rules](#general-rules)
- [Adding an MCP server](#adding-an-mcp-server)
- [Adding a skill](#adding-a-skill)
- [Adding a hook](#adding-a-hook)
- [Adding a template](#adding-a-template)
- [Updating the marketplace catalog](#updating-the-marketplace-catalog)
- [Security — porting from external sources](#security--porting-from-external-sources)
- [Submitting a pull request](#submitting-a-pull-request)
- [Code of conduct](#code-of-conduct)

---

## Local development setup

When building or testing a plugin you want Claude Code to load from your local clone rather than from the published GitHub repo. Register the marketplace as a local directory source so changes take effect immediately on `/reload-plugins` — no push or publish step required.

Add this to `~/.claude/settings.json` (global, affects all projects) or to `.claude/settings.json` in the project where you are testing (project-scoped):

```jsonc
{
  "extraKnownMarketplaces": {
    "agentic-plugins-marketplace": {
      "source": {
        "source": "directory",
        "path": "/absolute/path/to/your/clone"
      }
    }
  }
}
```

Then enable the plugin you are working on:

```jsonc
{
  "enabledPlugins": {
    "my-new-plugin@agentic-plugins-marketplace": true
  }
}
```

Run `/reload-plugins` inside Claude Code to pick up changes. You do not need to install the plugin — enabling it from a directory source loads the files directly from disk.

> **Scope tip** — use project scope (`.claude/settings.json`) while developing so your test config is isolated to the clone directory and does not affect other projects.

---

## Before you start

- Check `.claude-plugin/marketplace.json` and `plugins/` to make sure a similar plugin doesn't already exist.
- Open an issue first if you're unsure whether a plugin fits or want feedback on the idea.
- If you are porting a plugin from an external source, read the [security guidance below](#security-porting-from-external-sources) before proceeding.

---

## Plugin types overview

| Type | Directory | Purpose |
|------|-----------|---------|
| MCP Server | `plugins/mcp-servers/` | Expose external APIs and services as Claude tools |
| Skill | `plugins/skills/` | Slash-command prompts that give Claude a structured playbook |
| Hook | `plugins/hooks/` | Shell scripts triggered by Claude Code lifecycle events |
| Template | `plugins/templates/` | `CLAUDE.md` starter files for specific project stacks |

Plugins are installed exclusively through Claude Code's native `/plugin` system. There is no separate bash installer.

---

## General rules

Every plugin lives in its own directory under the relevant type folder.

**Required in every plugin:**

```
plugins/<type>/<name>/
├── .claude-plugin/
│   └── plugin.json    ← plugin metadata
└── README.md          ← user-facing documentation
```

**Additional type-specific files** are described in each section below.

### Naming

- Directory name: lowercase kebab-case (e.g. `my-new-plugin`)
- Be specific — `postgres` is better than `database`
- Must be unique across the marketplace

### .claude-plugin/plugin.json

Minimum required fields:

```jsonc
{
  "name": "my-plugin",        // kebab-case, matches directory name
  "version": "1.0.0",         // semver, start at 1.0.0
  "description": "One sentence describing what this plugin does.",
  "author": "your-github-handle",
  "license": "MIT",
  "keywords": ["tag1", "tag2"]
}
```

### README.md

Every README must cover:

1. **What it does** — one-sentence description
2. **Prerequisites** — anything the user must install beforehand
3. **Installation** — the `/plugin install <name>@agentic-plugins-marketplace` command
4. **Configuration** — all required env vars or settings with examples
5. **Usage example** — at least one concrete example

---

## Adding an MCP server

### Directory structure

```
plugins/mcp-servers/<name>/
├── .claude-plugin/
│   └── plugin.json   ← include userConfig for every required env var
├── .mcp.json         ← MCP server config read by /plugin
└── README.md
```

### .mcp.json

```jsonc
{
  "<server-name>": {
    "command": "npx",
    "args": ["-y", "@scope/mcp-server-package"],
    "env": {
      "API_KEY": "${API_KEY}"   // ${VAR} = resolved from the user's environment
    }
  }
}
```

### userConfig in .claude-plugin/plugin.json

Declare every `${VAR}` placeholder so the `/plugin` TUI can prompt the user and store secrets in the OS keychain:

```jsonc
{
  "name": "my-server",
  "userConfig": {
    "API_KEY": {
      "description": "API key for the service (found at example.com/settings)",
      "required": true,
      "secret": true    // stored in OS keychain, not settings.json
    }
  }
}
```

### Checklist

- [ ] `.mcp.json` present with correct server command and args
- [ ] `.claude-plugin/plugin.json` has `userConfig` for every `${VAR}` placeholder
- [ ] README lists all tools the server exposes
- [ ] `.claude-plugin/marketplace.json` entry added
- [ ] No secrets or hardcoded credentials anywhere

---

## Adding a skill

### Directory structure

```
plugins/skills/<name>/
├── .claude-plugin/
│   └── plugin.json
├── skills/
│   └── <trigger>/
│       └── SKILL.md    ← the prompt template
└── README.md
```

The trigger name (directory under `skills/`) becomes the slash command: `skills/review/SKILL.md` → `/review`.

### Writing SKILL.md

Write it as instructions to a capable engineer:

- Use imperative mood ("Analyse the diff and…", "Generate a…")
- Be explicit about the steps Claude should follow
- Specify the expected output format
- One skill, one job — keep it focused
- Never include secrets or credentials

### Checklist

- [ ] `skills/<trigger>/SKILL.md` contains clear, actionable instructions
- [ ] Trigger name doesn't clash with an existing skill
- [ ] `.claude-plugin/plugin.json` present
- [ ] README shows the slash command and a concrete example
- [ ] `.claude-plugin/marketplace.json` entry added

---

## Adding a hook

### Directory structure

```
plugins/hooks/<name>/
├── .claude-plugin/
│   └── plugin.json
├── hooks/
│   └── hooks.json      ← native hook config
├── hook.sh             ← the hook script
└── README.md
```

### hooks/hooks.json

```jsonc
{
  "Stop": [                         // lifecycle event (see table below)
    {
      "hooks": [
        {
          "type": "command",
          "command": "${CLAUDE_PLUGIN_ROOT}/hook.sh"
        }
      ]
    }
  ]
}
```

Use `${CLAUDE_PLUGIN_ROOT}` for the script path — it resolves to the installed plugin directory.

### Lifecycle events

| Event | Fires when | Can block tool calls? |
|-------|-----------|----------------------|
| `PreToolUse` | Before any tool call | Yes (non-zero exit blocks) |
| `PostToolUse` | After any tool call | No |
| `Notification` | Claude surfaces a notification | No |
| `Stop` | Claude finishes its turn | No |
| `SubagentStop` | A subagent finishes | No |

### Writing hook.sh

- Start with `#!/usr/bin/env bash` and `set -euo pipefail`
- Keep the script idempotent — it runs many times per session
- Use `${CLAUDE_PLUGIN_ROOT}` for paths to bundled files
- Avoid blocking I/O in `PreToolUse` hooks

### Checklist

- [ ] `hook.sh` starts with `set -euo pipefail`
- [ ] `hooks/hooks.json` uses `${CLAUDE_PLUGIN_ROOT}/hook.sh`
- [ ] Script is idempotent
- [ ] `.claude-plugin/plugin.json` present
- [ ] README documents env variables read and required system tools
- [ ] `.claude-plugin/marketplace.json` entry added

---

## Adding a template

Templates are `CLAUDE.md` files for specific project stacks. Claude Code reads `CLAUDE.md` automatically at the start of every session to understand the project's conventions.

### Directory structure

```
plugins/templates/<name>/
├── .claude-plugin/
│   └── plugin.json
├── CLAUDE.md           ← the template
└── README.md
```

### Writing CLAUDE.md

A good template covers:

| Section | Content |
|---------|---------|
| Overview | Placeholder (`<!-- fill in -->`) for the project description |
| Tech stack | Language version, package manager, test runner, linter |
| Project structure | Annotated two-level directory tree |
| Development commands | Copy-pasteable commands Claude can run |
| Conventions | Naming, style, patterns specific to this stack |
| Testing guidelines | Unit vs integration boundary |
| What Claude should NOT do | Guardrails to prevent common mistakes |

Use `<!-- comment -->` to mark sections the user must fill in after installation.

### Checklist

- [ ] Placeholder comments mark every section requiring user input
- [ ] "What Claude should NOT do" section present
- [ ] All commands are correct for the stated toolchain
- [ ] `.claude-plugin/plugin.json` present
- [ ] README explains what to customise after installation
- [ ] `.claude-plugin/marketplace.json` entry added

---

## Updating the marketplace catalog

After adding or modifying a plugin, add or update its entry in `.claude-plugin/marketplace.json`:

```jsonc
{
  "name": "<name>",
  "source": "./plugins/<type>/<name>",
  "description": "<same as plugin.json description>",
  "version": "1.0.0",
  "category": "<mcp-server | skill | hook | template>",
  "tags": ["tag1", "tag2"]
}
```

Keep entries sorted: `mcp-server` → `skill` → `hook` → `template`, alphabetically within each group.

---

## Security — porting from external sources

> **Warning: never copy a plugin from an external source without a full security review.**

When you port a plugin from outside this organisation — a public GitHub repo, a blog post, a third-party marketplace — you are potentially introducing code that runs with elevated privilege inside every installer's Claude session. The review bar must be higher than for plugins written from scratch, because you cannot know the original author's intent.

### What to audit before submitting

**MCP servers**

- Read the server's source code in full, or verify it comes from a reputable publisher (e.g., an official `@modelcontextprotocol/server-*` package, or a package owned by the service provider itself).
- Check what the server does with tool responses. A malicious server can embed instructions in response text that hijack Claude's subsequent behaviour — **prompt injection via tool output**. Look for anything that constructs response strings from external data without sanitisation.
- Confirm the server does not phone home, write files outside its declared scope, or request more permissions than it needs.
- Pin to a specific version or commit hash in `.mcp.json` rather than a floating `latest`.

**Skills**

- Read `SKILL.md` in full, including any HTML comments (`<!-- -->`), Unicode whitespace, or zero-width characters that could conceal instructions.
- A SKILL.md from an untrusted source can contain hidden prompt-injection payloads that override Claude's behaviour when the slash command is invoked. Treat it with the same scrutiny as executable code.

**Hooks**

- Hook scripts run as shell commands with your full user privileges — **no sandboxing**. A single malicious line can exfiltrate credentials, install persistence, or destroy data.
- Read every line of `hook.sh`. Do not trust scripts that use `eval`, pipe from the internet, or obfuscate logic with base64 / here-docs.
- Run the script in a throwaway environment first if you have any doubt.

### Porting checklist

- [ ] Source repository identified and linked in the PR description
- [ ] Server source code reviewed (MCP servers) or skill file read in full (skills)
- [ ] No obfuscated code, unexpected network calls, or excessive filesystem access
- [ ] Version pinned to a specific release, not `latest`
- [ ] PR description explains what the plugin does and why it is safe to include

---

## Submitting a pull request

1. Fork the repo and create a branch: `git checkout -b feat/plugin-<name>`
2. Add the plugin directory with all required files
3. Add the entry to `.claude-plugin/marketplace.json`
4. Open a PR against `main` with the title `feat: add <name> <type>`

### PR checklist

- [ ] Plugin directory contains `.claude-plugin/plugin.json` and `README.md`
- [ ] Type-specific file present: `.mcp.json` / `skills/<trigger>/SKILL.md` / `hooks/hooks.json`
- [ ] `userConfig` declared for every required env var (MCP servers)
- [ ] `.claude-plugin/marketplace.json` updated
- [ ] No secrets or credentials anywhere in the plugin directory
- [ ] README covers prerequisites, installation, configuration, and a usage example

---

## Code of conduct

Be kind. Review feedback constructively. Assume good intent.

If you experience or witness unacceptable behaviour, open an issue or contact the maintainers directly.
