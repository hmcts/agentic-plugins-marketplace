# Contributing to the Agentic Plugins Marketplace

Thank you for contributing! This guide explains how to add new plugins, what each file must contain, and how the review process works.

---

## Table of contents

- [Before you start](#before-you-start)
- [Plugin types overview](#plugin-types-overview)
- [General rules for all plugins](#general-rules-for-all-plugins)
  - [Naming](#naming)
  - [plugin.json requirements](#pluginjson-requirements)
  - [README.md requirements](#readmemd-requirements)
- [Adding an MCP server](#adding-an-mcp-server)
- [Adding a skill](#adding-a-skill)
- [Adding a hook](#adding-a-hook)
- [Adding a template](#adding-a-template)
- [Updating registry.json](#updating-registryjson)
- [Submitting a pull request](#submitting-a-pull-request)
- [Code of conduct](#code-of-conduct)

---

## Before you start

- Check [registry.json](registry.json) and the `plugins/` directory to make sure a similar plugin does not already exist.
- Open an issue first if you're unsure whether a plugin fits the marketplace or want feedback on the idea.
- Read the [plugin type](#plugin-types-overview) section that applies to what you're building.

---

## Plugin types overview

| Type | Directory | Purpose |
|------|-----------|---------|
| MCP Server | `plugins/mcp-servers/` | Expose external APIs/services as tools Claude can call |
| Skill | `plugins/skills/` | Slash-command prompts that give Claude a structured playbook |
| Hook | `plugins/hooks/` | Shell scripts triggered by Claude Code lifecycle events |
| Template | `plugins/templates/` | `CLAUDE.md` starter files for specific project stacks |

---

## Two installation paths — keep both working

Every plugin supports two independent install paths:

| Path | How it works | Key files |
|------|-------------|-----------|
| **`/plugin` TUI** | Claude Code's native plugin system reads `.claude-plugin/` and type-specific directories | `.claude-plugin/plugin.json`, `.mcp.json` / `skills/<t>/SKILL.md` / `hooks/hooks.json` |
| **`install.sh`** | Bash installer reads `plugin.json` and copies/registers things manually | `plugin.json`, `skill.md` / `hook.sh` / `CLAUDE.md` |

When you add or modify a plugin, **both paths must keep working**. The files for each path live side-by-side in the same plugin directory.

---

## General rules for all plugins

Every plugin lives in its own directory under the relevant type folder and must contain **at minimum**:

```
plugins/<type>/<plugin-name>/
├── .claude-plugin/
│   └── plugin.json    ← native metadata for /plugin system
├── plugin.json        ← installer manifest (validated against schemas/plugin.schema.json)
└── README.md          ← user-facing documentation
```

Additional type-specific files are described in each section below.

### Naming

- Directory and `name` field: lowercase kebab-case (e.g. `my-new-plugin`).
- Be specific — `postgres` is better than `database`.
- Avoid vendor/brand names as the sole identifier when a category name works (e.g. prefer `linear-issues` over just `linear`).

### plugin.json requirements

- Must validate against [`schemas/plugin.schema.json`](schemas/plugin.schema.json).
- `version` must follow [semver](https://semver.org/) — start new plugins at `1.0.0`.
- `description` must be a single sentence under 100 characters.
- `tags` must include at least one tag and no more than ten.
- All `${VAR_NAME}` placeholders in `env` or `args` must be documented in the README.

### README.md requirements

Every README must include:

1. **One-sentence description** — what the plugin does.
2. **Prerequisites** — anything the user must install or configure beforehand.
3. **Installation** — the exact `./scripts/install.sh <path>` command, plus any manual alternative.
4. **Configuration** — all environment variables or settings the user must provide, with examples.
5. **Usage example** — at least one concrete example showing the plugin in action.

---

## Adding an MCP server

MCP servers wrap an existing MCP-compatible package (e.g. an `@modelcontextprotocol/server-*` npm package or a Python `mcp-*` package) and make it discoverable in the marketplace.

### Directory structure

```
plugins/mcp-servers/<name>/
├── .claude-plugin/
│   └── plugin.json   ← native metadata; include userConfig for required env vars
├── .mcp.json         ← native MCP server config read by /plugin
├── plugin.json       ← installer manifest
└── README.md
```

### plugin.json fields

```jsonc
{
  "name": "my-service",          // kebab-case, unique across the marketplace
  "version": "1.0.0",
  "description": "Short description of what tools this server exposes.",
  "type": "mcp-server",
  "author": "your-github-handle",
  "license": "MIT",
  "homepage": "https://...",     // link to the upstream package / docs
  "tags": ["my-service", "api"],
  "mcp": {
    "transport": "stdio",        // or "sse"
    "command": "npx",            // executable to run
    "args": ["-y", "@scope/server-name"],
    "env": {
      "API_KEY": "${API_KEY}"    // ${VAR} = user must supply; literal = default value
    }
  }
}
```

### .mcp.json format

```jsonc
{
  "mcpServers": {
    "<server-name>": {
      "command": "npx",
      "args": ["-y", "@scope/server-package"],
      "env": {
        "API_KEY": "${API_KEY}"   // ${VAR} = user must supply
      }
    }
  }
}
```

### .claude-plugin/plugin.json — userConfig

Declare each `${VAR}` placeholder in `userConfig` so the `/plugin` TUI can prompt the user and store secrets in the OS keychain:

```jsonc
{
  "name": "my-server",
  "userConfig": {
    "API_KEY": {
      "description": "API key for the service",
      "required": true,
      "secret": true      // stored in OS keychain, not settings.json
    }
  }
}
```

### Checklist

- [ ] `plugin.json` validates against the schema
- [ ] `.mcp.json` present with correct server config
- [ ] `.claude-plugin/plugin.json` has `userConfig` entry for every `${VAR}` placeholder
- [ ] All `${VAR}` placeholders are also documented in the README
- [ ] README lists the tools the server exposes (name + description)
- [ ] README includes an example `claude mcp add` command as a manual alternative
- [ ] `.claude-plugin/marketplace.json` entry added
- [ ] `registry.json` updated with a new entry for this plugin

---

## Adding a skill

Skills are Markdown prompt files that give Claude a structured task description when triggered by a slash command.

### Directory structure

```
plugins/skills/<name>/
├── .claude-plugin/
│   └── plugin.json         ← native metadata
├── skills/
│   └── <trigger>/
│       └── SKILL.md        ← native skill file read by /plugin (same content as skill.md)
├── plugin.json             ← installer manifest
├── skill.md                ← skill file read by install.sh
└── README.md
```

`skills/<trigger>/SKILL.md` and `skill.md` must have identical content — they are two entry points to the same prompt for the two install paths.

### plugin.json fields

```jsonc
{
  "name": "my-skill",
  "version": "1.0.0",
  "description": "One sentence describing what this skill does.",
  "type": "skill",
  "author": "your-github-handle",
  "license": "MIT",
  "tags": ["tag1", "tag2"],
  "skill": {
    "file": "skill.md",     // path relative to the plugin directory
    "trigger": "my-cmd"     // slash command without the leading /
  }
}
```

### Writing skill.md

A skill file is a prompt Claude receives instead of user input when the slash command is invoked. Write it as you would write instructions to a capable engineer:

- Use imperative mood ("Analyse the diff and…", "Generate a…").
- Be explicit about the steps Claude should follow.
- Specify the exact output format you expect.
- Keep it focused — one skill, one job.
- Do not include secrets or credentials.

### Checklist

- [ ] `skill.md` contains clear, actionable instructions
- [ ] `skills/<trigger>/SKILL.md` is present with identical content
- [ ] Trigger name does not clash with an existing skill (check `plugins/skills/`)
- [ ] `.claude-plugin/plugin.json` present
- [ ] README shows the slash command and a concrete example output
- [ ] `.claude-plugin/marketplace.json` entry added
- [ ] `registry.json` updated

---

## Adding a hook

Hooks are shell scripts that run at specific points in the Claude Code session lifecycle.

### Directory structure

```
plugins/hooks/<name>/
├── .claude-plugin/
│   └── plugin.json       ← native metadata
├── hooks/
│   └── hooks.json        ← native hook config read by /plugin
├── plugin.json           ← installer manifest
├── hook.sh               ← hook script (referenced by both hooks.json and install.sh)
└── README.md
```

### plugin.json fields

```jsonc
{
  "name": "my-hook",
  "version": "1.0.0",
  "description": "One sentence describing what this hook does.",
  "type": "hook",
  "author": "your-github-handle",
  "license": "MIT",
  "tags": ["tag1"],
  "hook": {
    "event": "Stop",                              // lifecycle event (see below)
    "matcher": "Bash",                            // optional: tool name filter (PreToolUse / PostToolUse only)
    "command": "~/.claude/hooks/my-hook.sh"      // where the installer places the script
  }
}
```

### Supported events

| Event | When it fires | Can block? |
|-------|--------------|-----------|
| `PreToolUse` | Before any tool call | Yes (non-zero exit blocks) |
| `PostToolUse` | After any tool call | No |
| `Notification` | Claude surfaces a notification | No |
| `Stop` | Claude finishes its turn | No |
| `SubagentStop` | A subagent finishes | No |

### Writing hook.sh

- Start with `#!/usr/bin/env bash` and `set -euo pipefail`.
- Keep the script idempotent — it may be called many times per session.
- Use environment variables injected by Claude Code:
  - `CLAUDE_TOOL_NAME` — name of the tool (Pre/PostToolUse)
  - `CLAUDE_TOOL_INPUT` — JSON string of tool input (Pre/PostToolUse)
  - `CLAUDE_SESSION_ID` — current session identifier
- Avoid blocking I/O in `PreToolUse` hooks — they delay the tool call.
- Non-zero exit from a `PreToolUse` hook **blocks** the tool call and surfaces the exit code to the user. Use this power deliberately.

### hooks/hooks.json format

```jsonc
{
  "Stop": [                       // lifecycle event
    {
      "hooks": [
        {
          "type": "command",
          "command": "${CLAUDE_PLUGIN_ROOT}/hook.sh"  // path within the installed plugin
        }
      ]
    }
  ]
}
```

Use `${CLAUDE_PLUGIN_ROOT}` for the script path — it resolves to the plugin's installed directory regardless of where Claude Code is run from.

### Checklist

- [ ] `hook.sh` starts with `set -euo pipefail`
- [ ] Script is idempotent
- [ ] `hooks/hooks.json` present with correct event and `${CLAUDE_PLUGIN_ROOT}` path
- [ ] `.claude-plugin/plugin.json` present
- [ ] README documents which env variables are read and any required system tools
- [ ] Manual install instructions included (for users who don't use the installer)
- [ ] `.claude-plugin/marketplace.json` entry added
- [ ] `registry.json` updated

---

## Adding a template

Templates are `CLAUDE.md` files for specific project stacks. They give Claude accurate context from day one.

### Directory structure

```
plugins/templates/<name>/
├── plugin.json
├── CLAUDE.md     ← the template (filename can differ, set in plugin.json)
└── README.md
```

### plugin.json fields

```jsonc
{
  "name": "my-stack",
  "version": "1.0.0",
  "description": "CLAUDE.md template for [stack] projects.",
  "type": "template",
  "author": "your-github-handle",
  "license": "MIT",
  "tags": ["python", "django"],   // include language and key framework names
  "template": {
    "file": "CLAUDE.md",
    "targetPath": "CLAUDE.md"     // where it's placed relative to the project root
  }
}
```

### Writing CLAUDE.md

A good project template covers:

| Section | What to include |
|---------|----------------|
| Overview | Placeholder for the project description |
| Tech stack | Language version, package manager, test runner, linter |
| Project structure | Annotated directory tree (max 2 levels) |
| Development commands | Copy-pasteable commands Claude can run |
| Conventions | Naming, style, patterns specific to this stack |
| Testing guidelines | What counts as a unit test vs integration test |
| What Claude should NOT do | Guardrails that prevent common mistakes |

Use `<!-- comment -->` for sections the user must fill in.

### Checklist

- [ ] Placeholder comments mark sections requiring user input
- [ ] All commands are correct for the stated package manager and toolchain
- [ ] "What Claude should NOT do" section present
- [ ] README explains what to customise after installation
- [ ] `registry.json` updated

---

## Updating registry.json

After adding or modifying a plugin, add or update its entry in `registry.json`:

```jsonc
{
  "path": "plugins/<type>/<name>",
  "name": "<name>",
  "version": "1.0.0",
  "type": "<type>",
  "description": "<same as plugin.json>",
  "tags": ["..."],
  "author": "<your-github-handle>"
}
```

Keep entries sorted alphabetically within each type, then across types in the order: `mcp-server`, `skill`, `hook`, `template`.

---

## Submitting a pull request

1. Fork the repository and create a branch: `git checkout -b feat/plugin-<name>`.
2. Add your plugin directory, `plugin.json`, supporting files, and `README.md`.
3. Update `registry.json`.
4. Run a quick sanity check:
   ```bash
   # Validate plugin.json against the schema (requires ajv-cli)
   npx ajv validate -s schemas/plugin.schema.json -d plugins/<type>/<name>/plugin.json

   # Dry-run the installer
   ./scripts/install.sh <type>/<name> --dry-run
   ```
5. Open a PR against `main` with the title `feat: add <name> <type>`.
6. Fill in the PR template — describe the plugin and why it's useful.

### PR checklist

- [ ] Plugin directory follows the structure described above
- [ ] `plugin.json` validates against the schema (`npx ajv validate -s schemas/plugin.schema.json -d plugins/<type>/<name>/plugin.json`)
- [ ] `.claude-plugin/plugin.json` present with at minimum a `name` field
- [ ] Type-specific native file present: `.mcp.json` / `skills/<trigger>/SKILL.md` / `hooks/hooks.json`
- [ ] `README.md` covers prerequisites, installation, configuration, and a usage example
- [ ] `.claude-plugin/marketplace.json` updated with the new plugin entry
- [ ] `registry.json` updated
- [ ] No secrets or credentials included anywhere
- [ ] `--dry-run` completes without errors (`./scripts/install.sh <type>/<name> --dry-run`)

---

## Code of conduct

Be kind. Review feedback constructively. Assume good intent.

If you experience or witness unacceptable behaviour, open an issue or contact the maintainers directly.
