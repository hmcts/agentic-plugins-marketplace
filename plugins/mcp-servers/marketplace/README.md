# Marketplace MCP Server

Gives Claude three tools — `list_plugins`, `search_plugins`, and `get_plugin` — available in **every** conversation. Claude can proactively suggest relevant plugins and answer "is there a plugin for X?" without you having to open the `/plugin` TUI.

## Tools provided

| Tool | Description |
|------|-------------|
| `list_plugins` | List all plugins, optionally filtered by category |
| `search_plugins` | Full-text search across name, description, and tags |
| `get_plugin` | Full README + install command for a specific plugin |

## Prerequisites

- Node.js 18+
- This marketplace repository cloned locally

## Installation

```
/plugin install marketplace@agentic-plugins-marketplace
```

The `/plugin` TUI will prompt for `MARKETPLACE_DIR` — set it to the absolute path of your local clone of this repo.

## Usage examples

Once installed, ask Claude in any conversation:

> "What plugins are available for working with databases?"

> "Is there anything that can notify me when you finish a task?"

> "Tell me about the audit-log hook."

Claude responds with plugin details and the exact `/plugin install` command to use.

## Difference from the `/marketplace` skill

| | `/marketplace` skill | Marketplace MCP server |
|---|---|---|
| How invoked | `/marketplace` slash command | Available in every conversation automatically |
| Requires Node.js | No | Yes |
| Claude proactively suggests plugins | No | Yes |
