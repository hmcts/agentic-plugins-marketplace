# Agentic Plugins Marketplace

A community-maintained collection of plugins for [Claude Code](https://claude.ai/code) — Anthropic's AI coding agent. Browse and install MCP servers, skills, hooks, and project templates to extend what Claude can do in your development workflow.

---

## Table of contents

- [Plugin types](#plugin-types)
- [Available plugins](#available-plugins)
  - [MCP Servers](#mcp-servers)
  - [Skills (slash commands)](#skills-slash-commands)
  - [Hooks](#hooks)
  - [Templates](#templates)
- [Installing from within Claude](#installing-from-within-claude)
  - [Option A — Marketplace skill (quickest bootstrap)](#option-a--marketplace-skill-quickest-bootstrap)
  - [Option B — Marketplace MCP server (fully integrated)](#option-b--marketplace-mcp-server-fully-integrated)
- [Installation (CLI)](#installation-cli)
  - [Prerequisites](#prerequisites)
  - [Quick install](#quick-install)
  - [Install a specific plugin](#install-a-specific-plugin)
  - [Dry run](#dry-run)
- [How each type installs](#how-each-type-installs)
  - [MCP Servers](#mcp-servers-1)
  - [Skills](#skills)
  - [Hooks](#hooks-1)
  - [Templates](#templates-1)
- [Repository layout](#repository-layout)
- [Contributing](#contributing)
- [License](#license)

---

## Plugin types

| Type | What it does | Installed to |
|------|-------------|-------------|
| **MCP Server** | Gives Claude new tools to call external APIs and services | `claude mcp add` |
| **Skill** | Reusable slash-command prompt that guides Claude through a task | `~/.claude/skills/` |
| **Hook** | Shell script that runs automatically on Claude lifecycle events | `~/.claude/settings.json` |
| **Template** | Pre-written `CLAUDE.md` for a specific project type | your project root |

---

## Available plugins

### MCP Servers

| Plugin | Description |
|--------|-------------|
| [marketplace](plugins/mcp-servers/marketplace/) | Browse, search, and install plugins via Claude tools |
| [github](plugins/mcp-servers/github/) | Search repos, read files, manage issues and PRs |
| [filesystem](plugins/mcp-servers/filesystem/) | Sandboxed read/write access to local directories |
| [postgres](plugins/mcp-servers/postgres/) | Read-only SQL queries against PostgreSQL |
| [slack](plugins/mcp-servers/slack/) | Read channels and post messages to Slack |

### Skills (slash commands)

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

## Installing from within Claude

By default the marketplace is just a git repository — Claude has no awareness of it. Two plugins change that, making the marketplace self-discoverable from inside any Claude Code session.

### Option A — Marketplace skill (quickest bootstrap)

The `/marketplace` skill is a single Markdown file. Install it with one `curl` command — **no git clone needed**:

```bash
mkdir -p ~/.claude/skills && curl -fsSL \
  https://raw.githubusercontent.com/your-org/agentic-plugins-marketplace/main/plugins/skills/marketplace/skill.md \
  -o ~/.claude/skills/marketplace.md
```

From your next Claude Code session, type `/marketplace` and talk to Claude naturally:

```
/marketplace
> what plugins are available?
> anything for Slack?
> install the github MCP server
```

Claude will show a dry-run and ask for confirmation before making any changes.

### Option B — Marketplace MCP server (fully integrated)

The marketplace MCP server registers four tools (`list_plugins`, `search_plugins`, `get_plugin`, `install_plugin`) that are available in **every** conversation — Claude can proactively suggest plugins without you having to invoke a slash command first.

```bash
# 1. Clone the marketplace
git clone https://github.com/your-org/agentic-plugins-marketplace.git ~/marketplace
export MARKETPLACE_DIR=~/marketplace

# 2. Register the MCP server
claude mcp add marketplace \
  -e MARKETPLACE_DIR=$MARKETPLACE_DIR \
  -- node $MARKETPLACE_DIR/plugins/mcp-servers/marketplace/server.js
```

Restart Claude Code. Claude can now answer questions like:

> "Is there a plugin that logs what tools you use?"

> "Install the notify-on-stop hook."

See [plugins/mcp-servers/marketplace/](plugins/mcp-servers/marketplace/) for full documentation.

### Comparison

| | Marketplace skill | Marketplace MCP server |
|---|---|---|
| Setup | `curl` one file | Clone repo + `claude mcp add` |
| Requires Node.js | No | Yes |
| Invocation | `/marketplace` command | Available in every conversation |
| Claude proactively suggests plugins | No | Yes |

---

## Installation (CLI)

### Prerequisites

- [Claude Code](https://claude.ai/code) CLI installed and authenticated
- `jq` (`brew install jq` / `apt install jq`)
- `node` 18+ for MCP servers that use `npx`

### Quick install

Clone the marketplace and run the installer:

```bash
git clone https://github.com/your-org/agentic-plugins-marketplace.git
cd agentic-plugins-marketplace
./scripts/install.sh
```

The interactive mode lists all available plugins. Type the plugin path to install it.

### Install a specific plugin

```bash
# MCP server
./scripts/install.sh mcp-servers/github

# Skill
./scripts/install.sh skills/code-review

# Hook
./scripts/install.sh hooks/notify-on-stop

# Template (defaults to current directory)
./scripts/install.sh templates/python-project

# Template to a specific project
./scripts/install.sh templates/python-project --target /path/to/my-project
```

### Dry run

Preview what the installer will do without making any changes:

```bash
./scripts/install.sh mcp-servers/github --dry-run
```

---

## How each type installs

### MCP Servers

The installer calls `claude mcp add` with the command and environment variables from `plugin.json`. Any `${VAR_NAME}` placeholders are resolved from your current environment.

```bash
# What the installer runs under the hood:
claude mcp add github \
  -e GITHUB_PERSONAL_ACCESS_TOKEN=<your-token> \
  -- npx -y @modelcontextprotocol/server-github
```

After installation, restart Claude Code. The new tools will appear automatically.

### Skills

The installer copies the skill's `.md` file to `~/.claude/skills/<trigger>.md`. The next time you open Claude Code, the slash command is available:

```
/review     # runs the code-review skill
/commit     # runs the conventional-commit skill
/explain    # runs the explain-codebase skill
```

### Hooks

The installer:
1. Copies the hook script to `~/.claude/hooks/`
2. Makes it executable
3. Merges the hook configuration into `~/.claude/settings.json`

The hook runs automatically on the configured lifecycle event in every subsequent session.

### Templates

The installer copies the `CLAUDE.md` file to your project root (or `--target` directory). Open the file and fill in the placeholders specific to your project.

---

## Repository layout

```
agentic-plugins-marketplace/
├── plugins/
│   ├── mcp-servers/        # MCP server plugins
│   │   └── <name>/
│   │       ├── plugin.json     ← manifest (required)
│   │       └── README.md       ← user-facing docs (required)
│   ├── skills/             # Slash-command prompt plugins
│   │   └── <name>/
│   │       ├── plugin.json
│   │       ├── skill.md        ← the prompt template
│   │       └── README.md
│   ├── hooks/              # Lifecycle hook plugins
│   │   └── <name>/
│   │       ├── plugin.json
│   │       ├── hook.sh         ← the hook script
│   │       └── README.md
│   └── templates/          # CLAUDE.md project templates
│       └── <name>/
│           ├── plugin.json
│           ├── CLAUDE.md       ← the template file
│           └── README.md
├── schemas/
│   └── plugin.schema.json  ← JSON Schema for plugin.json
├── scripts/
│   └── install.sh          ← installer script
├── registry.json           ← machine-readable plugin index
├── README.md
└── CONTRIBUTING.md
```

---

## Contributing

Want to add a plugin, fix a bug, or improve docs? See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT — see [LICENSE](LICENSE).
