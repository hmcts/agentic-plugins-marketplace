# GitHub MCP Server

Gives Claude the ability to interact with GitHub — search code, read files, manage issues, create and review pull requests — without leaving the conversation.

## Tools provided

| Tool | Description |
|------|-------------|
| `search_repositories` | Search GitHub repositories |
| `get_file_contents` | Read a file from any public (or accessible private) repo |
| `create_issue` | Open a new issue |
| `list_issues` | List issues with filtering |
| `create_pull_request` | Open a pull request |
| `get_pull_request` | Fetch PR details and diff |
| `search_code` | Full-text code search across GitHub |

## Prerequisites

- Node.js 18+ (for `npx`)
- A GitHub Personal Access Token with the scopes your use-case needs:
  - `repo` — full access to private repositories
  - `read:org` — read org membership (optional)

## Installation

```bash
# Quick install via the marketplace installer
./scripts/install.sh mcp-servers/github

# Or add manually
claude mcp add github \
  -e GITHUB_PERSONAL_ACCESS_TOKEN=<your-token> \
  -- npx -y @modelcontextprotocol/server-github
```

## Configuration

Set the following environment variable before installing, or export it in your shell profile:

```bash
export GITHUB_PERSONAL_ACCESS_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxx
```

## Usage example

Once installed, Claude can answer questions like:

> "List all open issues labelled `bug` in anthropics/claude-code and summarise the top 5."

> "Search for usages of `useEffect` with missing dependency arrays across my org's repos."
