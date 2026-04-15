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
- [Installation](#installation)
  - [Step 1 — add this marketplace](#step-1--add-this-marketplace)
  - [Step 2 — browse and install](#step-2--browse-and-install)
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
| [github](plugins/mcp-servers/github/) | Search repos, read files, manage issues and PRs |
| [filesystem](plugins/mcp-servers/filesystem/) | Sandboxed read/write access to local directories |
| [postgres](plugins/mcp-servers/postgres/) | Read-only SQL queries against PostgreSQL |
| [slack](plugins/mcp-servers/slack/) | Read channel history and post messages to Slack |

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

### Step 2 — browse and install

Switch to the **Discover** tab to see all available plugins. To install from the command line without opening the TUI:

```bash
# Install a single plugin
/plugin install github@agentic-plugins-marketplace
/plugin install code-review@agentic-plugins-marketplace
/plugin install audit-log@agentic-plugins-marketplace

# Install all plugins at once
/plugin install --all @agentic-plugins-marketplace
```

For MCP server plugins, Claude Code will prompt for any required API keys or configuration and store secrets in your OS keychain — no manual JSON editing needed.

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
