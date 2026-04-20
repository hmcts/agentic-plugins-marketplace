# Agentic Plugins Marketplace

A community-maintained collection of plugins for [Claude Code](https://claude.ai/code) — Anthropic's AI coding agent. Browse and install MCP servers, skills, hooks, and project templates directly from Claude Code's built-in `/plugin` TUI.

---

## Table of contents

- [Official Claude plugin marketplaces](#official-claude-plugin-marketplaces)
- [Security — prompt injection risk](#security--prompt-injection-risk)
- [Plugin types](#plugin-types)
- [Available plugins](#available-plugins)
  - [MCP Servers](#mcp-servers)
  - [Skills](#skills)
  - [Hooks](#hooks)
  - [Templates](#templates)
- [Recommended official plugins](#recommended-official-plugins)
  - [MCP servers — integrations](#mcp-servers--integrations)
  - [Skills — slash commands](#skills--slash-commands)
  - [Hooks — automatic](#hooks--automatic)
- [Installation](#installation)
  - [Team setup — commit .claude/settings.json](#team-setup--commit-claudesettingsjson)
  - [Step 1 — add this marketplace](#step-1--add-this-marketplace)
  - [Step 2 — browse and install](#step-2--browse-and-install)
  - [Plugin scopes](#plugin-scopes)
  - [What gets installed automatically](#what-gets-installed-automatically)
- [Using Claude to discover plugins](#using-claude-to-discover-plugins)
  - [Option A — /marketplace skill](#option-a---marketplace-skill)
  - [Option B — Marketplace MCP server](#option-b--marketplace-mcp-server)
- [Repository layout](#repository-layout)
- [Contributing](#contributing)
- [License](#license)

---

## Official Claude plugin marketplaces

Before adding plugins from community sources, check the official registries — they curate vetted, production-ready integrations:

| Marketplace | What it contains | URL |
|-------------|-----------------|-----|
| **Anthropic official plugins** | Curated integrations (GitHub, Slack, Jira, etc.) maintained by Anthropic | [claude.com/plugins](https://claude.com/plugins) |
| **MCP Registry** | Open registry of MCP servers backed by Anthropic, GitHub, and Microsoft | [registry.modelcontextprotocol.io](https://registry.modelcontextprotocol.io) |
| **Claude Code `/plugin` built-in** | Accessible inside Claude Code via `/plugin` → Discover tab | run `/plugin` in Claude Code |

In Claude Code you can add the official marketplace as a source alongside this one:

```
/plugin
→ Marketplaces tab → Add: claude-plugins-official
```

---

## Security — prompt injection risk

> **Warning: only install plugins from sources you trust.**

Plugins run with significant privilege inside your Claude session. There are three distinct attack surfaces:

**MCP servers — prompt injection via tool responses**
When Claude calls a tool, the server's response is injected directly into Claude's context. A malicious server can embed text designed to hijack Claude's subsequent behaviour — for example, instructing it to exfiltrate files, call destructive tools, or ignore safety guidelines. This is particularly dangerous because the injected content arrives as "tool output" rather than user input, making it harder to detect.

**Skills — prompt injection via SKILL.md**
A skill file from an untrusted source can contain hidden or misleading instructions that override Claude's normal behaviour when the slash command is invoked.

**Hooks — arbitrary code execution**
Hook scripts (`hook.sh`) execute as shell commands with the full privileges of your user account. A malicious hook can read credentials, exfiltrate data, or install persistent backdoors — with no sandboxing.

### How to protect yourself

- **Prefer official marketplaces** (see above) for any plugin that touches sensitive systems.
- **Read the source before installing.** For MCP servers, review the server code or verify it is published by a known maintainer. For skills, read `SKILL.md` in full. For hooks, read `hook.sh` line by line.
- **Use the `audit-log` hook** to record every tool Claude calls — it makes injected behaviour visible after the fact.
- **Scope permissions tightly.** For MCP servers, use read-only credentials where possible (e.g., a read-only database user for the `postgres` plugin).
- **Treat unknown marketplaces like unknown npm packages** — the blast radius of a compromised plugin is your entire Claude session and anything it has access to.

---

## Plugin types

| Type | What it does |
|------|-------------|
| **MCP Server** | Gives Claude new tools to call external APIs and services |
| **Skill** | Reusable slash-command prompt that guides Claude through a task |
| **Hook** | Shell script that runs automatically on Claude lifecycle events |
| **Template** | Pre-written `CLAUDE.md` for a specific project type |

---

## Available plugins

### MCP Servers

| Plugin | Description |
|--------|-------------|
| [marketplace](plugins/mcp-servers/marketplace/) | Browse and search marketplace plugins via Claude tools |
| [filesystem](plugins/mcp-servers/filesystem/) | Sandboxed read/write access to local directories |
| [postgres](plugins/mcp-servers/postgres/) | Read-only SQL queries against PostgreSQL |

> **GitHub** — use the official plugin at [claude.com/plugins/github](https://claude.com/plugins/github) (172k+ installs, maintained by GitHub).
> **Slack** — use the official plugin at [claude.com/plugins/slack](https://claude.com/plugins/slack) (40k+ installs, verified by Slack/Anthropic).

### Skills

| Plugin | Trigger | Description |
|--------|---------|-------------|
| [marketplace](plugins/skills/marketplace/) | `/marketplace` | Browse and install plugins conversationally |
| [code-review](plugins/skills/code-review/) | `/review` | Structured PR review — security, correctness, performance |
| [conventional-commit](plugins/skills/conventional-commit/) | `/commit` | Conventional Commits message from staged changes |
| [explain-codebase](plugins/skills/explain-codebase/) | `/explain` | Onboarding guide for new developers |

### Hooks

| Plugin | Event | Description |
|--------|-------|-------------|
| [notify-on-stop](plugins/hooks/notify-on-stop/) | `Stop` | Desktop notification when Claude finishes |
| [audit-log](plugins/hooks/audit-log/) | `PostToolUse` | JSON audit trail of every tool call |

### Templates

| Plugin | Stack | Description |
|--------|-------|-------------|
| [python-project](plugins/templates/python-project/) | Python / uv | `CLAUDE.md` for Python with uv, pytest, ruff, mypy |
| [nodejs-project](plugins/templates/nodejs-project/) | Node.js / TypeScript | `CLAUDE.md` for TypeScript with Vitest and ESLint |

> **A note on plugin overhead** — every installed plugin has a cost. MCP servers run as persistent subprocesses and expose all their tools to Claude on every turn, making responses slightly slower and more expensive. `PreToolUse` hooks execute synchronously before every tool call — a slow or broken hook blocks Claude entirely. `PostToolUse` hooks multiply across tool calls, spawning a subprocess each time. Skills cost nothing until invoked. The practical rule: enable hooks and skills for the whole team, but let individuals opt in to MCP servers based on the services they actually use.

---

## Recommended official plugins

Curated picks from [claude.com/plugins](https://claude.com/plugins), grouped by type and category. Install any of them in Claude Code via `/plugin`.

> Most of these are hooks or skills and have negligible overhead. MCP servers (GitHub, Greptile, Atlassian, the LSPs) launch subprocesses — only install the ones your project actively uses.

### MCP servers — integrations

#### Developer tools

| Plugin | Description |
|--------|-------------|
| [GitHub](https://claude.com/plugins/github) | Official GitHub integration — manage repos, issues, PRs, Actions, and Dependabot alerts directly from Claude |
| [Greptile](https://claude.com/plugins/greptile) | AI-powered codebase search and automated PR reviews integrated with GitHub and GitLab |
| [Pyright LSP](https://claude.com/plugins/pyright-lsp) | Python static type checking — real-time type errors and diagnostics without executing code |
| [TypeScript LSP](https://claude.com/plugins/typescript-lsp) | TS/JS code intelligence — go-to-definition, find references, real-time error checking |

#### Project management

| Plugin | Description |
|--------|-------------|
| [Atlassian](https://claude.com/plugins/atlassian) | Search and manage Jira, Confluence, and Compass via natural language commands |

### Skills — slash commands

#### Architecture & workflow

| Plugin | Trigger | Description |
|--------|---------|-------------|
| [Superpowers](https://claude.com/plugins/superpowers) | `/brainstorming`, `/execute-plan` | TDD cycles, Socratic planning, and subagent-driven development with built-in review checkpoints |
| [Claude Code Setup](https://claude.com/plugins/claude-code-setup) | — | Analyses your project and recommends relevant MCP servers, skills, hooks, and agents |

#### Git & version control

| Plugin | Trigger | Description |
|--------|---------|-------------|
| [Commit Commands](https://claude.com/plugins/commit-commands) | `/commit`, `/commit-push-pr`, `/clean_gone` | Generates commit messages matching repo style; full commit → push → PR workflow in one command |

#### Code review

| Plugin | Trigger | Description |
|--------|---------|-------------|
| [Code Review](https://claude.com/plugins/code-review) | `/code-review` | Five parallel review agents with confidence-score filtering to reduce false positives |
| [PR Review Toolkit](https://claude.com/plugins/pr-review-toolkit) | — | Six specialised agents covering tests, type design, silent failures, docs, and code simplicity |

#### Memory & documentation

| Plugin | Trigger | Description |
|--------|---------|-------------|
| [Remember](https://claude.com/plugins/remember) | `/remember` | Captures sessions into tiered logs so Claude recalls decisions and file changes across restarts |
| [CLAUDE.md Management](https://claude.com/plugins/claude-md-management) | `/revise-claude-md` | Audits and proposes updates to CLAUDE.md files to keep project memory accurate |

#### Plugin development

| Plugin | Trigger | Description |
|--------|---------|-------------|
| [Plugin Developer Toolkit](https://claude.com/plugins/plugin-dev) | `/plugin-dev:create-plugin` | 8-phase guided workflow for building hooks, skills, MCP servers, and agents |
| [Skill Creator](https://claude.com/plugins/skill-creator) | `/skill-creator` | Create, evaluate, improve, and A/B benchmark Claude Code skills |

### Hooks — automatic

#### Security

| Plugin | Event | Description |
|--------|-------|-------------|
| [Security Guidance](https://claude.com/plugins/security-guidance) | `PreToolUse` | Intercepts Write/Edit operations and warns on command injection, XSS, eval, and unsafe deserialization before changes land |

#### Code quality

| Plugin | Event | Description |
|--------|-------|-------------|
| [Code Simplifier](https://claude.com/plugins/code-simplifier) | automatic | Simplifies recently modified code — reduces nesting, improves naming, removes redundancy while preserving behaviour |

#### Learning & output style

| Plugin | Event | Description |
|--------|-------|-------------|
| [Learning Output Style](https://claude.com/plugins/learning-output-style) | session start | Pauses at architectural decisions and prompts you to contribute key code, turning sessions into hands-on learning |
| [Explanatory Output Style](https://claude.com/plugins/explanatory-output-style) | session start | Adds insight boxes to responses covering codebase-specific patterns and design trade-offs |

---

## Installation

Plugins are installed through Claude Code's built-in `/plugin` command, which opens a terminal UI with four tabs: **Discover**, **Installed**, **Marketplaces**, and **Errors**.

### Step 1 — add this marketplace

Open Claude Code and run:

```
/plugin
```

Navigate to the **Marketplaces** tab and add:

```
github@hmcts/agentic-plugins-marketplace
```

### Team setup — commit `.claude/settings.json`

This repo ships a `.claude/settings.json` that pre-registers the marketplace and auto-enables all skills, hooks, and templates. MCP servers are intentionally excluded from auto-install — they run as persistent subprocesses and require credentials, so team members should opt in individually based on the services they use.

The settings file also enables [Security Guidance](https://claude.com/plugins/security-guidance) from the official marketplace, which intercepts Write/Edit operations and warns on common vulnerabilities before changes land.

After cloning, run:

```
/plugin install --all @agentic-plugins-marketplace
```

`enabledPlugins` keeps the activated plugins live for the project without further configuration.

### Step 2 — browse and install

Switch to the **Discover** tab to see all available plugins. To install from the command line without opening the TUI:

```bash
# Install a single plugin (project scope — only active in the current directory)
/plugin install code-review@agentic-plugins-marketplace

# Install globally — active in every project you open
/plugin install audit-log@agentic-plugins-marketplace --global
```

For MCP server plugins, Claude Code will prompt for any required API keys or configuration and store secrets in your OS keychain — no manual JSON editing needed.

### Plugin scopes

Every plugin is installed with a **scope** that controls where it activates:

| Scope | Activates in | How to install |
|-------|-------------|----------------|
| **Project** | The current directory only | `/plugin install <name>@agentic-plugins-marketplace` |
| **Global** | Every project you open | `/plugin install <name>@agentic-plugins-marketplace --global` |

**Project scope** is the default and the safer choice — it keeps plugins contained to the repo that needs them and lets teams commit `.claude/settings.json` to share the same setup with everyone who clones the repo.

**Global scope** is useful for personal productivity plugins (e.g. `notify-on-stop`, `audit-log`) that you want active everywhere regardless of project.

#### Installing from a local clone vs GitHub

If you have cloned this repo locally, register it as a local marketplace source so Claude Code reads plugins directly from disk (no network, always up to date with your working branch):

```bash
# In .claude/settings.json (project) or ~/.claude/settings.json (global)
{
  "extraKnownMarketplaces": {
    "agentic-plugins-marketplace": {
      "source": { "source": "directory", "path": "/path/to/your/clone" }
    }
  }
}
```

If you have not cloned the repo, register it from GitHub instead:

```bash
# Pulls plugins from the published GitHub repo
{
  "extraKnownMarketplaces": {
    "agentic-plugins-marketplace": {
      "source": { "source": "github", "repo": "hmcts/agentic-plugins-marketplace" }
    }
  }
}
```

Both sources use the same `/plugin install` commands once registered.

### What gets installed automatically

| File in the plugin directory | What Claude Code does |
|-----------------------------|----------------------|
| `.mcp.json` | Registers the MCP server; prompts for env vars via `userConfig` |
| `skills/<trigger>/SKILL.md` | Adds the `/trigger` slash command |
| `hooks/hooks.json` | Registers the lifecycle hook |

---

## Using Claude to discover plugins

Two plugins make the marketplace searchable from within a Claude conversation.

### Option A — `/marketplace` skill

A single slash command. No extra setup beyond installing the skill itself:

```bash
/plugin install marketplace-skill@agentic-plugins-marketplace
```

Then in any session:

```
/marketplace
> what skills are available?
> anything for databases?
> tell me about the audit-log hook
```

### Option B — Marketplace MCP server

Registers `list_plugins`, `search_plugins`, and `get_plugin` tools so Claude can answer plugin questions **in any conversation automatically**, without invoking a slash command:

```bash
/plugin install marketplace@agentic-plugins-marketplace
```

The `/plugin` TUI will prompt for `MARKETPLACE_DIR` — the path to your local clone of this repo.

| | `/marketplace` skill | Marketplace MCP server |
|---|---|---|
| Setup | Install one skill | Install MCP server + set `MARKETPLACE_DIR` |
| Requires Node.js | No | Yes |
| Available in every conversation | No (invoke `/marketplace`) | Yes |

---

## Repository layout

```
agentic-plugins-marketplace/
├── .claude-plugin/
│   └── marketplace.json        ← /plugin marketplace catalog
├── plugins/
│   ├── mcp-servers/
│   │   └── <name>/
│   │       ├── .claude-plugin/
│   │       │   └── plugin.json ← metadata + userConfig for required env vars
│   │       ├── .mcp.json       ← MCP server config
│   │       └── README.md
│   ├── skills/
│   │   └── <name>/
│   │       ├── .claude-plugin/
│   │       │   └── plugin.json
│   │       ├── skills/
│   │       │   └── <trigger>/
│   │       │       └── SKILL.md
│   │       └── README.md
│   ├── hooks/
│   │   └── <name>/
│   │       ├── .claude-plugin/
│   │       │   └── plugin.json
│   │       ├── hooks/
│   │       │   └── hooks.json
│   │       ├── hook.sh
│   │       └── README.md
│   └── templates/
│       └── <name>/
│           ├── .claude-plugin/
│           │   └── plugin.json
│           ├── CLAUDE.md
│           └── README.md
├── README.md
└── CONTRIBUTING.md
```

---

## Contributing

Want to add a plugin or improve an existing one? See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT — see [LICENSE](LICENSE).
