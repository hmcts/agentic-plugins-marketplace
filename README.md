# Agentic Plugins Marketplace

An easy way to make and share reusable Claude Code plugins — MCP servers, skills, agents, hooks, and project templates. Browse and install them directly from Claude Code's built-in `/plugin` TUI using the native marketplace capability.

---

## Table of contents

- [Official Claude plugin marketplaces](#official-claude-plugin-marketplaces)
- [Security — prompt injection risk](#security--prompt-injection-risk)
- [Plugin types](#plugin-types)
- [Installation](#installation)
  - [Step 1 — add this marketplace](#step-1--add-this-marketplace)
  - [Team setup — commit .claude/settings.json](#team-setup--commit-claudesettingsjson)
  - [Step 2 — browse and install](#step-2--browse-and-install)
  - [Plugin scopes](#plugin-scopes)
- [Using Claude to discover plugins](#using-claude-to-discover-plugins)
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
When Claude calls a tool, the server's response is injected directly into Claude's context. A malicious server can embed text designed to hijack Claude's subsequent behaviour.

**Skills — prompt injection via SKILL.md**
A skill file from an untrusted source can contain hidden or misleading instructions that override Claude's normal behaviour when invoked.

**Hooks — arbitrary code execution**
Hook scripts execute as shell commands with the full privileges of your user account — no sandboxing.

### How to protect yourself

- **Prefer official marketplaces** for any plugin that touches sensitive systems.
- **Read the source before installing.** Review server code, read `SKILL.md` in full, read `hook.sh` line by line.
- **Use the `audit-log` hook** to record every tool Claude calls — it makes injected behaviour visible after the fact.
- **Scope permissions tightly.** Use read-only credentials where possible (e.g. a read-only database user for the `postgres` plugin).

---

## Plugin types

| Type | What it does |
|------|-------------|
| **MCP Server** | Gives Claude new tools to call external APIs and services |
| **Skill** | Prompt that guides Claude through a task — auto-triggered or slash-invoked |
| **Agent** | Specialised sub-agent Claude can spawn to handle a focused task in isolation |
| **Hook** | Shell script that runs automatically on Claude lifecycle events |
| **Template** | Pre-written `CLAUDE.md` for a specific project type |

Browse all available plugins and official recommendations in [CATALOG.md](CATALOG.md).

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
hmcts/agentic-plugins-marketplace
```

### Team setup — commit `.claude/settings.json`

This repo ships a `.claude/settings.json` that auto-enables all skills, hooks, and templates via `enabledPlugins`. MCP servers are intentionally excluded — they run as persistent subprocesses and require credentials, so team members should opt in individually.

Cloning the repo and opening it in Claude Code is enough — the marketplace source is registered in Step 1, and `enabledPlugins` in `.claude/settings.json` activates the bundled plugins automatically. No additional install step required.

### Step 2 — browse and install

Switch to the **Discover** tab to see all available plugins. To install from the command line:

```bash
# Install for the current project only
/plugin install code-review@agentic-plugins-marketplace

# Install globally — active in every project
/plugin install audit-log@agentic-plugins-marketplace --global
```

For MCP server plugins, Claude Code will prompt for any required API keys and store secrets in your OS keychain — no manual JSON editing needed.

### Plugin scopes

| Scope | Activates in | How to install |
|-------|-------------|----------------|
| **Project** | The current directory only | `/plugin install <name>@agentic-plugins-marketplace` |
| **Global** | Every project you open | `/plugin install <name>@agentic-plugins-marketplace --global` |

---

## Using Claude to discover plugins

Two plugins make the marketplace searchable from within a Claude conversation.

### Option A — marketplace skill

```bash
/plugin install marketplace-skill@agentic-plugins-marketplace
```

Then in any session, just describe what you need:

```
> what skills are available?
> anything for databases?
> tell me about the audit-log hook
```

### Option B — Marketplace MCP server

Registers `list_plugins`, `search_plugins`, and `get_plugin` tools so Claude can answer plugin questions in any conversation automatically, without a slash command:

```bash
/plugin install marketplace@agentic-plugins-marketplace
```

| | Marketplace skill | Marketplace MCP server |
|---|---|---|
| Setup | Install one skill | Install MCP server + set `MARKETPLACE_DIR` |
| Requires Node.js | No | Yes |
| Available in every conversation | No | Yes |

---

## Contributing

Claude can guide you through the entire contribution process — creating a new plugin from scratch or migrating an existing one from another format. Open this repo in Claude Code and describe what you want to do.

### Create a new plugin

Claude will suggest the right plugin type for your use case, install the appropriate official creation tool, and generate the required files and structure.

```
I want a plugin that reviews Terraform plans for security issues before apply
```

```
Create a hook that posts a desktop notification when Claude finishes a long task
```

```
Build an MCP server that wraps the GitHub CLI so Claude can manage PRs
```

### Migrate an existing plugin

Claude will inspect the source, flag any type mismatches, restructure the files to match this repo's layout, and iterate through `/reload-plugins` until the plugin loads cleanly.

```
I have a SKILL.md file I've been using locally — help me package it for the marketplace
```

```
Here's my settings.json MCP entry for a Postgres server. Migrate it to a proper plugin.
```

```
I found this hook script on GitHub. Can you review it and migrate it here?
```

For the full contribution guide — directory structure, required files, testing checklist, and security guidance — see [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT — see [LICENSE](LICENSE).
