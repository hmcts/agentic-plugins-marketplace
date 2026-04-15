# GitHub MCP Server

Gives Claude the ability to interact with GitHub — search code, read files, manage issues, create and review pull requests — without leaving the conversation. Uses the `gh` CLI for authentication, so no Personal Access Token is needed.

## Tools provided

Exposes the full GitHub API surface via `gh mcp serve`. Key capabilities include:

| Category | Examples |
|----------|---------|
| Repositories | search, create, fork, get metadata |
| Files | read contents, list directory, get commits |
| Issues | create, list, update, comment |
| Pull requests | create, list, review, merge, get diff |
| Code search | full-text search across GitHub |
| Actions | list runs, get logs |
| Notifications | list, mark as read |

## Prerequisites

- [`gh` CLI](https://cli.github.com/) installed and authenticated:
  ```bash
  brew install gh   # macOS
  gh auth login
  ```

## Installation

```
/plugin install github@agentic-plugins-marketplace
```

No additional configuration needed — the server inherits your existing `gh` session.

## Usage examples

> "List all open issues labelled `bug` in hmcts/agentic-plugins-marketplace and summarise the top 5."

> "Search for usages of `useEffect` with missing dependency arrays across my org's repos."

> "Create a PR from my current branch to main with a summary of the changes."
