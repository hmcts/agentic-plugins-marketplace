# MCP Server Plugins

Model Context Protocol (MCP) servers extend Claude with new **tools** — callable functions that let Claude interact with external services, databases, and APIs.

## Available servers

| Plugin | Description | Author |
|--------|-------------|--------|
| [marketplace](./marketplace/) | Browse, search, and install plugins via Claude tools | agentic-plugins-marketplace |
| [github](./github/) | Search repos, read files, manage issues and PRs | Anthropic |
| [filesystem](./filesystem/) | Sandboxed read/write access to local directories | Anthropic |
| [postgres](./postgres/) | Read-only SQL queries against PostgreSQL | Anthropic |
| [slack](./slack/) | Read channels and post messages to Slack | Anthropic |

## How MCP servers work

When you install an MCP server, Claude Code launches it as a subprocess and communicates over a standard protocol. Claude automatically discovers the tools the server exposes and can call them during conversations.

```
Claude Code  <──stdio──>  MCP Server  <──API/SDK──>  External Service
```

## Adding a new MCP server

See [CONTRIBUTING.md](../../../CONTRIBUTING.md#adding-an-mcp-server).
