# MCP Server Plugins

MCP servers extend Claude with new **tools** — callable functions that let Claude interact with external services, databases, and APIs.

## Available servers

| Plugin | Description |
|--------|-------------|
| [marketplace](./marketplace/) | Browse and search marketplace plugins via Claude tools |
| [filesystem](./filesystem/) | Sandboxed read/write access to local directories |
| [postgres](./postgres/) | Read-only SQL queries against PostgreSQL |

> **GitHub** — use the official plugin at [claude.com/plugins/github](https://claude.com/plugins/github) rather than a community duplicate.
> **Slack** — use the official plugin at [claude.com/plugins/slack](https://claude.com/plugins/slack) rather than a community duplicate.

## Installation

```
/plugin install <name>@agentic-plugins-marketplace
```

The `/plugin` TUI will prompt for any required API keys and store them in your OS keychain.

## How MCP servers work

When you install an MCP server plugin, Claude Code launches it as a subprocess and communicates over the MCP protocol. Claude automatically discovers the tools the server exposes and can call them in any conversation.

## Adding a new MCP server

See [CONTRIBUTING.md](../../CONTRIBUTING.md#adding-an-mcp-server).
