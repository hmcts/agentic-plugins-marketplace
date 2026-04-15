# Marketplace MCP Server

The marketplace's own MCP server. Once installed, Claude gains four tools — `list_plugins`, `search_plugins`, `get_plugin`, and `install_plugin` — so it can browse and install plugins as part of any conversation, not just when `/marketplace` is invoked.

This is the most integrated way to use the marketplace: Claude can proactively suggest plugins, answer "is there a plugin for X?" questions, and install them on request without you leaving your current task.

## Tools provided

| Tool | Description |
|------|-------------|
| `list_plugins` | List all plugins, optionally filtered by type |
| `search_plugins` | Full-text search across name, description, and tags |
| `get_plugin` | Detailed info + README for a single plugin |
| `install_plugin` | Run the installer (dry-run by default; set `dry_run: false` to install) |

## Prerequisites

- Node.js 18+
- The marketplace repository cloned locally
- `MARKETPLACE_DIR` set to the clone path

## Installation

```bash
# 1. Clone the marketplace (if not already done)
git clone https://github.com/your-org/agentic-plugins-marketplace.git ~/marketplace
export MARKETPLACE_DIR=~/marketplace

# 2. Register the MCP server
claude mcp add marketplace \
  -e MARKETPLACE_DIR=$MARKETPLACE_DIR \
  -- node $MARKETPLACE_DIR/plugins/mcp-servers/marketplace/server.js
```

Or via the installer:

```bash
MARKETPLACE_DIR=$(pwd) ./scripts/install.sh mcp-servers/marketplace
```

Restart Claude Code after installation.

## Usage examples

Once installed, you can ask Claude in natural language:

> "What plugins are available for working with databases?"

> "Is there anything that can send me notifications when you finish a task?"

> "Show me everything in the hooks category."

> "Install the github MCP server." *(Claude will dry-run first and ask for confirmation)*

> "What does the audit-log hook do exactly?"

## Difference from the `/marketplace` skill

| | Marketplace skill | Marketplace MCP server |
|---|---|---|
| How invoked | `/marketplace` slash command | Available in every conversation automatically |
| Claude's access | Reads files via shell | Structured tool calls |
| Discoverability | Only when explicitly invoked | Claude can proactively suggest plugins |
| Setup | Copy one `.md` file | Register MCP server, restart Claude Code |
